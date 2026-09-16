"""Orchestrator 计划与执行快照的唯一持久化服务。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.timezone import china_now
from ..models import OrchestratorPlanRecord, Session as DBSession


class OrchestratorPlanNotFoundError(LookupError):
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
        orchestrator_agent_id: str | None = None,
        agent_scope: list[str] | None = None,
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
            record.normalized_plan_json = json.dumps(normalized_plan, ensure_ascii=False)
            record.orchestrator_agent_id = orchestrator_agent_id or record.orchestrator_agent_id
            if agent_scope is not None:
                record.agent_scope_json = json.dumps(agent_scope, ensure_ascii=False)
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
                normalized_plan_json=json.dumps(normalized_plan, ensure_ascii=False),
                agent_scope_json=json.dumps(agent_scope or [], ensure_ascii=False),
                orchestrator_agent_id=orchestrator_agent_id,
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

    async def get_by_execution_id(self, execution_id: str) -> OrchestratorPlanRecord:
        result = await self.db.execute(
            select(OrchestratorPlanRecord).where(
                OrchestratorPlanRecord.execution_id == execution_id,
            )
        )
        record = result.scalars().first()
        if not record:
            raise OrchestratorPlanNotFoundError(execution_id)
        return record

    async def latest_draft(self, session_id: str) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(OrchestratorPlanRecord)
            .where(
                OrchestratorPlanRecord.session_id == session_id,
                OrchestratorPlanRecord.status == "draft",
            )
            .order_by(OrchestratorPlanRecord.updated_at.desc(), OrchestratorPlanRecord.id.desc())
            .limit(1)
        )
        record = result.scalars().first()
        if not record or not record.normalized_plan_json:
            return None
        try:
            plan = json.loads(record.normalized_plan_json)
        except json.JSONDecodeError:
            return None
        return plan if isinstance(plan, dict) else None

    async def latest_execution_snapshot(self, session_id: str) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(OrchestratorPlanRecord)
            .where(
                OrchestratorPlanRecord.session_id == session_id,
                OrchestratorPlanRecord.execution_snapshot_json.is_not(None),
            )
            .order_by(OrchestratorPlanRecord.updated_at.desc(), OrchestratorPlanRecord.id.desc())
            .limit(1)
        )
        record = result.scalars().first()
        if not record or not record.execution_snapshot_json:
            return None
        try:
            snapshot = json.loads(record.execution_snapshot_json)
        except json.JSONDecodeError:
            return None
        return snapshot if isinstance(snapshot, dict) else None

    async def update_status(self, plan_id: str, status: str) -> None:
        record = await self.get(plan_id)
        record.status = status
        if record.normalized_plan_json:
            try:
                plan = json.loads(record.normalized_plan_json)
            except json.JSONDecodeError:
                plan = None
            if isinstance(plan, dict):
                plan["status"] = status
                record.normalized_plan_json = json.dumps(plan, ensure_ascii=False)
        record.updated_at = china_now()
        await self.db.commit()

    async def persist_execution_snapshot(self, execution: dict[str, Any]) -> None:
        record = await self.get(str(execution.get("planId") or ""))
        record.execution_id = str(execution.get("executionId") or "") or None
        record.execution_snapshot_json = json.dumps(execution, ensure_ascii=False)
        record.status = str(execution.get("status") or record.status)
        record.steps_json = json.dumps([
            {
                "id": task.get("taskId"),
                "title": task.get("title"),
                "agentId": task.get("assignedAgentId"),
                "status": task.get("status"),
                "dependsOn": task.get("dependsOn") or [],
            }
            for task in execution.get("tasks") or []
        ], ensure_ascii=False)
        record.run_id = str(execution.get("runId") or "") or record.run_id
        record.updated_at = china_now()
        await self.db.commit()

def _steps_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw_tasks = plan.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    steps: list[dict[str, Any]] = []
    for index, task in enumerate(raw_tasks):
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id") or task.get("taskId") or f"step-{index + 1}")
        steps.append({
            "id": task_id,
            "title": str(task.get("title") or task_id),
            "agentId": task.get("assigned_agent_id") or task.get("assignedAgentId"),
            "status": "pending",
            "dependsOn": task.get("depends_on") or task.get("dependsOn") or [],
        })
    return steps


def _status_from_steps(steps: list[dict[str, Any]], *, default: str) -> str:
    if not steps:
        return default
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
        if step.get("status") in {"paused", "pending", "running"}:
            return str(step.get("id"))
    return None
