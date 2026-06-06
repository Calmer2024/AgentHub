from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services import (
    SessionService, SessionCreate, SessionRead, SessionUpdate, MemberRead,
    SessionNotFoundError, AgentNotFoundError,
)
from ..services.session_service import ProjectNotFoundError

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _svc(db: AsyncSession) -> SessionService:
    return SessionService(db)


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(data: SessionCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).create_session(data)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")


@router.get("", response_model=List[SessionRead])
async def list_sessions(projectId: str | None = None, db: AsyncSession = Depends(get_db)):
    return await _svc(db).list_sessions(projectId)


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await _svc(db).get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/{session_id}/members", response_model=List[MemberRead])
async def list_members(session_id: str, db: AsyncSession = Depends(get_db)):
    return await _svc(db).get_members(session_id)


@router.get("/{session_id}/workspace")
async def get_session_workspace(session_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return {"workspacePath": await _svc(db).get_workspace_path(session_id)}
    except Exception:
        raise HTTPException(status_code=404, detail="workspace not found")


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
