import json
import uuid
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession, Message as DBMessage, AgentConfig
from ..agents.registry import agent_registry
from ..domain.orchestrator import orchestrator
from .ws_manager import manager as ws_manager

router = APIRouter(prefix="", tags=["chat"])


class ChatRequest(BaseModel):
    content: str
    mentions: list[str] | None = None


async def generate_chat_stream(
    session_id: str,
    user_content: str,
    mentions: list[str] | None,
    db: AsyncSession,
    session: DBSession,
) -> AsyncGenerator[str, None]:
    user_msg_id = str(uuid.uuid4())
    db.add(DBMessage(id=user_msg_id, session_id=session_id, role="user", content=user_content))
    await db.commit()

    result = await db.execute(
        select(DBMessage).where(DBMessage.session_id == session_id)
        .order_by(DBMessage.created_at.asc()).limit(50)
    )
    history = [{"role": m.role, "content": m.content} for m in result.scalars().all()]

    if session.mode == "group":
        targets = await orchestrator.route(session_id, mentions, db)
        if not targets:
            msg = "没有合适的 Agent 处理此请求，请尝试 @ 指定 Agent"
            yield f"data: {json.dumps({'token': '', 'done': True, 'error': msg}, ensure_ascii=False)}\n\n"
            return

        async def invoke_one(agent: AgentConfig):
            aid = str(uuid.uuid4())
            full = ""
            try:
                adapter = agent_registry.get_adapter(agent.provider)
                async for token in adapter.chat_stream(messages=history, system_prompt=agent.system_prompt, model=agent.model or None):
                    full += token
                    yield f"data: {json.dumps({'token': token, 'agentId': agent.id, 'agentName': agent.name, 'done': False}, ensure_ascii=False)}\n\n"
            except Exception as e:
                err = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                full = f"[{agent.name} 错误: {err}]"
                yield f"data: {json.dumps({'token': full, 'agentId': agent.id, 'agentName': agent.name, 'done': False}, ensure_ascii=False)}\n\n"
            db.add(DBMessage(id=aid, session_id=session_id, role="assistant", content=f"[{agent.name}]: {full}"))
            await db.commit()
            yield f"data: {json.dumps({'token': '', 'agentId': agent.id, 'agentName': agent.name, 'done': True, 'messageId': aid}, ensure_ascii=False)}\n\n"

        async for event in _merge_streams([invoke_one(a) for a in targets[:5]]):
            yield event
        return

    # 单聊模式
    agent_config = None
    if session.agent_config_id:
        agent_config = await db.get(AgentConfig, session.agent_config_id)
    if not agent_config:
        yield f"data: {json.dumps({'token': '', 'done': True, 'error': '会话未关联 Agent'}, ensure_ascii=False)}\n\n"
        return

    adapter = agent_registry.get_adapter(agent_config.provider)
    if not adapter or not agent_registry.is_available(agent_config.provider):
        yield f"data: {json.dumps({'token': '', 'done': True, 'error': f'供应商 {agent_config.provider} 不可用'}, ensure_ascii=False)}\n\n"
        return

    assistant_msg_id = str(uuid.uuid4())
    full_response = ""

    try:
        async for token in adapter.chat_stream(messages=history, system_prompt=agent_config.system_prompt, model=agent_config.model or None):
            full_response += token
            yield f"data: {json.dumps({'token': token, 'done': False}, ensure_ascii=False)}\n\n"
            await ws_manager.broadcast(session_id, {"type": "token", "token": token, "messageId": assistant_msg_id})
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        yield f"data: {json.dumps({'token': '', 'done': True, 'error': err_msg}, ensure_ascii=False)}\n\n"
        return

    db.add(DBMessage(id=assistant_msg_id, session_id=session_id, role="assistant", content=full_response))
    from datetime import datetime, timezone
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await ws_manager.broadcast(session_id, {"type": "message.completed", "messageId": assistant_msg_id})
    yield f"data: {json.dumps({'token': '', 'done': True, 'messageId': assistant_msg_id}, ensure_ascii=False)}\n\n"


async def _merge_streams(generators):
    """并发执行多个异步生成器，按 token 到达顺序交错输出。"""
    import asyncio
    queue: asyncio.Queue = asyncio.Queue()
    done_count = 0
    total = 0

    async def run(gen):
        nonlocal done_count
        async for item in gen:
            await queue.put(item)
        done_count += 1
        if done_count >= total:
            await queue.put(None)

    gens = list(generators)
    total = len(gens)
    tasks = [asyncio.create_task(run(g)) for g in gens]

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item

    for t in tasks:
        t.cancel()


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, data: ChatRequest, db: AsyncSession = Depends(get_db)):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content must not be empty")

    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    return StreamingResponse(
        generate_chat_stream(session_id, data.content, data.mentions, db, session),
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
    return [{
        "id": m.id, "sessionId": m.session_id,
        "role": m.role, "content": m.content,
        "createdAt": m.created_at.isoformat(),
    } for m in messages]
