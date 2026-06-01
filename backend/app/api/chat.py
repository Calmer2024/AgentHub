import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession, Message as DBMessage
from ..services.chat_service_impl import ChatServiceImpl
from ..services.schemas import ChatRequest, ChainConfigSchema

router = APIRouter(prefix="", tags=["chat"])


class MessageRead(BaseModel):
    id: str
    session_id: str = Field(alias="sessionId")
    role: str
    content: str
    agent_name: str | None = Field(None, alias="agentName")
    created_at: str = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


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
        svc.send_message_stream(
            session_id, data.content, data.mentions,
            parent_message_id=data.parent_message_id,
            chain_config=data.chain_config,
        ),
        media_type="text/event-stream",
    )


@router.get("/sessions/{session_id}/messages", response_model=List[MessageRead])
async def list_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DBMessage)
        .where(DBMessage.session_id == session_id)
        .order_by(DBMessage.created_at.asc())
    )
    return [MessageRead(
        id=m.id, session_id=m.session_id, role=m.role, content=m.content,
        agent_name=m.agent_name,
        created_at=m.created_at.isoformat() if m.created_at else "",
    ) for m in result.scalars().all()]
