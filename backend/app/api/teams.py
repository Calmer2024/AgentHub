from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.phase9_schemas import (
    TeamCreate,
    TeamJoinCodeRead,
    TeamJoinRequest,
    TeamListRead,
    TeamMemberCreate,
    TeamMemberListRead,
    TeamMemberRead,
    TeamMemberUpdate,
    TeamRead,
)
from ..services.team_service import (
    PermissionDeniedError,
    TeamConflictError,
    TeamNotFoundError,
    TeamService,
    TeamValidationError,
)
from .auth import require_current_user

router = APIRouter(prefix="/teams", tags=["teams"])


def _svc(db: AsyncSession) -> TeamService:
    from ..main import _event_bus
    return TeamService(db, event_bus=_event_bus)


@router.get("", response_model=TeamListRead)
async def list_teams(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    return TeamListRead(items=await _svc(db).list_teams(user))


@router.post("", response_model=TeamRead, status_code=201)
async def create_team(
    data: TeamCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return await _svc(db).create_team(data.name, user)
    except TeamValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TeamConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/join-by-code", response_model=TeamRead)
async def join_team(
    data: TeamJoinRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return await _svc(db).join_with_code(data.code, user)
    except TeamNotFoundError:
        raise HTTPException(status_code=404, detail="team not found")
    except TeamValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{team_id}/join-code", response_model=TeamJoinCodeRead)
async def get_team_join_code(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return TeamJoinCodeRead(team_id=team_id, code=await _svc(db).join_code(team_id, user))
    except TeamNotFoundError:
        raise HTTPException(status_code=404, detail="team not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{team_id}/members", response_model=TeamMemberRead, status_code=201)
async def add_team_member(
    team_id: str,
    data: TeamMemberCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return await _svc(db).add_member(team_id, data.email, data.role, user)
    except TeamNotFoundError:
        raise HTTPException(status_code=404, detail="team not found")
    except TeamValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TeamConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{team_id}/members", response_model=TeamMemberListRead)
async def list_team_members(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return TeamMemberListRead(items=await _svc(db).list_members(team_id, user))
    except TeamNotFoundError:
        raise HTTPException(status_code=404, detail="team not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.patch("/{team_id}/members/{member_id}", response_model=TeamMemberRead)
async def update_team_member(
    team_id: str,
    member_id: str,
    data: TeamMemberUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return await _svc(db).update_member_role(team_id, member_id, data.role, user)
    except TeamNotFoundError:
        raise HTTPException(status_code=404, detail="team member not found")
    except TeamValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.delete("/{team_id}/members/{member_id}")
async def remove_team_member(
    team_id: str,
    member_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        await _svc(db).remove_member(team_id, member_id, user)
        return {"ok": True}
    except TeamNotFoundError:
        raise HTTPException(status_code=404, detail="team member not found")
    except TeamValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
