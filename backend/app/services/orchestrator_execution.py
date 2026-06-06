"""Execution registry for approved Orchestrator plans.

This bridge owns backend execution state for a chat-rendered draft plan. The
current scheduler is deliberately simulated: it verifies DAG topology and state
transitions without starting real CLI agents yet.
"""

from __future__ import annotations

import asyncio
import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..domain.orchestrator_plan import normalize_plan, validate_plan
from ..models import AgentConfig, Message as DBMessage, Session as DBSession
from ..agents.cli_trace import trace_text
from .cli_agent_service import CliAgentService
from .execution_trace import ExecutionTraceBuilder, merge_trace_metadata
from .session_service import SessionService
from .streaming_text import iter_stream_pieces


class PlanExecutionError(ValueError):
    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        super().__init__("调度计划无法创建执行对象")
        self.errors = errors
        self.warnings = warnings or []


class TaskRunner(Protocol):
    async def run(
        self,
        task: dict[str, Any],
        execution: dict[str, Any],
        upstream_results: list[dict[str, Any]],
    ) -> str:
        """Run one scheduled task and return its user-visible summary."""


class MockTaskRunner:
    def __init__(self, delay_seconds: float = 0.12):
        self.delay_seconds = delay_seconds

    async def run(
        self,
        task: dict[str, Any],
        execution: dict[str, Any],
        upstream_results: list[dict[str, Any]],
    ) -> str:
        await asyncio.sleep(self.delay_seconds)
        agent = task.get("assignedAgentName") or task.get("assignedAgentId") or "未分配 Agent"
        skills = ", ".join(task.get("requiredSkills") or []) or "none"
        return f"{task['taskId']} 已完成：模拟执行 {agent} / required_skills={skills}"


class CliTaskRunner:
    def __init__(self, session_factory: Callable[[], AsyncSession]):
        self._session_factory = session_factory

    async def run(
        self,
        task: dict[str, Any],
        execution: dict[str, Any],
        upstream_results: list[dict[str, Any]],
    ) -> str:
        agent_id = task.get("assignedAgentId")
        if not agent_id:
            raise RuntimeError(f"{task['taskId']} 缺少 assignedAgentId")

        async with self._session_factory() as db:
            agent = await db.get(AgentConfig, agent_id)
            session = await db.get(DBSession, execution["sessionId"])
            if not agent or not agent.is_active:
                raise RuntimeError(f"{task['taskId']} 分配的 Agent 不存在或未启用: {agent_id}")
            if not session:
                raise RuntimeError(f"Session 不存在: {execution['sessionId']}")
            workspace_path = await SessionService(db).get_workspace_path(execution["sessionId"])

        message_id = f"msg_agent_{uuid.uuid4().hex[:12]}"
        task["visibleMessageId"] = message_id
        await _broadcast_ws(execution["sessionId"], {
            "type": "agent.start",
            "sessionId": execution["sessionId"],
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "role": "executor",
            "phase": task.get("phase"),
            "task": task["title"],
            "callKey": _call_key(agent.id, task),
        })

        visible = ""
        raw_output = ""
        process_id = ""
        exit_code = None
        metadata: dict[str, Any] = {
            "agentType": agent.agent_type or "cli_wrapper",
            "cliTool": agent.cli_tool or "custom",
            "workspacePath": workspace_path,
        }
        trace = ExecutionTraceBuilder(
            agent_name=agent.name,
            cli_tool=agent.cli_tool or "custom",
            workspace_path=workspace_path,
        )
        async for event in CliAgentService().stream(
            agent=agent,
            session_id=execution["sessionId"],
            workspace_path=workspace_path,
            messages=[{"role": "user", "content": self._task_prompt(execution, task, upstream_results)}],
            system_prompt=agent.system_prompt or "",
        ):
            process_id = event.process_id or process_id
            if event.type == "agent.process.started":
                metadata["processId"] = process_id
                trace.set_process(process_id)
                item = trace.add(
                    kind="process",
                    text=trace_text(event.trace or {}, f"正在启动 {agent.name}"),
                    process_id=process_id,
                    trace=event.trace,
                )
                if item:
                    await self._broadcast_trace(execution, task, agent, message_id, process_id, item)
                await _broadcast_ws(execution["sessionId"], {
                    "type": "agent.process.started",
                    "sessionId": execution["sessionId"],
                    "agentId": agent.id,
                    "agentName": agent.name,
                    "messageId": message_id,
                    "processId": process_id,
                    "callKey": _call_key(agent.id, task),
                    "role": "executor",
                    "phase": task.get("phase"),
                    "task": task["title"],
                    "token": "",
                    "done": False,
                })
                continue

            if event.type == "agent.output":
                raw_output += event.chunk
                if event.chunk_type in {"text", "artifact_signal"}:
                    visible += event.chunk
                if event.chunk_type != "text":
                    if event.chunk_type == "artifact_signal":
                        kind = "artifact"
                    elif event.chunk_type == "error":
                        kind = "error"
                    else:
                        kind = "progress"
                    item = trace.add(
                        kind=kind,
                        text=event.chunk,
                        source="cli",
                        chunk_type=event.chunk_type,
                        process_id=process_id,
                        trace=event.trace,
                    )
                    if item:
                        await self._broadcast_trace(execution, task, agent, message_id, process_id, item)
                if event.chunk_type == "text":
                    for token in iter_stream_pieces(event.chunk):
                        await _broadcast_ws(execution["sessionId"], {
                            "type": "agent.output",
                            "sessionId": execution["sessionId"],
                            "agentId": agent.id,
                            "agentName": agent.name,
                            "messageId": message_id,
                            "processId": process_id,
                            "callKey": _call_key(agent.id, task),
                            "role": "executor",
                            "phase": task.get("phase"),
                            "task": task["title"],
                            "chunk": token,
                            "chunkType": "text",
                            "token": token,
                            "done": False,
                        })
                continue

            if event.type == "agent.process.completed":
                exit_code = event.exit_code
                metadata["exitCode"] = exit_code
                status = "completed" if exit_code in (0, None) else "error"
                item = trace.add(
                    kind="process",
                    text=trace_text(event.trace or {}, f"{agent.name} 已结束"),
                    process_id=process_id,
                    trace=event.trace,
                )
                trace.complete(status=status, exit_code=exit_code)
                if item:
                    await self._broadcast_trace(execution, task, agent, message_id, process_id, item)
                await _broadcast_ws(execution["sessionId"], {
                    "type": "agent.process.completed",
                    "sessionId": execution["sessionId"],
                    "agentId": agent.id,
                    "agentName": agent.name,
                    "messageId": message_id,
                    "processId": process_id,
                    "callKey": _call_key(agent.id, task),
                    "role": "executor",
                    "phase": task.get("phase"),
                    "task": task["title"],
                    "exitCode": exit_code,
                    "token": "",
                    "done": False,
                })
                continue

            if event.type in {"agent.process.timeout", "error"}:
                error = event.error or f"{agent.name} 执行失败"
                item = trace.add(
                    kind="error",
                    text=error,
                    process_id=process_id,
                    trace=event.trace,
                )
                trace.complete(status="error", exit_code=exit_code)
                metadata["error"] = error
                if item:
                    await self._broadcast_trace(execution, task, agent, message_id, process_id, item)
                await self._persist_visible_message(
                    execution,
                    task,
                    agent,
                    message_id,
                    visible.strip() or f"CLI Agent 执行失败：{error}",
                    merge_trace_metadata(metadata, trace),
                )
                await _broadcast_ws(execution["sessionId"], {
                    "type": "message.completed",
                    "sessionId": execution["sessionId"],
                    "messageId": message_id,
                })
                raise RuntimeError(event.error or f"{agent.name} 执行失败")

        if exit_code not in (0, None):
            error = f"{agent.name} 执行失败，exitCode={exit_code}"
            trace.complete(status="error", exit_code=exit_code)
            metadata["error"] = error
            await self._persist_visible_message(
                execution,
                task,
                agent,
                message_id,
                visible.strip() or f"CLI Agent 执行失败：{error}",
                merge_trace_metadata(metadata, trace),
            )
            await _broadcast_ws(execution["sessionId"], {
                "type": "message.completed",
                "sessionId": execution["sessionId"],
                "messageId": message_id,
            })
            raise RuntimeError(error)

        content = visible.strip() or raw_output.strip() or f"{task['taskId']} 已完成，但没有可见输出。"
        await self._persist_visible_message(
            execution,
            task,
            agent,
            message_id,
            content,
            merge_trace_metadata(metadata, trace),
        )
        await _broadcast_ws(execution["sessionId"], {
            "type": "message.completed",
            "sessionId": execution["sessionId"],
            "messageId": message_id,
        })
        return _summary_text(content)

    async def _persist_visible_message(
        self,
        execution: dict[str, Any],
        task: dict[str, Any],
        agent: AgentConfig,
        message_id: str,
        content: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        metadata = {
            "orchestratorTaskMessage": {
                "executionId": execution["executionId"],
                "planId": execution["planId"],
                "taskId": task["taskId"],
                "title": task["title"],
                "runnerType": "cli",
                "upstreamResults": task.get("upstreamResults") or [],
            }
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        async with self._session_factory() as db:
            session = await db.get(DBSession, execution["sessionId"])
            db.add(DBMessage(
                id=message_id,
                session_id=execution["sessionId"],
                role="assistant",
                content=content,
                content_type="text",
                agent_name=agent.name,
                source_type="agent",
                source_id=agent.id,
                source_name=agent.name,
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            ))
            if session:
                session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()

    async def _broadcast_trace(
        self,
        execution: dict[str, Any],
        task: dict[str, Any],
        agent: AgentConfig,
        message_id: str,
        process_id: str,
        item: dict[str, Any],
    ) -> None:
        await _broadcast_ws(execution["sessionId"], {
            "type": "agent.trace.delta",
            "sessionId": execution["sessionId"],
            "agentId": agent.id,
            "agentName": agent.name,
            "cliTool": agent.cli_tool or "custom",
            "messageId": message_id,
            "processId": process_id,
            "callKey": _call_key(agent.id, task),
            "role": "executor",
            "phase": task.get("phase"),
            "task": task["title"],
            "item": item,
            "token": "",
            "done": False,
        })

    @staticmethod
    def _task_prompt(
        execution: dict[str, Any],
        task: dict[str, Any],
        upstream_results: list[dict[str, Any]],
    ) -> str:
        plan = execution.get("plan") or {}
        upstream = "\n".join(
            f"- {item.get('taskId')}: {item.get('summary') or ''}"
            for item in upstream_results
        ) or "- 无"
        return (
            "你正在作为 AgentHub 调度任务中的专家 Agent 执行一个 DAG 节点。\n"
            "请完成当前任务，输出可以直接给用户阅读和给下游任务复用的结果。\n\n"
            f"Plan ID: {execution.get('planId')}\n"
            f"当前任务 ID: {task.get('taskId')}\n"
            f"当前任务标题: {task.get('title')}\n"
            f"当前任务目标: {task.get('goal')}\n"
            f"所需能力: {', '.join(task.get('requiredSkills') or []) or '未声明'}\n"
            f"期望输出: {', '.join(task.get('expectedOutputs') or []) or '未声明'}\n"
            f"验收标准: {', '.join(task.get('acceptanceCriteria') or []) or '未声明'}\n\n"
            "上游任务结果:\n"
            f"{upstream}\n\n"
            "完整计划 JSON:\n"
            f"{json.dumps(plan, ensure_ascii=False, indent=2)}"
        )


class OrchestratorExecutionRegistry:
    def __init__(
        self,
        task_runner: TaskRunner | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
    ):
        self._executions: dict[str, dict[str, Any]] = {}
        self._task_runner = task_runner or MockTaskRunner()
        self._session_factory = session_factory or AsyncSessionLocal
        self._cli_runner = CliTaskRunner(self._session_factory)

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
            "status": "running",
            "createdAt": now,
            "updatedAt": now,
            "startedAt": now,
            "completedAt": None,
            "plan": copy.deepcopy(normalized),
            "tasks": tasks,
            "events": [{
                "type": "execution_created",
                "status": "pending",
                "timestamp": now,
                "message": f"创建执行 {execution_id}，{len(tasks)} 个任务进入 pending 队列。",
            }, {
                "type": "execution_running",
                "status": "running",
                "timestamp": now,
                "message": "模拟 Scheduler 已启动。",
            }],
            "validation": {
                "ok": True,
                "errors": [],
                "warnings": validation["warnings"],
            },
        }
        self._executions[execution_id] = execution
        self._start_background_scheduler(execution_id)
        return copy.deepcopy(execution)

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        execution = self._executions.get(execution_id)
        return copy.deepcopy(execution) if execution else None

    def _start_background_scheduler(self, execution_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._run_scheduler(execution_id))
            return
        loop.create_task(self._run_scheduler(execution_id))

    async def _run_scheduler(self, execution_id: str) -> None:
        execution = self._executions.get(execution_id)
        if execution is None:
            return
        tasks = execution["tasks"]
        pending = {task["taskId"] for task in tasks}
        completed: set[str] = set()
        task_by_id = {task["taskId"]: task for task in tasks}

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
            execution["updatedAt"] = running_at
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
                task["upstreamResults"] = self._upstream_results_for(task, task_by_id)
                task["runnerType"] = self._runner_type_for(execution)
                if task["runnerType"] == "cli":
                    execution["cliTaskCount"] = int(execution.get("cliTaskCount") or 0) + 1
                task["status"] = "running"
                task["phase"] = phase
                task["startedAt"] = running_at
                task["updatedAt"] = running_at
                execution["events"].append({
                    "type": "task_started",
                    "status": "running",
                    "timestamp": running_at,
                    "phase": phase,
                    "taskId": task_id,
                    "message": f"{task_id} 开始执行：{task.get('title')}",
                })

            try:
                summaries = await asyncio.gather(*[
                    self._run_task(task_by_id[task_id], execution)
                    for task_id in ready
                ])
            except Exception as exc:
                failed_at = self._now()
                execution["status"] = "failed"
                execution["updatedAt"] = failed_at
                execution["events"].append({
                    "type": "execution_failed",
                    "status": "failed",
                    "timestamp": failed_at,
                    "phase": phase,
                    "taskIds": ready,
                    "message": f"模拟 Scheduler 执行失败：{exc}",
                })
                for task_id in ready:
                    task = task_by_id[task_id]
                    task["status"] = "failed"
                    task["updatedAt"] = failed_at
                return
            completed_at = self._now()
            execution["updatedAt"] = completed_at
            for task_id, summary in zip(ready, summaries):
                task = task_by_id[task_id]
                task["status"] = "completed"
                task["completedAt"] = completed_at
                task["updatedAt"] = completed_at
                task["summary"] = summary
                task["resultMessageId"] = await self._persist_task_result(execution, task, summary)
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

    async def _persist_task_result(
        self,
        execution: dict[str, Any],
        task: dict[str, Any],
        summary: str,
    ) -> str:
        message_id = f"msg_task_{uuid.uuid4().hex[:12]}"
        metadata = {
            "orchestratorTaskResult": {
                "executionId": execution["executionId"],
                "planId": execution["planId"],
                "taskId": task["taskId"],
                "title": task["title"],
                "status": task["status"],
                "summary": summary,
                "runnerType": task.get("runnerType") or "mock",
                "visibleMessageId": task.get("visibleMessageId"),
                "assignedAgentId": task.get("assignedAgentId"),
                "assignedAgentName": task.get("assignedAgentName"),
                "dependsOn": task.get("dependsOn") or [],
                "requiredSkills": task.get("requiredSkills") or [],
                "upstreamResults": task.get("upstreamResults") or [],
            }
        }
        async with self._session_factory() as db:
            db.add(DBMessage(
                id=message_id,
                session_id=execution["sessionId"],
                role="system",
                content=summary,
                content_type="orchestrator_task_result",
                agent_name=task.get("assignedAgentName"),
                source_type="system",
                source_id=task.get("assignedAgentId"),
                source_name="Scheduler",
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            ))
            await db.commit()
        return message_id

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
            "resultMessageId": None,
            "visibleMessageId": None,
            "runnerType": "mock",
            "upstreamResults": [],
            "assignedAgentId": task.get("assigned_agent_id"),
            "assignedAgentName": task.get("assigned_agent_name"),
            "dependsOn": list(task.get("depends_on") or []),
            "requiredSkills": list(task.get("required_skills") or []),
            "needsApproval": bool(task.get("needs_approval")),
            "isBlocking": bool(task.get("is_blocking")),
            "expectedOutputs": list(task.get("expected_outputs") or []),
            "acceptanceCriteria": list(task.get("acceptance_criteria") or []),
        }

    async def _run_task(self, task: dict[str, Any], execution: dict[str, Any]) -> str:
        runner = self._cli_runner if task.get("runnerType") == "cli" else self._task_runner
        return await runner.run(task, execution, task.get("upstreamResults") or [])

    @staticmethod
    def _runner_type_for(execution: dict[str, Any]) -> str:
        if int(execution.get("cliTaskCount") or 0) < int(execution.get("cliTaskLimit") or 1):
            return "cli"
        return "mock"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _upstream_results_for(
        task: dict[str, Any],
        task_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results = []
        for dep_id in task.get("dependsOn") or []:
            upstream = task_by_id.get(dep_id)
            if not upstream:
                continue
            results.append({
                "taskId": upstream["taskId"],
                "title": upstream.get("title"),
                "summary": upstream.get("summary"),
                "resultMessageId": upstream.get("resultMessageId"),
                "assignedAgentId": upstream.get("assignedAgentId"),
                "assignedAgentName": upstream.get("assignedAgentName"),
            })
        return results


execution_registry = OrchestratorExecutionRegistry()


def _call_key(agent_id: str, task: dict[str, Any]) -> str:
    return f"{agent_id}:{task.get('phase') if task.get('phase') is not None else 0}:{task.get('taskId')}"


def _summary_text(content: str, limit: int = 1200) -> str:
    clean = content.strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "\n...(已截断，完整内容见 Agent 消息)"


async def _broadcast_ws(session_id: str, payload: dict[str, Any]) -> None:
    try:
        from ..api.ws_manager import manager as ws_manager
        await ws_manager.broadcast(session_id, payload)
    except Exception:
        pass
