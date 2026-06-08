"""Phase 8 Orchestrator 计划持久化与审批续跑状态机。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..event_bus.event_types import EventType
from ..models import OrchestratorPlanRecord, Session as DBSession
from .phase8_schemas import OrchestratorPlanRead, OrchestratorPlanStepRead


TERMINAL_PLAN_STATUSES = {"completed", "failed", "cancelled"}


class OrchestratorPlanNotFoundError(LookupError):
    pass


class InvalidOrchestratorPlanStateError(ValueError):
    pass


class OrchestratorPlanService:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus

    async def create_or_update_from_normalized_plan(
        self,
        *,
        session_id: str,
        normalized_plan: dict[str, Any],
        run_id: str | None = None,
    ) -> OrchestratorPlanRecord:
        session = await self.db.get(DBSession, session_id)
        if not session:
            raise OrchestratorPlanNotFoundError("session not found")
        plan_id = str(normalized_plan.get("plan_id") or normalized_plan.get("planId") or uuid.uuid4())
        steps = _steps_from_plan(normalized_plan)
        record = await self.db.get(OrchestratorPlanRecord, plan_id)
        now = china_now()
        if record:
            record.steps_json = json.dumps(steps, ensure_ascii=False)
            record.status = _status_from_steps(steps, default=record.status)
            record.current_step_id = _current_step_id(steps)
            record.run_id = run_id or record.run_id
            record.updated_at = now
        else:
            record = OrchestratorPlanRecord(
                id=plan_id,
                session_id=session_id,
                status=_status_from_steps(steps, default="draft"),
                steps_json=json.dumps(steps, ensure_ascii=False),
                current_step_id=_current_step_id(steps),
                run_id=run_id,
                created_at=now,
                updated_at=now,
            )
            self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get(self, plan_id: str) -> OrchestratorPlanRecord:
        record = await self.db.get(OrchestratorPlanRecord, plan_id)
        if not record:
            raise OrchestratorPlanNotFoundError(plan_id)
        return record

    async def resume(
        self,
        plan_id: str,
        *,
        approval_id: str | None = None,
        message: str | None = None,
    ) -> OrchestratorPlanRecord:
        record = await self.get(plan_id)
        if record.status in TERMINAL_PLAN_STATUSES:
            raise InvalidOrchestratorPlanStateError("plan is terminal")
        steps = _loads_steps(record.steps_json)
        if not steps:
            raise InvalidOrchestratorPlanStateError("plan has no steps")
        current_id = record.current_step_id or _first_resumable_step_id(steps)
        if not current_id:
            raise InvalidOrchestratorPlanStateError("plan has no resumable step")
        for step in steps:
            if step.get("id") == current_id and step.get("status") in {"waiting_approval", "paused", "pending"}:
                step["status"] = "running"
                step["approvalId"] = approval_id
                if message:
                    step["resumeMessage"] = message.strip()
                break
        record.steps_json = json.dumps(steps, ensure_ascii=False)
        record.status = "running"
        record.current_step_id = current_id
        record.updated_at = china_now()
        await self.db.commit()
        await self.db.refresh(record)
        await self._publish(EventType.ORCHESTRATOR_PLAN_RESUMED, {
            "planId": record.id,
            "sessionId": record.session_id,
            "resumedFromStepId": current_id,
            "approvalId": approval_id,
        })
        return record

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)


def plan_to_read(record: OrchestratorPlanRecord) -> OrchestratorPlanRead:
    steps = _loads_steps(record.steps_json)
    return OrchestratorPlanRead(
        id=record.id,
        session_id=record.session_id,
        status=record.status,
        current_step_id=record.current_step_id,
        steps=[
            OrchestratorPlanStepRead(
                id=str(step.get("id") or ""),
                title=str(step.get("title") or step.get("id") or "未命名步骤"),
                agent_id=step.get("agentId") if isinstance(step.get("agentId"), str) else None,
                status=str(step.get("status") or "pending"),
            )
            for step in steps
        ],
    )


def _steps_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw_tasks = plan.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    steps: list[dict[str, Any]] = []
    for index, task in enumerate(raw_tasks):
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id") or task.get("taskId") or f"step-{index + 1}")
        needs_approval = bool(task.get("needs_approval") or task.get("needsApproval"))
        steps.append({
            "id": task_id,
            "title": str(task.get("title") or task_id),
            "agentId": task.get("assigned_agent_id") or task.get("assignedAgentId"),
            "status": "waiting_approval" if needs_approval else "pending",
            "dependsOn": task.get("depends_on") or task.get("dependsOn") or [],
            "needsApproval": needs_approval,
        })
    return steps


def _loads_steps(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _status_from_steps(steps: list[dict[str, Any]], *, default: str) -> str:
    if not steps:
        return default
    if any(step.get("status") in {"waiting_approval", "paused"} for step in steps):
        return "waiting_approval"
    if any(step.get("status") == "running" for step in steps):
        return "running"
    if all(step.get("status") == "completed" for step in steps):
        return "completed"
    return default


def _current_step_id(steps: list[dict[str, Any]]) -> str | None:
    return _first_resumable_step_id(steps) or (
        str(steps[0].get("id")) if steps and steps[0].get("id") else None
    )


def _first_resumable_step_id(steps: list[dict[str, Any]]) -> str | None:
    for step in steps:
        if step.get("status") in {"waiting_approval", "paused", "pending", "running"}:
            return str(step.get("id"))
    return None
