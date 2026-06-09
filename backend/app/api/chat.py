import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Project, Session as DBSession
from ..services.chat_service_impl import ChatServiceImpl
from ..services.cloud_agent_runtime import CloudAgentRuntimeService
from ..services.schemas import ChatRequest, MessageRead
from ..services.message_service_sqlalchemy import SqlAlchemyMessageService
from ..agents.cli_runtime import CliProcessNotFound
from ..agents.cli_runtime_registry import cli_runtime_registry
from ..services.auth_service import AuthService
from ..services.team_service import PermissionDeniedError
from ..services.tenant_guard import TenantGuard, tenant_scope_required_for_cloud

router = APIRouter(prefix="", tags=["chat"])
logger = logging.getLogger(__name__)


class InteractiveReplyRequest(BaseModel):
    processId: str
    reply: str


def _chat_svc(db: AsyncSession):
    from ..main import _event_bus
    return ChatServiceImpl(db, event_bus=_event_bus)


async def _authorize_session(
    request: Request,
    db: AsyncSession,
    session: DBSession,
    *,
    mode: str,
):
    project = await db.get(Project, session.project_id) if session.project_id else None
    if not project:
        return None, None
    if project.workspace_mode != "cloud" and not tenant_scope_required_for_cloud():
        return project, None
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
    return project, actor


@router.post("/sessions/{session_id}/chat")
async def chat(
    session_id: str,
    data: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content must not be empty")

    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    project, actor = await _authorize_session(request, db, session, mode="write")
    if project and project.workspace_mode == "cloud":
        from ..main import _event_bus
        runtime = CloudAgentRuntimeService(db, event_bus=_event_bus)
        return StreamingResponse(
            _safe_sse_stream(runtime.stream_chat(
                session_id,
                data.content,
                actor=actor,
                parent_message_id=data.parent_message_id,
                attachment_ids=data.attachment_ids,
            )),
            media_type="text/event-stream",
        )

    svc = _chat_svc(db)
    return StreamingResponse(
        _safe_sse_stream(svc.send_message_stream(
            session_id, data.content, data.mentions,
            parent_message_id=data.parent_message_id,
            chain_config=data.chain_config,
            attachment_ids=data.attachment_ids,
        )),
        media_type="text/event-stream",
    )


@router.get("/sessions/{session_id}/messages", response_model=list[MessageRead])
async def list_messages(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    await _authorize_session(request, db, session, mode="read")
    svc = SqlAlchemyMessageService(db)
    return await svc.get_session_messages(session_id, limit=500)


@router.post("/sessions/{session_id}/interactive_reply")
async def interactive_reply(session_id: str, data: InteractiveReplyRequest):
    if data.reply not in {"y", "n"}:
        raise HTTPException(status_code=400, detail="reply must be 'y' or 'n'")
    try:
        await cli_runtime_registry.reply(data.processId, data.reply)
    except CliProcessNotFound:
        raise HTTPException(status_code=404, detail="process not found")
    return {"status": "acknowledged"}


async def _safe_sse_stream(stream: AsyncIterator[str]) -> AsyncIterator[str]:
    try:
        async for item in stream:
            yield item
    except Exception as exc:
        logger.exception("chat SSE stream failed")
        payload = {
            "type": "error",
            "token": "",
            "done": True,
            "error": f"{type(exc).__name__}: {exc}",
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
