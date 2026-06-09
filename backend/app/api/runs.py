from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as DBSession
from ..services.cloud_agent_runtime import CloudAgentRuntimeService, CloudRunNotFoundError, CloudRuntimeError
from ..services.orchestrator_execution import execution_registry
from ..services.phase10_schemas import RuntimeLogsRead, SessionRunCreate, SessionRunQueuedRead
from ..services.run_service import RunNotFoundError, RunService, run_to_read
from ..services.runtime_schemas import ProcessRead, RunRead, TaskRead
from .auth import require_user_from_header_values

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


@router.post("/sessions/{session_id}/runs", response_model=SessionRunQueuedRead, status_code=202)
async def create_session_run(
    session_id: str,
    data: SessionRunCreate,
    stream: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    x_agenthub_user_email: str | None = Header(default=None),
    x_agenthub_user_name: str | None = Header(default=None),
    x_agenthub_user_avatar: str | None = Header(default=None),
):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    from ..main import _event_bus
    runtime = CloudAgentRuntimeService(db, event_bus=_event_bus)
    if data.runtime == "local":
        return await runtime.create_local_placeholder_run(session_id, data)

    actor = await require_user_from_header_values(
        db,
        x_agenthub_user_email,
        display_name=x_agenthub_user_name,
        avatar_url=x_agenthub_user_avatar,
    )
    if stream:
        return StreamingResponse(
            runtime.stream_existing_message(session_id, data, actor=actor),
            media_type="text/event-stream",
        )
    try:
        return await runtime.run_existing_message(session_id, data, actor=actor)
    except CloudRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
        from ..main import _event_bus
        cloud_run = await CloudAgentRuntimeService(db, event_bus=_event_bus).cancel_cloud_run(
            run_id,
            (data.reason if data else None),
        )
        run = cloud_run or await _run_service(db).cancel_run(run_id, (data.reason if data else None))
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="run not found")
    execution_registry.mark_cancelled_by_run(
        run_id,
        reason=(data.reason if data else None) or "用户通过运行控制停止当前调度执行。",
    )
    return run_to_read(run)


@router.get("/runs/{run_id}/logs", response_model=RuntimeLogsRead)
async def get_run_logs(run_id: str, db: AsyncSession = Depends(get_db)):
    from ..main import _event_bus
    try:
        return await CloudAgentRuntimeService(db, event_bus=_event_bus).get_logs(run_id)
    except CloudRunNotFoundError:
        raise HTTPException(status_code=404, detail="runtime run not found")


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
