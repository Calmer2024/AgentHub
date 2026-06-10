from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Project, Run, Session as DBSession
from ..services.cloud_agent_runtime import CloudAgentRuntimeService, CloudRunNotFoundError, CloudRuntimeError
from ..services.orchestrator_execution import execution_registry
from ..services.phase10_schemas import RuntimeLogsRead, SessionRunCreate, SessionRunQueuedRead
from ..services.run_service import RunNotFoundError, RunService, run_to_read
from ..services.runtime_schemas import ProcessRead, RunRead, TaskRead
from ..services.auth_service import AuthService
from ..services.team_service import PermissionDeniedError
from ..services.tenant_guard import TenantGuard, tenant_scope_required_for_cloud

router = APIRouter(prefix="", tags=["runs"])


class CancelRunRequest(BaseModel):
    reason: str | None = None


def _run_service(db: AsyncSession):
    from ..main import _event_bus
    return RunService(db, event_bus=_event_bus)


async def _authorize_project(request: Request, db: AsyncSession, project: Project | None, mode: str):
    if not project:
        return None
    if project.workspace_mode != "cloud" and not tenant_scope_required_for_cloud():
        return None
    actor = await AuthService(db).resolve_request(request)
    if not actor:
        raise HTTPException(status_code=401, detail="请先登录后继续")
    scope = await TenantGuard(db).scope_for_user(actor)
    guard = TenantGuard(db)
    try:
        if mode == "read":
            await guard.assert_project_read(scope, project)
        else:
            await guard.assert_project_write(scope, project)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return actor


async def _authorize_session(request: Request, db: AsyncSession, session_id: str, mode: str):
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    project = await db.get(Project, session.project_id) if session.project_id else None
    actor = await _authorize_project(request, db, project, mode)
    return session, project, actor


async def _authorize_run(request: Request, db: AsyncSession, run_id: str, mode: str):
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    if run.project_id:
        project = await db.get(Project, run.project_id)
        await _authorize_project(request, db, project, mode)
    else:
        await _authorize_session(request, db, run.session_id, mode)
    return run


@router.get("/sessions/{session_id}/runs", response_model=list[RunRead])
async def list_session_runs(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _authorize_session(request, db, session_id, "read")
    return await _run_service(db).list_runs(session_id)


@router.post("/sessions/{session_id}/runs", response_model=SessionRunQueuedRead, status_code=202)
async def create_session_run(
    session_id: str,
    data: SessionRunCreate,
    request: Request,
    stream: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    _session, _project, actor = await _authorize_session(request, db, session_id, "write")
    from ..main import _event_bus
    runtime = CloudAgentRuntimeService(db, event_bus=_event_bus)
    if data.runtime == "local":
        return await runtime.create_local_placeholder_run(session_id, data)

    if not actor:
        raise HTTPException(status_code=401, detail="请先登录后继续")
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
async def get_run(run_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_run(request, db, run_id, "read")
        return run_to_read(await _run_service(db).get_run(run_id))
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="run not found")


@router.post("/runs/{run_id}/cancel", response_model=RunRead)
async def cancel_run(
    run_id: str,
    request: Request,
    data: CancelRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_run(request, db, run_id, "write")
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
async def get_run_logs(run_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from ..main import _event_bus
    try:
        await _authorize_run(request, db, run_id, "read")
        return await CloudAgentRuntimeService(db, event_bus=_event_bus).get_logs(run_id)
    except CloudRunNotFoundError:
        raise HTTPException(status_code=404, detail="runtime run not found")


@router.get("/runs/{run_id}/tasks", response_model=list[TaskRead])
async def list_run_tasks(run_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_run(request, db, run_id, "read")
        return await _run_service(db).list_tasks(run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="run not found")


@router.get("/runs/{run_id}/processes", response_model=list[ProcessRead])
async def list_run_processes(run_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_run(request, db, run_id, "read")
        return await _run_service(db).list_processes(run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="run not found")
