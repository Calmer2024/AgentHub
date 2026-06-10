from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.phase10_schemas import SandboxCreate, SandboxRead, SandboxStopRead, SandboxStopRequest
from ..services.quota_service import QuotaExceededError
from ..services.sandbox_service import SandboxNotFoundError, SandboxService, SandboxValidationError
from ..services.team_service import PermissionDeniedError
from .auth import require_current_user

router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])


def _svc(db: AsyncSession) -> SandboxService:
    from ..main import _event_bus
    return SandboxService(db, event_bus=_event_bus)


@router.post("", response_model=SandboxRead, status_code=201)
async def create_sandbox(
    data: SandboxCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return await _svc(db).create_sandbox(data, user)
    except SandboxNotFoundError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except QuotaExceededError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except SandboxValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{sandbox_id}", response_model=SandboxRead)
async def get_sandbox(
    sandbox_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return await _svc(db).get_sandbox(sandbox_id, user)
    except SandboxNotFoundError:
        raise HTTPException(status_code=404, detail="sandbox not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{sandbox_id}/stop", response_model=SandboxStopRead)
async def stop_sandbox(
    sandbox_id: str,
    data: SandboxStopRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        sandbox = await _svc(db).stop_sandbox(sandbox_id, user, reason=data.reason if data else None)
        return SandboxStopRead(id=sandbox.id, status=sandbox.status)
    except SandboxNotFoundError:
        raise HTTPException(status_code=404, detail="sandbox not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
