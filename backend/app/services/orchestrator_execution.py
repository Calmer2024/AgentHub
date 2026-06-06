"""Thin execution registry for approved Orchestrator plans.

This is the first bridge from a chat-rendered draft plan to a backend-owned
execution object. It intentionally does not start CLI agents yet.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from ..domain.orchestrator_plan import normalize_plan, validate_plan


class PlanExecutionError(ValueError):
    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        super().__init__("调度计划无法创建执行对象")
        self.errors = errors
        self.warnings = warnings or []


class OrchestratorExecutionRegistry:
    def __init__(self):
        self._executions: dict[str, dict[str, Any]] = {}

    def create_execution(
        self,
        *,
        session_id: str,
        plan: dict[str, Any],
        active_agent_ids: set[str],
    ) -> dict[str, Any]:
        normalized = normalize_plan(plan)
        validation = validate_plan(normalized, active_agent_ids)
        readiness_errors = self._validate_execution_readiness(normalized, active_agent_ids)
        errors = list(validation["errors"]) + readiness_errors
        if errors:
            raise PlanExecutionError(errors, validation["warnings"])

        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        tasks = [
            self._task_snapshot(task)
            for task in normalized.get("tasks", [])
            if isinstance(task, dict)
        ]
        execution = {
            "executionId": execution_id,
            "sessionId": session_id,
            "planId": normalized.get("plan_id"),
            "status": "pending",
            "createdAt": now,
            "updatedAt": now,
            "plan": copy.deepcopy(normalized),
            "tasks": tasks,
            "validation": {
                "ok": True,
                "errors": [],
                "warnings": validation["warnings"],
            },
        }
        self._executions[execution_id] = execution
        return copy.deepcopy(execution)

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        execution = self._executions.get(execution_id)
        return copy.deepcopy(execution) if execution else None

    @staticmethod
    def _validate_execution_readiness(plan: dict[str, Any], active_agent_ids: set[str]) -> list[str]:
        errors: list[str] = []
        for task in plan.get("tasks", []):
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("task_id"))
            assigned_agent_id = task.get("assigned_agent_id")
            if not assigned_agent_id:
                errors.append(f"{task_id} 缺少 assigned_agent_id，无法执行")
                continue
            if str(assigned_agent_id) not in active_agent_ids:
                errors.append(f"{task_id}.assigned_agent_id 不存在或未启用: {assigned_agent_id}")
        return errors

    @staticmethod
    def _task_snapshot(task: dict[str, Any]) -> dict[str, Any]:
        return {
            "taskId": str(task.get("task_id")),
            "title": str(task.get("title") or task.get("task_id")),
            "goal": str(task.get("goal") or ""),
            "status": "pending",
            "assignedAgentId": task.get("assigned_agent_id"),
            "assignedAgentName": task.get("assigned_agent_name"),
            "dependsOn": list(task.get("depends_on") or []),
            "requiredSkills": list(task.get("required_skills") or []),
            "needsApproval": bool(task.get("needs_approval")),
            "isBlocking": bool(task.get("is_blocking")),
            "expectedOutputs": list(task.get("expected_outputs") or []),
            "acceptanceCriteria": list(task.get("acceptance_criteria") or []),
        }


execution_registry = OrchestratorExecutionRegistry()
