import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession, AgentConfig, SessionMember

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
        select(DBSession).order_by(DBSession.updated_at.desc())
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
    agent_config_id: str | None = Field(None, alias="agentConfigId")

    model_config = {"populate_by_name": True}


@router.patch("/{session_id}", response_model=SessionRead)
async def update_session(session_id: str, data: SessionUpdate, db: AsyncSession = Depends(get_db)):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    if data.agent_config_id is not None:
        agent = await db.get(AgentConfig, data.agent_config_id)
        if not agent:
            raise HTTPException(status_code=400, detail="Agent 不存在")
        session.agent_config_id = data.agent_config_id

    await db.commit()
    await db.refresh(session)
    return session
