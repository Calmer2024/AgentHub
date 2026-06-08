from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.context_pack_service import (
    ContextPackNotFoundError,
    ContextPackService,
    ContextPackValidationError,
)
from ..services.phase8_schemas import ContextPackPreviewRead

router = APIRouter(tags=["context-pack"])


def _svc(db: AsyncSession) -> ContextPackService:
    from ..main import _event_bus
    return ContextPackService(db, event_bus=_event_bus)


@router.get("/sessions/{session_id}/context-pack", response_model=ContextPackPreviewRead)
async def get_session_context_pack(
    session_id: str,
    purpose: str = "send",
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _svc(db).preview(session_id, purpose=purpose)
    except ContextPackNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")
    except ContextPackValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
