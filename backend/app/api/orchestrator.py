import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import AgentConfig, Message as DBMessage, Session
from ..services.orchestrator_execution import PlanExecutionError, execution_registry
from ..services.orchestrator_plan_service import (
    OrchestratorPlanNotFoundError,
    OrchestratorPlanService,
)
from ..services.run_service import RunService

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class ExecutePlanBody(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    normalized_plan: dict[str, Any] = Field(..., alias="normalizedPlan")

    model_config = {"populate_by_name": True}


def _plan_svc(db: AsyncSession) -> OrchestratorPlanService:
    from ..main import _event_bus
    return OrchestratorPlanService(db, event_bus=_event_bus)


class ExecutionControlBody(BaseModel):
    reason: str | None = None


@router.post("/plans/execute")
async def execute_orchestrator_plan(
    data: ExecutePlanBody,
    db: AsyncSession = Depends(get_db),
):
    if not data.session_id.strip():
        raise HTTPException(status_code=400, detail="sessionId 不能为空")

    session = await db.get(Session, data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session 不存在")

    active_agent_ids = await _session_worker_ids(db, data.session_id)
    orchestrator_agent_id = await _session_orchestrator_id(db, data.session_id)
    if not orchestrator_agent_id:
        raise HTTPException(status_code=400, detail="群聊缺少项目Leader，无法执行协作计划")
    group_context = await _session_group_context(db, data.session_id)
    try:
        execution = execution_registry.create_execution(
            session_id=data.session_id,
            plan=data.normalized_plan,
            active_agent_ids=active_agent_ids,
            auto_start=False,
            orchestrator_agent_id=orchestrator_agent_id,
            group_context=group_context,
        )
    except PlanExecutionError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "调度计划无法执行",
                "errors": exc.errors,
                "warnings": exc.warnings,
            },
        ) from exc
    run_service = RunService(db)
    run = await run_service.create_run(
        session,
        mode="orchestrator",
        metadata={
            "executionId": execution["executionId"],
            "planId": execution["planId"],
            "source": "orchestrator_execution",
        },
    )
    runtime_task_ids: dict[str, str] = {}
    for task in execution.get("tasks") or []:
        runtime_task = await run_service.create_task(
            run,
            agent_id=task.get("assignedAgentId"),
            name=f"{task.get('taskId')} · {task.get('title')}",
            role="executor",
            phase=task.get("phase"),
            depends_on=task.get("dependsOn") or [],
            metadata={
                "executionId": execution["executionId"],
                "planId": execution["planId"],
                "orchestratorTaskId": task.get("taskId"),
                "maxAttempts": task.get("maxAttempts"),
            },
        )
        runtime_task_ids[str(task.get("taskId"))] = runtime_task.id
    execution_registry.bind_runtime(
        execution["executionId"],
        run_id=run.id,
        task_id_by_orchestrator_task_id=runtime_task_ids,
    )
    persistent_plan = dict(data.normalized_plan)
    persistent_plan.setdefault("planId", execution["planId"])
    await _plan_svc(db).create_or_update_from_normalized_plan(
        session_id=data.session_id,
        normalized_plan=persistent_plan,
        run_id=run.id,
        orchestrator_agent_id=orchestrator_agent_id,
        agent_scope=sorted(active_agent_ids),
    )
    execution_registry.start_execution(execution["executionId"])
    return execution_registry.get_execution(execution["executionId"]) or execution


@router.get("/executions/{execution_id}")
async def get_orchestrator_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
):
    execution = execution_registry.get_execution(execution_id)
    if execution is None:
        execution = await _persisted_execution_snapshot(db, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution 不存在")
    return execution


@router.post("/executions/{execution_id}/interrupt")
async def interrupt_orchestrator_execution(
    execution_id: str,
    data: ExecutionControlBody | None = None,
    db: AsyncSession = Depends(get_db),
):
    execution = execution_registry.get_execution(execution_id)
    if execution is None:
        execution = await _persisted_execution_snapshot(db, execution_id)
        if execution is not None:
            execution_registry.restore_execution(execution)
    execution = await execution_registry.interrupt_execution(
        execution_id,
        reason=(data.reason if data else None),
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution 不存在或无法中断")
    return execution


@router.post("/executions/{execution_id}/resume")
async def resume_orchestrator_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
):
    execution = execution_registry.get_execution(execution_id)
    if execution is None:
        execution = await _persisted_execution_snapshot(db, execution_id)
        if execution is not None:
            if execution.get("status") in {"pending", "running", "cancelling"}:
                execution = execution_registry.interrupted_snapshot(
                    execution,
                    reason="服务重启或页面刷新后恢复执行",
                )
            execution_registry.restore_execution(execution)
    execution = await execution_registry.resume_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution 不存在或无法恢复")
    return execution


@router.post("/executions/{execution_id}/cancel")
async def cancel_orchestrator_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
):
    execution = execution_registry.get_execution(execution_id)
    if execution is None:
        execution = await _persisted_execution_snapshot(db, execution_id)
        if execution is not None:
            execution_registry.restore_execution(execution)
    execution = await execution_registry.cancel_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution 不存在或已不可取消")
    return execution


async def _session_worker_ids(db: AsyncSession, session_id: str) -> set[str]:
    from ..models import SessionMember
    result = await db.execute(
        select(AgentConfig.id)
        .join(SessionMember, SessionMember.agent_config_id == AgentConfig.id)
        .where(
            SessionMember.session_id == session_id,
            AgentConfig.is_active == True,
            or_(
                AgentConfig.primary_skill.is_(None),
                AgentConfig.primary_skill != "orchestrator_planner",
            ),
        )
    )
    return {str(agent_id) for agent_id in result.scalars().all()}


async def _session_orchestrator_id(db: AsyncSession, session_id: str) -> str | None:
    from ..models import SessionMember
    result = await db.execute(
        select(AgentConfig.id)
        .join(SessionMember, SessionMember.agent_config_id == AgentConfig.id)
        .where(
            SessionMember.session_id == session_id,
            AgentConfig.primary_skill == "orchestrator_planner",
            AgentConfig.is_active == True,
        )
        .limit(1)
    )
    value = result.scalars().first()
    return str(value) if value else None


async def _session_group_context(db: AsyncSession, session_id: str) -> list[dict[str, str]]:
    result = await db.execute(
        select(DBMessage)
        .where(DBMessage.session_id == session_id, DBMessage.content_type == "text")
        .order_by(DBMessage.created_at.asc(), DBMessage.id.asc())
    )
    return [
        {"role": message.role, "content": message.content}
        for message in result.scalars().all()
        if message.role in {"user", "assistant", "system"} and (message.content or "").strip()
    ]


async def _persisted_execution_snapshot(db: AsyncSession, execution_id: str) -> dict[str, Any] | None:
    try:
        record = await _plan_svc(db).get_by_execution_id(execution_id)
    except OrchestratorPlanNotFoundError:
        record = None
    if record and record.execution_snapshot_json:
        try:
            persisted = json.loads(record.execution_snapshot_json)
        except json.JSONDecodeError:
            persisted = None
        if isinstance(persisted, dict):
            if persisted.get("status") in {"pending", "running", "cancelling"}:
                return execution_registry.interrupted_snapshot(
                    persisted,
                    reason="服务重启或页面刷新后检测到运行态丢失",
                )
            return persisted
    return None
