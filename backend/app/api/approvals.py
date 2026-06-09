from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Project, Session as DBSession
from ..services.approval_service import (
    ApprovalNotFoundError,
    ApprovalService,
    InvalidApprovalStateError,
    approval_to_read,
)
from ..services.runtime_schemas import ApprovalCheckpointRead
from ..services.auth_service import AuthService
from ..services.team_service import PermissionDeniedError
from ..services.tenant_guard import TenantGuard, tenant_scope_required_for_cloud

router = APIRouter(prefix="", tags=["approvals"])


class ApprovalApproveRequest(BaseModel):
    artifact_id: str | None = Field(default=None, alias="artifactId")
    artifact_version: int | None = Field(default=None, alias="artifactVersion")
    comment: str | None = None

    model_config = {"populate_by_name": True}


class ApprovalRejectRequest(BaseModel):
    reason: str
    artifact_id: str | None = Field(default=None, alias="artifactId")
    artifact_version: int | None = Field(default=None, alias="artifactVersion")
    code_reference: dict | None = Field(default=None, alias="codeReference")

    model_config = {"populate_by_name": True}


def _approval_service(db: AsyncSession):
    from ..main import _event_bus
    return ApprovalService(db, event_bus=_event_bus)


async def _authorize_session(request: Request, db: AsyncSession, session_id: str, mode: str) -> None:
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    project = await db.get(Project, session.project_id) if session.project_id else None
    if not project:
        return
    if project.workspace_mode != "cloud" and not tenant_scope_required_for_cloud():
        return
    actor = await AuthService(db).resolve_request(request)
    if not actor:
        raise HTTPException(status_code=401, detail="请先登录后继续")
    scope = await TenantGuard(db).scope_for_user(actor)
    guard = TenantGuard(db)
    try:
        if mode == "read":
            await guard.assert_project_read(scope, project)
        else:
            await guard.assert_project_write(scope, project)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


async def _authorize_approval(request: Request, db: AsyncSession, checkpoint_id: str, mode: str):
    checkpoint = await _approval_service(db).get(checkpoint_id)
    await _authorize_session(request, db, checkpoint.session_id, mode)
    return checkpoint


@router.get("/sessions/{session_id}/approvals", response_model=list[ApprovalCheckpointRead])
async def list_session_approvals(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _authorize_session(request, db, session_id, "read")
    return await _approval_service(db).list_session(session_id)


@router.get("/approvals/{checkpoint_id}", response_model=ApprovalCheckpointRead)
async def get_approval(checkpoint_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        return approval_to_read(await _authorize_approval(request, db, checkpoint_id, "read"))
    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="approval not found")


@router.post("/approvals/{checkpoint_id}/approve", response_model=ApprovalCheckpointRead)
async def approve_checkpoint(
    checkpoint_id: str,
    request: Request,
    data: ApprovalApproveRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_approval(request, db, checkpoint_id, "write")
        checkpoint = await _approval_service(db).approve(
            checkpoint_id,
            artifact_id=data.artifact_id if data else None,
            artifact_version=data.artifact_version if data else None,
            comment=data.comment if data else None,
        )
    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="approval not found")
    except InvalidApprovalStateError:
        raise HTTPException(status_code=409, detail="APPROVAL_ALREADY_DECIDED")
    return approval_to_read(checkpoint)


@router.post("/approvals/{checkpoint_id}/reject", response_model=ApprovalCheckpointRead)
async def reject_checkpoint(
    checkpoint_id: str,
    data: ApprovalRejectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_approval(request, db, checkpoint_id, "write")
        checkpoint = await _approval_service(db).reject(
            checkpoint_id,
            reason=data.reason,
            artifact_id=data.artifact_id,
            artifact_version=data.artifact_version,
            code_reference=data.code_reference,
        )
    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="approval not found")
    except InvalidApprovalStateError:
        raise HTTPException(status_code=409, detail="APPROVAL_ALREADY_DECIDED")
    except ValueError:
        raise HTTPException(status_code=400, detail="REASON_REQUIRED")
    return approval_to_read(checkpoint)
