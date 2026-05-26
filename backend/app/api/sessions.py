import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession, AgentConfig

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = "新对话"
    agent_config_id: str | None = Field(None, alias="agentConfigId")

    model_config = {"populate_by_name": True}


class SessionRead(BaseModel):
    id: str
    title: str
    agent_config_id: str | None = Field(None, alias="agentConfigId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(data: SessionCreate, db: AsyncSession = Depends(get_db)):
    agent_config_id = data.agent_config_id
    if not agent_config_id:
        result = await db.execute(select(AgentConfig).where(AgentConfig.is_active == True).limit(1))
        default_agent = result.scalars().first()
        if default_agent:
            agent_config_id = default_agent.id

    session = DBSession(
        id=str(uuid.uuid4()),
        title=data.title,
        agent_config_id=agent_config_id,
    )
    db.add(session)
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
