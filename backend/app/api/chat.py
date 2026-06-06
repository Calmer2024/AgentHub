import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession
from ..services.chat_service_impl import ChatServiceImpl
from ..services.schemas import ChatRequest, MessageRead
from ..services.message_service_sqlalchemy import SqlAlchemyMessageService
from ..agents.cli_runtime import CliProcessNotFound, cli_process_manager

router = APIRouter(prefix="", tags=["chat"])
logger = logging.getLogger(__name__)


class InteractiveReplyRequest(BaseModel):
    processId: str
    reply: str


def _chat_svc(db: AsyncSession):
    from ..main import _event_bus
    return ChatServiceImpl(db, event_bus=_event_bus)


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, data: ChatRequest, db: AsyncSession = Depends(get_db)):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content must not be empty")

    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    svc = _chat_svc(db)
    return StreamingResponse(
        _safe_sse_stream(svc.send_message_stream(
            session_id, data.content, data.mentions,
            parent_message_id=data.parent_message_id,
            chain_config=data.chain_config,
        )),
        media_type="text/event-stream",
    )


@router.get("/sessions/{session_id}/messages", response_model=list[MessageRead])
async def list_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    svc = SqlAlchemyMessageService(db)
    return await svc.get_session_messages(session_id, limit=500)


@router.post("/sessions/{session_id}/interactive_reply")
async def interactive_reply(session_id: str, data: InteractiveReplyRequest):
    if data.reply not in {"y", "n"}:
        raise HTTPException(status_code=400, detail="reply must be 'y' or 'n'")
    try:
        await cli_process_manager.reply(data.processId, data.reply)
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
