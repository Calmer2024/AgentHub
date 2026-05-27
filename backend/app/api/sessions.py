from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services import (
    SessionService, SessionCreate, SessionRead, SessionUpdate, MemberRead,
    SessionNotFoundError, AgentNotFoundError,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _svc(db: AsyncSession) -> SessionService:
    return SessionService(db)


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(data: SessionCreate, db: AsyncSession = Depends(get_db)):
    return await _svc(db).create_session(data)


@router.get("", response_model=List[SessionRead])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    return await _svc(db).list_sessions()


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await _svc(db).get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/{session_id}/members", response_model=List[MemberRead])
async def list_members(session_id: str, db: AsyncSession = Depends(get_db)):
    return await _svc(db).get_members(session_id)


@router.patch("/{session_id}", response_model=SessionRead)
async def update_session(session_id: str, data: SessionUpdate, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).update_session(session_id, data)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")
    except AgentNotFoundError:
        raise HTTPException(status_code=400, detail="Agent 不存在")


@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    ok = await _svc(db).delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}


@router.post("/{session_id}/summarize", response_model=SessionRead)
async def summarize_session(session_id: str, db: AsyncSession = Depends(get_db)):
    svc = _svc(db)
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        title = await svc.generate_title(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await svc.get_session(session_id)
