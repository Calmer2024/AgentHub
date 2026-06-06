from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession
from ..services.run_service import RunNotFoundError, RunService, run_to_read
from ..services.runtime_schemas import ProcessRead, RunRead, TaskRead

router = APIRouter(prefix="", tags=["runs"])


class CancelRunRequest(BaseModel):
    reason: str | None = None


def _run_service(db: AsyncSession):
    from ..main import _event_bus
    return RunService(db, event_bus=_event_bus)


@router.get("/sessions/{session_id}/runs", response_model=list[RunRead])
async def list_session_runs(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return await _run_service(db).list_runs(session_id)


@router.get("/runs/{run_id}", response_model=RunRead)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return run_to_read(await _run_service(db).get_run(run_id))
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="run not found")


@router.post("/runs/{run_id}/cancel", response_model=RunRead)
async def cancel_run(
    run_id: str,
    data: CancelRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await _run_service(db).cancel_run(run_id, (data.reason if data else None))
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="run not found")
    return run_to_read(run)


@router.get("/runs/{run_id}/tasks", response_model=list[TaskRead])
async def list_run_tasks(run_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await _run_service(db).list_tasks(run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="run not found")


@router.get("/runs/{run_id}/processes", response_model=list[ProcessRead])
async def list_run_processes(run_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await _run_service(db).list_processes(run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="run not found")
