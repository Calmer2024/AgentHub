"""Phase 4 message action and search endpoints."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Message as DBMessage
from ..services.message_service_sqlalchemy import (
    InvalidMessageOperationError,
    MessageNotFoundError,
    SqlAlchemyMessageService,
    message_to_read,
)
from ..services.schemas import MessageCreate, MessageRead

router = APIRouter(prefix="/messages", tags=["messages"])


class ReplyRequest(BaseModel):
    content: str


class PinResponse(BaseModel):
    is_pinned: bool = Field(alias="isPinned")

    model_config = {"populate_by_name": True}


@router.post("/{message_id}/reply", response_model=MessageRead, status_code=201)
async def reply_to_message(
    message_id: str,
    data: ReplyRequest,
    db: AsyncSession = Depends(get_db),
):
    parent = await db.get(DBMessage, message_id)
    if not parent:
        raise HTTPException(status_code=404, detail="message not found")
    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="content must not be empty")

    svc = SqlAlchemyMessageService(db)
    try:
        return await svc.reply_to_message(
            MessageCreate(sessionId=parent.session_id, role="user", content=content),
            parent_message_id=message_id,
        )
    except InvalidMessageOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{message_id}/regenerate")
async def regenerate_message(
    message_id: str,
    db: AsyncSession = Depends(get_db),
):
    svc = SqlAlchemyMessageService(db)

    async def events() -> AsyncIterator[str]:
        async for item in svc.regenerate_message(message_id):
            yield item

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/{message_id}/pin", response_model=PinResponse)
async def pin_message(message_id: str, db: AsyncSession = Depends(get_db)):
    svc = SqlAlchemyMessageService(db)
    try:
        await svc.pin_message(message_id)
    except MessageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PinResponse(is_pinned=True)


@router.delete("/{message_id}/pin", response_model=PinResponse)
async def unpin_message(message_id: str, db: AsyncSession = Depends(get_db)):
    svc = SqlAlchemyMessageService(db)
    try:
        await svc.unpin_message(message_id)
    except MessageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PinResponse(is_pinned=False)


@router.get("/search", response_model=list[MessageRead])
async def search_messages(
    session_id: str = Query(...),
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    svc = SqlAlchemyMessageService(db)
    return await svc.search_messages(session_id=session_id, query=q, limit=limit)


@router.get("/{message_id}", response_model=MessageRead)
async def get_message(message_id: str, db: AsyncSession = Depends(get_db)):
    message = await db.get(DBMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message not found")
    return message_to_read(message)
