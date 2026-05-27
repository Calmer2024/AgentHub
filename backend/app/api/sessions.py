import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession, AgentConfig, SessionMember, Message

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = "新对话"
    agent_config_id: str | None = Field(None, alias="agentConfigId")
    mode: str = "single"
    agent_config_ids: list[str] | None = Field(None, alias="agentConfigIds")

    model_config = {"populate_by_name": True}


class SessionRead(BaseModel):
    id: str
    title: str
    agent_config_id: str | None = Field(None, alias="agentConfigId")
    mode: str = "single"
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class MemberRead(BaseModel):
    agent_config_id: str = Field(alias="agentConfigId")
    agent_name: str = Field(alias="agentName")
    joined_at: datetime = Field(alias="joinedAt")

    model_config = {"populate_by_name": True}


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(data: SessionCreate, db: AsyncSession = Depends(get_db)):
    is_group = data.mode == "group" and data.agent_config_ids and len(data.agent_config_ids) >= 2

    session = DBSession(
        id=str(uuid.uuid4()),
        title=data.title,
        agent_config_id=data.agent_config_ids[0] if is_group and data.agent_config_ids else None,
        mode="group" if is_group else "single",
    )

    if is_group:
        agent_config_id = data.agent_config_ids[0]
        session.agent_config_id = agent_config_id
    elif data.agent_config_id:
        agent_config_id = data.agent_config_id
    else:
        result = await db.execute(select(AgentConfig).where(AgentConfig.is_active == True).limit(1))
        default_agent = result.scalars().first()
        agent_config_id = default_agent.id if default_agent else None

    session.agent_config_id = agent_config_id
    db.add(session)

    if is_group and data.agent_config_ids:
        for aid in data.agent_config_ids[:5]:
            db.add(SessionMember(session_id=session.id, agent_config_id=aid))

    await db.commit()
    await db.refresh(session)
    return session


@router.get("", response_model=List[SessionRead])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DBSession).where(DBSession.is_active == "1").order_by(DBSession.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/{session_id}/members", response_model=List[MemberRead])
async def list_members(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SessionMember, AgentConfig).join(
            AgentConfig, SessionMember.agent_config_id == AgentConfig.id
        ).where(SessionMember.session_id == session_id)
    )
    members = []
    for sm, agent in result.all():
        members.append(MemberRead(
            agent_config_id=sm.agent_config_id,
            agent_name=agent.name,
            joined_at=sm.joined_at,
        ))
    return members


class SessionUpdate(BaseModel):
    title: str | None = None
    agent_config_id: str | None = Field(None, alias="agentConfigId")

    model_config = {"populate_by_name": True}


@router.patch("/{session_id}", response_model=SessionRead)
async def update_session(session_id: str, data: SessionUpdate, db: AsyncSession = Depends(get_db)):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    if data.title is not None:
        session.title = data.title
    if data.agent_config_id is not None:
        agent = await db.get(AgentConfig, data.agent_config_id)
        if not agent:
            raise HTTPException(status_code=400, detail="Agent 不存在")
        session.agent_config_id = data.agent_config_id

    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    session.is_active = "0"
    await db.commit()
    return {"ok": True}


@router.post("/{session_id}/summarize", response_model=SessionRead)
async def summarize_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at.desc()).limit(3)
    )
    msgs = list(result.scalars().all())
    if not msgs:
        raise HTTPException(status_code=400, detail="无消息可总结")

    agent_config = None
    if session.agent_config_id:
        agent_config = await db.get(AgentConfig, session.agent_config_id)
    if not agent_config:
        result2 = await db.execute(select(AgentConfig).where(AgentConfig.is_active == True).limit(1))
        agent_config = result2.scalars().first()
    if not agent_config:
        raise HTTPException(status_code=400, detail="无可用 Agent")

    from ..agents.registry import agent_registry
    adapter = agent_registry.get_adapter(agent_config.provider)
    if not adapter:
        raise HTTPException(status_code=400, detail="Agent 不可用")

    history = [{"role": m.role, "content": m.content} for m in reversed(msgs)]
    history.append({"role": "user", "content": "请用不超过10个字总结以上对话内容，只输出总结文本。"})

    title = ""
    async for token in adapter.chat_stream(messages=history, system_prompt="你是一个标题生成器。", model=agent_config.model or None):
        title += token

    session.title = title.strip()[:20] or "新对话"
    await db.commit()
    await db.refresh(session)
    return session
