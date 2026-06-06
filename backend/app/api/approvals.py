from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession
from ..services.approval_service import (
    ApprovalNotFoundError,
    ApprovalService,
    InvalidApprovalStateError,
    approval_to_read,
)
from ..services.runtime_schemas import ApprovalCheckpointRead

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


@router.get("/sessions/{session_id}/approvals", response_model=list[ApprovalCheckpointRead])
async def list_session_approvals(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return await _approval_service(db).list_session(session_id)


@router.get("/approvals/{checkpoint_id}", response_model=ApprovalCheckpointRead)
async def get_approval(checkpoint_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return approval_to_read(await _approval_service(db).get(checkpoint_id))
    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="approval not found")


@router.post("/approvals/{checkpoint_id}/approve", response_model=ApprovalCheckpointRead)
async def approve_checkpoint(
    checkpoint_id: str,
    data: ApprovalApproveRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
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
    db: AsyncSession = Depends(get_db),
):
    try:
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
