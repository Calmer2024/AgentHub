import json
import uuid
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession, Message as DBMessage
from ..agents import ClaudeAdapter
from ..agents.deepseek_adapter import DeepSeekAdapter
from ..config import settings

router = APIRouter(prefix="", tags=["chat"])

agent = None
if settings.deepseek_api_key:
    agent = DeepSeekAdapter()
elif settings.anthropic_api_key:
    agent = ClaudeAdapter()


class ChatRequest(BaseModel):
    content: str


async def generate_chat_stream(
    session_id: str,
    user_content: str,
    db: AsyncSession,
    session: DBSession,
) -> AsyncGenerator[str, None]:
    if not agent:
        yield f"data: {json.dumps({'token': '', 'done': True, 'error': '没有配置 API Key，请在 .env 中设置 DEEPSEEK_API_KEY 或 ANTHROPIC_API_KEY'}, ensure_ascii=False)}\n\n"
        return

    user_msg_id = str(uuid.uuid4())
    user_msg = DBMessage(
        id=user_msg_id,
        session_id=session_id,
        role="user",
        content=user_content,
    )
    db.add(user_msg)
    await db.commit()

    result = await db.execute(
        select(DBMessage)
        .where(DBMessage.session_id == session_id)
        .order_by(DBMessage.created_at.asc())
        .limit(50)
    )
    history_messages = result.scalars().all()

    messages_for_llm = [
        {"role": m.role, "content": m.content}
        for m in history_messages
    ]

    assistant_msg_id = str(uuid.uuid4())
    full_response = ""

    try:
        async for token in agent.chat_stream(
            messages=messages_for_llm,
            system_prompt="你是一个有帮助的 AI 助手。请用简洁清晰的方式回答用户的问题。",
        ):
            full_response += token
            yield f"data: {json.dumps({'token': token, 'done': False}, ensure_ascii=False)}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'token': '', 'done': True, 'error': str(e)}, ensure_ascii=False)}\n\n"
        return

    assistant_msg = DBMessage(
        id=assistant_msg_id,
        session_id=session_id,
        role="assistant",
        content=full_response,
    )
    db.add(assistant_msg)

    from datetime import datetime, timezone
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()

    yield f"data: {json.dumps({'token': '', 'done': True, 'message_id': assistant_msg_id}, ensure_ascii=False)}\n\n"


@router.post("/sessions/{session_id}/chat")
async def chat(
    session_id: str,
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content must not be empty")

    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    return StreamingResponse(
        generate_chat_stream(session_id, data.content, db, session),
        media_type="text/event-stream",
    )


@router.get("/sessions/{session_id}/messages")
async def list_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DBMessage)
        .where(DBMessage.session_id == session_id)
        .order_by(DBMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "sessionId": m.session_id,
            "role": m.role,
            "content": m.content,
            "createdAt": m.created_at.isoformat(),
        }
        for m in messages
    ]
