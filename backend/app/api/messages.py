"""Phase 4 message action and search endpoints."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Message as DBMessage, Project, Session as DBSession
from ..services.artifact_output_bridge import (
    ArtifactOutputBridge,
    MessageNotFoundForScanError,
    SessionWithoutProjectError,
)
from ..services.cloud_agent_runtime import CloudAgentRuntimeService
from ..services.message_service_sqlalchemy import (
    InvalidMessageOperationError,
    MessageNotFoundError,
    SqlAlchemyMessageService,
    message_to_read,
)
from ..services.schemas import MessageCreate, MessageRead
from ..services.auth_service import AuthService
from ..services.team_service import PermissionDeniedError
from ..services.tenant_guard import TenantGuard, tenant_scope_required_for_cloud
from .artifacts import ArtifactRead

router = APIRouter(prefix="/messages", tags=["messages"])


async def _authorize_session_id(request: Request, db: AsyncSession, session_id: str, mode: str) -> None:
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


async def _authorize_message(request: Request, db: AsyncSession, message_id: str, mode: str) -> DBMessage:
    message = await db.get(DBMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message not found")
    await _authorize_session_id(request, db, message.session_id, mode)
    return message


class ReplyRequest(BaseModel):
    content: str


class PinResponse(BaseModel):
    is_pinned: bool = Field(alias="isPinned")

    model_config = {"populate_by_name": True}


class ArtifactScanRequest(BaseModel):
    force: bool = False


class ArtifactCandidateRead(BaseModel):
    artifact_type: str = Field(alias="artifactType")
    title: str
    source: str
    confidence: float
    reason: str
    content_preview: str = Field(alias="contentPreview")

    model_config = {"populate_by_name": True}


class ArtifactSkipRead(BaseModel):
    reason: str
    artifact_id: str | None = Field(default=None, alias="artifactId")
    title: str | None = None
    detail: str | None = None

    model_config = {"populate_by_name": True}


class ArtifactScanRead(BaseModel):
    created: list[ArtifactRead]
    candidates: list[ArtifactCandidateRead]
    skipped: list[ArtifactSkipRead]


@router.post("/{message_id}/reply", response_model=MessageRead, status_code=201)
async def reply_to_message(
    message_id: str,
    data: ReplyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    parent = await _authorize_message(request, db, message_id, "write")
    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="content must not be empty")

    svc = SqlAlchemyMessageService(db)
    try:
        return await svc.reply_to_message(
            MessageCreate(sessionId=parent.session_id, role="user", content=content),
            parent_message_id=message_id,
        )
    except InvalidMessageOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{message_id}/regenerate")
async def regenerate_message(
    message_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    message = await _authorize_message(request, db, message_id, "write")
    session = await db.get(DBSession, message.session_id)
    project = await db.get(Project, session.project_id) if session and session.project_id else None
    if project and project.workspace_mode == "cloud":
        actor = await AuthService(db).resolve_request(request)
        if not actor:
            raise HTTPException(status_code=401, detail="请先登录后继续")
        from ..main import _event_bus

        runtime = CloudAgentRuntimeService(db, event_bus=_event_bus)

        async def cloud_events() -> AsyncIterator[str]:
            async for item in runtime.stream_regenerate_message(message_id, actor=actor):
                yield item

        return StreamingResponse(cloud_events(), media_type="text/event-stream")

    svc = SqlAlchemyMessageService(db)

    async def events() -> AsyncIterator[str]:
        async for item in svc.regenerate_message(message_id):
            yield item

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/{message_id}/pin", response_model=PinResponse)
async def pin_message(message_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _authorize_message(request, db, message_id, "write")
    svc = SqlAlchemyMessageService(db)
    try:
        await svc.pin_message(message_id)
    except MessageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PinResponse(is_pinned=True)


@router.delete("/{message_id}/pin", response_model=PinResponse)
async def unpin_message(message_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _authorize_message(request, db, message_id, "write")
    svc = SqlAlchemyMessageService(db)
    try:
        await svc.unpin_message(message_id)
    except MessageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PinResponse(is_pinned=False)


@router.get("/search", response_model=list[MessageRead])
async def search_messages(
    request: Request,
    session_id: str = Query(...),
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    await _authorize_session_id(request, db, session_id, "read")
    svc = SqlAlchemyMessageService(db)
    return await svc.search_messages(session_id=session_id, query=q, limit=limit)


@router.post("/{message_id}/artifacts/scan", response_model=ArtifactScanRead)
async def scan_message_artifacts(
    message_id: str,
    request: Request,
    data: ArtifactScanRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    from ..main import _event_bus

    try:
        await _authorize_message(request, db, message_id, "write")
        result = await ArtifactOutputBridge(db, event_bus=_event_bus).scan_message(
            message_id,
            force=bool(data.force) if data else False,
        )
    except MessageNotFoundForScanError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionWithoutProjectError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ArtifactScanRead(
        created=[ArtifactRead.from_orm_with_iso(artifact) for artifact in result.created],
        candidates=[
            ArtifactCandidateRead(
                artifactType=item.artifact_type,
                title=item.title,
                source=item.source,
                confidence=round(item.confidence, 2),
                reason=item.reason,
                contentPreview=item.content[:500],
            )
            for item in result.candidates
        ],
        skipped=[ArtifactSkipRead(**item) for item in result.skipped],
    )


@router.get("/{message_id}", response_model=MessageRead)
async def get_message(message_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    message = await _authorize_message(request, db, message_id, "read")
    return message_to_read(message)
