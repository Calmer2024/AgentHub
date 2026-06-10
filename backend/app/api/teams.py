from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.phase9_schemas import TeamCreate, TeamListRead, TeamMemberCreate, TeamMemberRead, TeamRead
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
