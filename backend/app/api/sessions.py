import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession
from ..agents.registry import agent_registry

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = "新对话"
    agent_name: str = Field("claude", alias="agentName")

    model_config = {"populate_by_name": True}


class SessionRead(BaseModel):
    id: str
    title: str
    agent_name: str = Field(alias="agentName")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    if data.agent_name not in agent_registry.get_agent_names():
        raise HTTPException(status_code=400, detail=f"unknown agent: {data.agent_name}")

    new_session = DBSession(
        id=str(uuid.uuid4()),
        title=data.title,
        agent_name=data.agent_name,
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return new_session


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
    agent_name: str | None = Field(None, alias="agentName")

    model_config = {"populate_by_name": True}


@router.patch("/{session_id}", response_model=SessionRead)
async def update_session(
    session_id: str,
    data: SessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    if data.agent_name is not None:
        if data.agent_name not in agent_registry.get_agent_names():
            raise HTTPException(status_code=400, detail=f"unknown agent: {data.agent_name}")
        session.agent_name = data.agent_name

    await db.commit()
    await db.refresh(session)
    return session
