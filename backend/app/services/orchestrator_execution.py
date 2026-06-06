"""Execution registry for approved Orchestrator plans.

This bridge owns backend execution state for a chat-rendered draft plan. The
current scheduler is deliberately simulated: it verifies DAG topology and state
transitions without starting real CLI agents yet.
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
            "startedAt": None,
            "completedAt": None,
            "plan": copy.deepcopy(normalized),
            "tasks": tasks,
            "events": [{
                "type": "execution_created",
                "status": "pending",
                "timestamp": now,
                "message": f"创建执行 {execution_id}，{len(tasks)} 个任务进入 pending 队列。",
            }],
            "validation": {
                "ok": True,
                "errors": [],
                "warnings": validation["warnings"],
            },
        }
        self._run_simulated_scheduler(execution)
        self._executions[execution_id] = execution
        return copy.deepcopy(execution)

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        execution = self._executions.get(execution_id)
        return copy.deepcopy(execution) if execution else None

    def _run_simulated_scheduler(self, execution: dict[str, Any]) -> None:
        tasks = execution["tasks"]
        pending = {task["taskId"] for task in tasks}
        completed: set[str] = set()
        task_by_id = {task["taskId"]: task for task in tasks}

        start = self._now()
        execution["status"] = "running"
        execution["startedAt"] = start
        execution["updatedAt"] = start
        execution["events"].append({
            "type": "execution_running",
            "status": "running",
            "timestamp": start,
            "message": "模拟 Scheduler 已启动。",
        })

        phase = 0
        while pending:
            ready = sorted(
                task_id
                for task_id in pending
                if all(dep in completed for dep in task_by_id[task_id]["dependsOn"])
            )
            if not ready:
                failed_at = self._now()
                execution["status"] = "failed"
                execution["updatedAt"] = failed_at
                execution["events"].append({
                    "type": "execution_failed",
                    "status": "failed",
                    "timestamp": failed_at,
                    "message": "模拟 Scheduler 无法找到可运行任务，请检查 DAG 依赖。",
                    "remainingTaskIds": sorted(pending),
                })
                return

            running_at = self._now()
            execution["events"].append({
                "type": "scheduler_batch_running",
                "status": "running",
                "timestamp": running_at,
                "phase": phase,
                "taskIds": ready,
                "message": f"第 {phase + 1} 层任务进入 running：{', '.join(ready)}",
            })
            for task_id in ready:
                task = task_by_id[task_id]
                task["status"] = "running"
                task["startedAt"] = running_at
                task["updatedAt"] = running_at

            completed_at = self._now()
            for task_id in ready:
                task = task_by_id[task_id]
                summary = self._simulated_summary(task)
                task["status"] = "completed"
                task["completedAt"] = completed_at
                task["updatedAt"] = completed_at
                task["summary"] = summary
                execution["events"].append({
                    "type": "task_completed",
                    "status": "completed",
                    "timestamp": completed_at,
                    "phase": phase,
                    "taskId": task_id,
                    "message": summary,
                })
                pending.remove(task_id)
                completed.add(task_id)

            phase += 1

        completed_at = self._now()
        execution["status"] = "completed"
        execution["completedAt"] = completed_at
        execution["updatedAt"] = completed_at
        execution["events"].append({
            "type": "execution_completed",
            "status": "completed",
            "timestamp": completed_at,
            "message": "模拟 Scheduler 已按 DAG 完成全部任务。",
        })

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
            "startedAt": None,
            "completedAt": None,
            "updatedAt": None,
            "summary": None,
            "assignedAgentId": task.get("assigned_agent_id"),
            "assignedAgentName": task.get("assigned_agent_name"),
            "dependsOn": list(task.get("depends_on") or []),
            "requiredSkills": list(task.get("required_skills") or []),
            "needsApproval": bool(task.get("needs_approval")),
            "isBlocking": bool(task.get("is_blocking")),
            "expectedOutputs": list(task.get("expected_outputs") or []),
            "acceptanceCriteria": list(task.get("acceptance_criteria") or []),
        }

    @staticmethod
    def _simulated_summary(task: dict[str, Any]) -> str:
        agent = task.get("assignedAgentName") or task.get("assignedAgentId") or "未分配 Agent"
        skills = ", ".join(task.get("requiredSkills") or []) or "none"
        return f"{task['taskId']} 已完成：模拟执行 {agent} / required_skills={skills}"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


execution_registry = OrchestratorExecutionRegistry()
