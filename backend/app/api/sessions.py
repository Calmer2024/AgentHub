from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Message, Project, Session as DBSession
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
from ..services.auth_service import AuthService
from ..services.agent_seed import ensure_user_default_cli_agents
from ..services.team_service import PermissionDeniedError
from ..services.tenant_guard import TenantGuard, TenantScope, tenant_scope_required_for_cloud

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _svc(db: AsyncSession, agent_owner_user_id: str | None = None) -> SessionService:
    return SessionService(db, agent_owner_user_id=agent_owner_user_id)


def _agent_owner_id(scope: TenantScope | None) -> str | None:
    if not scope or not tenant_scope_required_for_cloud():
        return None
    return scope.actor_user_id


async def _require_scope(request: Request, db: AsyncSession):
    user = await AuthService(db).resolve_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录后继续")
    return await TenantGuard(db).scope_for_user(user)


async def _authorize_project(
    request: Request,
    db: AsyncSession,
    project_id: str | None,
    mode: str,
) -> TenantScope | None:
    if not project_id:
        if tenant_scope_required_for_cloud():
            raise HTTPException(status_code=400, detail="cloud session requires project")
        return None
    project = await db.get(Project, project_id)
    if not project or project.status == "archived":
        raise HTTPException(status_code=404, detail="project not found")
    if project.workspace_mode != "cloud" and not tenant_scope_required_for_cloud():
        return None
    scope = await _require_scope(request, db)
    guard = TenantGuard(db)
    try:
        if mode == "read":
            await guard.assert_project_read(scope, project)
        else:
            await guard.assert_project_write(scope, project)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    await ensure_user_default_cli_agents(db, scope.actor_user_id)
    return scope


async def _authorize_session(
    request: Request,
    db: AsyncSession,
    session_id: str,
    mode: str,
) -> tuple[DBSession, TenantScope | None]:
    session = await db.get(DBSession, session_id)
    if not session or session.is_active != "1":
        raise HTTPException(status_code=404, detail="session not found")
    scope = await _authorize_project(request, db, session.project_id, mode)
    return session, scope


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(data: SessionCreate, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        scope = await _authorize_project(request, db, data.project_id, "write")
        return await _svc(db, _agent_owner_id(scope)).create_session(data)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("", response_model=List[SessionRead])
async def list_sessions(
    request: Request,
    projectId: str | None = None,
    includeArchived: bool = False,
    db: AsyncSession = Depends(get_db),
):
    if tenant_scope_required_for_cloud():
        scope = await _require_scope(request, db)
        guard = TenantGuard(db)
        if projectId:
            await _authorize_project(request, db, projectId, "read")
            return await _svc(db).list_sessions(projectId, include_archived=includeArchived)
        result = await db.execute(
            select(Project.id).where(Project.status != "archived", guard.visible_project_filter(scope))
        )
        items = []
        for visible_project_id in result.scalars().all():
            items.extend(await _svc(db).list_sessions(str(visible_project_id), include_archived=includeArchived))
        return sorted(items, key=lambda item: item.updated_at, reverse=True)
    return await _svc(db).list_sessions(projectId, include_archived=includeArchived)


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _authorize_session(request, db, session_id, "read")
    session = await _svc(db).get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/{session_id}/members", response_model=List[MemberRead])
async def list_members(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _authorize_session(request, db, session_id, "read")
    return await _svc(db).get_members(session_id)


@router.post("/{session_id}/members", response_model=List[MemberRead])
async def add_member(
    session_id: str,
    data: GroupMemberCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        _session, scope = await _authorize_session(request, db, session_id, "write")
        return await _svc(db, _agent_owner_id(scope)).add_group_member(session_id, data.agent_config_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")
    except SessionModeError:
        raise HTTPException(status_code=400, detail="只有群聊可以管理成员")
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail="agent not found")
    except GroupMemberLimitError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.delete("/{session_id}/members/{agent_config_id}", response_model=List[MemberRead])
async def remove_member(
    session_id: str,
    agent_config_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        _session, scope = await _authorize_session(request, db, session_id, "write")
        return await _svc(db, _agent_owner_id(scope)).remove_group_member(session_id, agent_config_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")
    except SessionModeError:
        raise HTTPException(status_code=400, detail="只有群聊可以管理成员")
    except GroupMemberNotFoundError:
        raise HTTPException(status_code=404, detail="member not found")
    except GroupMemberLimitError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{session_id}/workspace")
async def get_session_workspace(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_session(request, db, session_id, "read")
        return {"workspacePath": await _svc(db).get_workspace_path(session_id)}
    except Exception:
        raise HTTPException(status_code=404, detail="workspace not found")


@router.patch("/{session_id}", response_model=SessionRead)
async def update_session(session_id: str, data: SessionUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        _session, scope = await _authorize_session(request, db, session_id, "write")
        return await _svc(db, _agent_owner_id(scope)).update_session(session_id, data)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")
    except AgentNotFoundError:
        raise HTTPException(status_code=400, detail="Agent 不存在")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{session_id}/read", response_model=SessionRead)
async def mark_session_read(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_session(request, db, session_id, "read")
        return await _svc(db).mark_read(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")


@router.post("/forward", response_model=ForwardMessagesResult, status_code=201)
async def forward_messages(data: ForwardMessagesRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        source_result = await db.execute(
            select(DBSession)
            .join(Message, Message.session_id == DBSession.id)
            .where(DBSession.is_active == "1", Message.id.in_(data.message_ids))
        )
        source_session_ids = [session.id for session in source_result.scalars().unique().all()]
        for session_id in source_session_ids:
            await _authorize_session(request, db, session_id, "read")
        for session_id in data.target_session_ids:
            await _authorize_session(request, db, session_id, "write")
        return await _svc(db).forward_messages(data)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="target session not found")
    except MessageNotForwardableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_session(request, db, session_id, "write")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    ok = await _svc(db).delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}
