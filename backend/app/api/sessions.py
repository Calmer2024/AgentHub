from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession
from ..services import (
    SessionService, SessionCreate, SessionRead, SessionUpdate, MemberRead, GroupMemberCreate,
    SessionNotFoundError, AgentNotFoundError, ForwardMessagesRequest,
    ForwardMessagesResult,
)
from ..services.session_service import (
    GroupMemberLimitError,
    GroupMemberNotFoundError,
    MessageNotForwardableError,
    ProjectNotFoundError,
    SessionModeError,
)
from ..services.group_dialog_state import GroupDialogStateService

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CloseGroupDialogBody(BaseModel):
    reason: str = "user_closed"


def _svc(db: AsyncSession) -> SessionService:
    return SessionService(db)


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(data: SessionCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).create_session(data)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")


@router.get("", response_model=List[SessionRead])
async def list_sessions(
    projectId: str | None = None,
    includeArchived: bool = False,
    db: AsyncSession = Depends(get_db),
):
    return await _svc(db).list_sessions(projectId, include_archived=includeArchived)


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await _svc(db).get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/{session_id}/members", response_model=List[MemberRead])
async def list_members(session_id: str, db: AsyncSession = Depends(get_db)):
    return await _svc(db).get_members(session_id)


@router.post("/{session_id}/members", response_model=List[MemberRead])
async def add_member(
    session_id: str,
    data: GroupMemberCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _svc(db).add_group_member(session_id, data.agent_config_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")
    except SessionModeError:
        raise HTTPException(status_code=400, detail="只有群聊可以管理成员")
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail="agent not found")
    except GroupMemberLimitError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{session_id}/members/{agent_config_id}", response_model=List[MemberRead])
async def remove_member(
    session_id: str,
    agent_config_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _svc(db).remove_group_member(session_id, agent_config_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")
    except SessionModeError:
        raise HTTPException(status_code=400, detail="只有群聊可以管理成员")
    except GroupMemberNotFoundError:
        raise HTTPException(status_code=404, detail="member not found")
    except GroupMemberLimitError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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


@router.post("/{session_id}/read", response_model=SessionRead)
async def mark_session_read(session_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).mark_read(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")


@router.post("/{session_id}/group-dialog/close")
async def close_group_dialog(
    session_id: str,
    data: CloseGroupDialogBody | None = None,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session.mode != "group":
        raise HTTPException(status_code=400, detail="只有群聊可以结束直接对齐")
    state = await GroupDialogStateService(db).close_active(
        session,
        reason=data.reason if data else "user_closed",
    )
    if state is None:
        return {"ok": True, "closed": False}
    return {
        "ok": True,
        "closed": True,
        "dialog": {
            **state.to_metadata(),
            "status": "closed",
            "closedReason": data.reason if data else "user_closed",
        },
    }


@router.post("/forward", response_model=ForwardMessagesResult, status_code=201)
async def forward_messages(data: ForwardMessagesRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).forward_messages(data)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="target session not found")
    except MessageNotForwardableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    ok = await _svc(db).delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}
