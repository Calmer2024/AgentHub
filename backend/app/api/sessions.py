import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = "新对话"
    agent_name: str = "claude"


class SessionRead(BaseModel):
    id: str
    title: str
    agent_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
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
