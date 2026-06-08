import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import AgentConfig, Message as DBMessage, Session
from ..services.orchestrator_execution import PlanExecutionError, execution_registry
from ..services.orchestrator_plan_service import (
    InvalidOrchestratorPlanStateError,
    OrchestratorPlanNotFoundError,
    OrchestratorPlanService,
    plan_to_read,
)
from ..services.phase8_schemas import OrchestratorPlanRead, OrchestratorPlanResumeRequest
from ..services.run_service import RunService

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class ExecutePlanBody(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    normalized_plan: dict[str, Any] = Field(..., alias="normalizedPlan")

    model_config = {"populate_by_name": True}


def _plan_svc(db: AsyncSession) -> OrchestratorPlanService:
    from ..main import _event_bus
    return OrchestratorPlanService(db, event_bus=_event_bus)


class ConfirmTaskBody(BaseModel):
    note: str | None = None


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

    active_agent_ids = await _active_agent_ids(db)
    try:
        execution = execution_registry.create_execution(
            session_id=data.session_id,
            plan=data.normalized_plan,
            active_agent_ids=active_agent_ids,
            auto_start=False,
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
                "requiresHumanApproval": bool(task.get("needsApproval")),
                "approvalTitle": f"确认 {task.get('title') or task.get('taskId')}",
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
    )
    execution_registry.start_execution(execution["executionId"])
    return execution_registry.get_execution(execution["executionId"]) or execution


@router.post("/plans/{plan_id}/resume", response_model=OrchestratorPlanRead)
async def resume_orchestrator_plan(
    plan_id: str,
    data: OrchestratorPlanResumeRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        record = await _plan_svc(db).resume(
            plan_id,
            approval_id=data.approval_id,
            message=data.message,
        )
        return plan_to_read(record)
    except OrchestratorPlanNotFoundError:
        raise HTTPException(status_code=404, detail="Plan 不存在")
    except InvalidOrchestratorPlanStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


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


@router.post("/executions/{execution_id}/cancel")
async def cancel_orchestrator_execution(execution_id: str):
    execution = await execution_registry.cancel_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution 不存在或已不可取消")
    return execution


@router.post("/executions/{execution_id}/tasks/{task_id}/confirm")
async def confirm_orchestrator_waiting_task(
    execution_id: str,
    task_id: str,
    data: ConfirmTaskBody | None = None,
):
    execution = await execution_registry.confirm_waiting_task(
        execution_id,
        task_id,
        note=data.note if data else None,
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="等待用户确认的任务不存在")
    return execution


async def _active_agent_ids(db: AsyncSession) -> set[str]:
    result = await db.execute(select(AgentConfig.id).where(AgentConfig.is_active == True))
    return {str(agent_id) for agent_id in result.scalars().all()}


async def _persisted_execution_snapshot(db: AsyncSession, execution_id: str) -> dict[str, Any] | None:
    result = await db.execute(
        select(DBMessage)
        .where(DBMessage.metadata_json.like(f"%{execution_id}%"))
        .order_by(DBMessage.created_at.desc(), DBMessage.id.desc())
        .limit(20)
    )
    for message in result.scalars().all():
        try:
            metadata = json.loads(message.metadata_json or "{}")
        except json.JSONDecodeError:
            continue
        execution = metadata.get("orchestratorExecution")
        if isinstance(execution, dict) and execution.get("executionId") == execution_id:
            return execution
    return None
