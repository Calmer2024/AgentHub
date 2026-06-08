"""Execution registry for approved Orchestrator plans.

This bridge owns backend execution state for a chat-rendered draft plan. The
current scheduler advances the DAG and can run a limited number of tasks through
real CLI agents while simulating the rest.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.cli_runtime_registry import cli_runtime_registry
from ..database import AsyncSessionLocal
from ..domain.orchestrator_plan import normalize_plan, validate_plan
from ..models import AgentConfig, Message as DBMessage, Session as DBSession
from ..agents.cli_trace import trace_text
from .cli_agent_service import CliAgentService
from .execution_trace import ExecutionTraceBuilder, merge_trace_metadata
from .run_service import RunService, run_to_read, task_to_read
from .session_service import SessionService
from .streaming_text import iter_stream_pieces


TASK_VISIBLE_OUTPUT_LIMIT = 3000
TASK_OUTPUT_TRUNCATION_NOTICE = "\n\n[后续输出已折叠：请查看任务工作包中的交付文件。]"


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

        task_workspace_path = self._ensure_task_workspace(
            workspace_path,
            execution,
            task,
            upstream_results,
        )
        message_id = f"msg_agent_{uuid.uuid4().hex[:12]}"
        task["taskWorkspacePath"] = task_workspace_path
        visible = ""
        raw_output = ""
        process_id = ""
        exit_code = None
        metadata: dict[str, Any] = {
            "agentType": agent.agent_type or "cli_wrapper",
            "cliTool": agent.cli_tool or "custom",
            "workspacePath": workspace_path,
            "taskWorkspacePath": task_workspace_path,
        }
        trace = ExecutionTraceBuilder(
            agent_name=agent.name,
            cli_tool=agent.cli_tool or "custom",
            workspace_path=workspace_path,
        )
        await self._persist_visible_message(
            execution,
            task,
            agent,
            message_id,
            "",
            merge_trace_metadata(metadata, trace),
        )
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
        truncated_notice_sent = False
        async for event in CliAgentService().stream(
            agent=agent,
            session_id=execution["sessionId"],
            workspace_path=workspace_path,
            messages=[{
                "role": "user",
                "content": self._task_prompt(
                    execution,
                    task,
                    upstream_results,
                    project_workspace_path=workspace_path,
                    task_workspace_path=task_workspace_path,
                ),
            }],
            system_prompt=agent.system_prompt or "",
        ):
            process_id = event.process_id or process_id
            if event.type == "agent.process.started":
                metadata["processId"] = process_id
                await self._bind_runtime_process(
                    execution,
                    task,
                    agent,
                    message_id,
                    process_id,
                )
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
                visible_chunk = ""
                if event.chunk_type in {"text", "artifact_signal"}:
                    visible_chunk, truncated_notice_sent = _bounded_visible_chunk(
                        event.chunk,
                        visible,
                        truncated_notice_sent,
                    )
                    visible += visible_chunk
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
                if event.chunk_type == "text" and visible_chunk:
                    await self._update_visible_message(
                        message_id,
                        content=visible,
                        metadata=merge_trace_metadata(metadata, trace),
                    )
                    for token in iter_stream_pieces(visible_chunk):
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
                await self._complete_runtime_process(process_id, exit_code=exit_code)
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
                await self._update_visible_message(
                    message_id,
                    content=visible,
                    metadata=merge_trace_metadata(metadata, trace),
                )
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
                await self._complete_runtime_process(
                    process_id,
                    exit_code=exit_code,
                    status="failed",
                )
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
                await self._update_visible_message(
                    message_id,
                    content=visible.strip() or f"CLI Agent 执行失败：{error}",
                    metadata=merge_trace_metadata(metadata, trace),
                )
                await self._broadcast_message_changed(execution["sessionId"], message_id)
                await _broadcast_ws(execution["sessionId"], {
                    "type": "message.completed",
                    "sessionId": execution["sessionId"],
                    "messageId": message_id,
                })
                raise RuntimeError(event.error or f"{agent.name} 执行失败")

        if exit_code not in (0, None):
            error = f"{agent.name} 执行失败，exitCode={exit_code}"
            await self._complete_runtime_process(
                process_id,
                exit_code=exit_code,
                status="failed",
            )
            trace.complete(status="error", exit_code=exit_code)
            metadata["error"] = error
            await self._update_visible_message(
                message_id,
                content=visible.strip() or f"CLI Agent 执行失败：{error}",
                metadata=merge_trace_metadata(metadata, trace),
            )
            await self._broadcast_message_changed(execution["sessionId"], message_id)
            await _broadcast_ws(execution["sessionId"], {
                "type": "message.completed",
                "sessionId": execution["sessionId"],
                "messageId": message_id,
            })
            raise RuntimeError(error)

        content = visible.strip() or raw_output.strip() or f"{task['taskId']} 已完成，但没有可见输出。"
        await self._update_visible_message(
            message_id,
            content=content,
            metadata=merge_trace_metadata(metadata, trace),
        )
        await self._broadcast_message_changed(execution["sessionId"], message_id)
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
        metadata = self._visible_message_metadata(execution, task, extra_metadata)
        async with self._session_factory() as db:
            session = await db.get(DBSession, execution["sessionId"])
            existing = await db.get(DBMessage, message_id)
            if existing:
                existing.content = content
                existing.metadata_json = json.dumps(metadata, ensure_ascii=False)
            else:
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

    async def _update_visible_message(
        self,
        message_id: str,
        *,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        async with self._session_factory() as db:
            message = await db.get(DBMessage, message_id)
            if not message:
                return
            if content is not None:
                message.content = content
            if metadata is not None:
                existing = _loads_metadata(message.metadata_json)
                existing.update(metadata)
                message.metadata_json = json.dumps(existing, ensure_ascii=False)
            await db.commit()

    @staticmethod
    def _visible_message_metadata(
        execution: dict[str, Any],
        task: dict[str, Any],
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = {
            "orchestratorTaskMessage": {
                "executionId": execution["executionId"],
                "planId": execution["planId"],
                "taskId": task["taskId"],
                "title": task["title"],
                "runnerType": "cli",
                "upstreamResults": task.get("upstreamResults") or [],
                "taskWorkspacePath": task.get("taskWorkspacePath"),
            },
            "agentRole": "executor",
            "phase": task.get("phase"),
            "taskName": task.get("title"),
        }
        if OrchestratorExecutionRegistry._task_waits_for_user(task):
            metadata.update({
                "dialogMode": "direct",
                "awaitingUserInput": True,
                "groupDialog": {
                    "mode": "direct_dialog",
                    "status": "awaiting_user_input",
                    "activeAgentId": task.get("assignedAgentId"),
                    "activeAgentName": task.get("assignedAgentName"),
                    "goal": task.get("goal") or task.get("title") or "",
                    "source": "orchestrator_task",
                    "executionId": execution.get("executionId"),
                    "taskId": task.get("taskId"),
                },
            })
        if execution.get("runId"):
            metadata["runId"] = execution["runId"]
            metadata["runStatus"] = "running"
        if task.get("runTaskId"):
            metadata["taskId"] = task["runTaskId"]
        if extra_metadata:
            metadata.update(extra_metadata)
        return metadata

    @staticmethod
    async def _broadcast_message_changed(session_id: str, message_id: str) -> None:
        await _broadcast_ws(session_id, {
            "type": "message.completed",
            "sessionId": session_id,
            "messageId": message_id,
        })

    async def _bind_runtime_process(
        self,
        execution: dict[str, Any],
        task: dict[str, Any],
        agent: AgentConfig,
        message_id: str,
        process_id: str,
    ) -> None:
        run_id = execution.get("runId")
        if not run_id or not process_id:
            return
        async with self._session_factory() as db:
            service = RunService(db)
            run = await service.bind_current_message(run_id, message_id)
            await _broadcast_ws(execution["sessionId"], {
                "type": "run.status_changed",
                "runId": run.id,
                "sessionId": run.session_id,
                "status": run.status,
                "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
                "token": "",
                "done": False,
            })
            if task.get("runTaskId"):
                task_row = await service.mark_task_status(
                    task["runTaskId"],
                    "running",
                    message_id=message_id,
                )
                await _broadcast_ws(execution["sessionId"], {
                    "type": "task.status_changed",
                    "runId": task_row.run_id,
                    "taskId": task_row.id,
                    "sessionId": task_row.session_id,
                    "status": task_row.status,
                    "task": task_to_read(task_row).model_dump(by_alias=True, mode="json"),
                    "token": "",
                    "done": False,
                })
            await service.bind_process(
                run_id=run_id,
                task_id=task.get("runTaskId"),
                session_id=execution["sessionId"],
                agent_id=agent.id,
                message_id=message_id,
                process_id=process_id,
            )

    async def _complete_runtime_process(
        self,
        process_id: str,
        *,
        exit_code: int | None,
        status: str | None = None,
    ) -> None:
        if not process_id:
            return
        async with self._session_factory() as db:
            await RunService(db).complete_process(
                process_id,
                exit_code=exit_code,
                status=status,
            )

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
        *,
        project_workspace_path: str,
        task_workspace_path: str,
    ) -> str:
        plan = execution.get("plan") or {}
        upstream = "\n".join(
            f"- {item.get('taskId')}: {item.get('summary') or ''}"
            for item in upstream_results
        ) or "- 无"
        return (
            "你正在作为 AgentHub 调度任务中的专家 Agent 执行一个 DAG 节点。\n"
            "当前进程 cwd 是项目根目录。请把用户最终需要看到、复用或继续开发的正式产物写入项目目录，"
            "聊天里只输出简短进展汇报。\n\n"
            "执行边界：\n"
            f"- 项目根目录: {project_workspace_path}\n"
            f"- 当前任务工作包目录: {task_workspace_path}\n"
            "- 项目根目录是正式交付区：PRD、架构设计、接口说明、测试清单等项目文档默认写入 `docs/`；"
            "源码、配置、测试和可运行 Demo 写入项目对应目录。\n"
            "- 任务工作包是临时追溯区：只放 TASK.md、草稿、过程笔记、HANDOFF.md 或给下游 Agent 的副本。\n"
            "- 不要把正式产物只留在 `.agenthub/executions/.../tasks`；除非任务明确说明只是内部草稿。\n"
            "- 不要在项目根目录创建 plan_*.json 等调度中间文件；需要保存中间结构时放任务工作包。\n"
            "- 聊天输出最多 8 行：完成了什么、写了哪些文件、下游应该看哪里、仍有什么风险。\n\n"
            f"Plan ID: {execution.get('planId')}\n"
            f"当前任务 ID: {task.get('taskId')}\n"
            f"当前任务标题: {task.get('title')}\n"
            f"当前任务目标: {task.get('goal')}\n"
            f"所需能力: {', '.join(task.get('requiredSkills') or []) or '未声明'}\n"
            f"期望输出: {', '.join(task.get('expectedOutputs') or []) or '未声明'}\n"
            f"验收标准: {', '.join(task.get('acceptanceCriteria') or []) or '未声明'}\n\n"
            f"互动策略: {task.get('interactionPolicy') or 'auto_run'}\n"
            f"交接策略: {task.get('handoffPolicy') or 'auto'}\n"
            f"下游释放条件: {task.get('blocksDownstreamUntil') or 'task_completed'}\n"
            "如果互动策略要求用户回答或确认，你本轮应优先向用户提出清晰问题或整理待确认事项，"
            "不要擅自代替用户确认，也不要把任务交给下游 Agent。\n\n"
            "上游任务结果:\n"
            f"{upstream}\n\n"
            "完整计划 JSON:\n"
            f"{json.dumps(plan, ensure_ascii=False, indent=2)}"
        )

    def _ensure_task_workspace(
        self,
        project_workspace_path: str,
        execution: dict[str, Any],
        task: dict[str, Any],
        upstream_results: list[dict[str, Any]],
    ) -> str:
        task_dir = (
            Path(project_workspace_path)
            / ".agenthub"
            / "executions"
            / _safe_path_part(execution["executionId"])
            / "tasks"
            / _safe_path_part(task["taskId"])
        )
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "TASK.md").write_text(
            self._task_card(
                execution,
                task,
                upstream_results,
                task_workspace_path=str(task_dir),
                project_workspace_path=project_workspace_path,
            ),
            encoding="utf-8",
        )
        return str(task_dir)

    @staticmethod
    def _task_card(
        execution: dict[str, Any],
        task: dict[str, Any],
        upstream_results: list[dict[str, Any]],
        *,
        task_workspace_path: str,
        project_workspace_path: str,
    ) -> str:
        upstream = "\n".join(
            f"- {item.get('taskId')}: {item.get('summary') or ''}"
            for item in upstream_results
        ) or "- 无"
        return (
            f"# {task.get('taskId')} · {task.get('title')}\n\n"
            f"- Plan: {execution.get('planId')}\n"
            f"- Execution: {execution.get('executionId')}\n"
            f"- Task workspace: `{task_workspace_path}`\n"
            f"- Project workspace: `{project_workspace_path}`\n"
            f"- Assigned Agent: {task.get('assignedAgentName') or task.get('assignedAgentId') or '未分配'}\n"
            f"- Required skills: {', '.join(task.get('requiredSkills') or []) or '未声明'}\n\n"
            "## Deliverable Boundary\n\n"
            "- Project workspace 是正式交付区；用户要的文档、代码、配置和测试应沉淀在项目目录。\n"
            "- Task workspace 是临时追溯区；只保存任务卡、草稿、过程笔记和下游 HANDOFF 副本。\n\n"
            "## Goal\n\n"
            f"{task.get('goal') or '未声明'}\n\n"
            "## Expected Outputs\n\n"
            f"{_markdown_list(task.get('expectedOutputs') or [])}\n\n"
            "## Acceptance Criteria\n\n"
            f"{_markdown_list(task.get('acceptanceCriteria') or [])}\n\n"
            "## Upstream Results\n\n"
            f"{upstream}\n"
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
        auto_start: bool = True,
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
                "message": "Scheduler 已启动。",
            }],
            "validation": {
                "ok": True,
                "errors": [],
                "warnings": validation["warnings"],
            },
        }
        self._executions[execution_id] = execution
        if auto_start:
            self._start_background_scheduler(execution_id)
        return copy.deepcopy(execution)

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        execution = self._executions.get(execution_id)
        if not execution:
            return None
        snapshot = copy.deepcopy(execution)
        for task in snapshot.get("tasks") or []:
            if (
                task.get("status") == "running"
                and task.get("runnerType") == "cli"
                and not task.get("visibleMessageId")
            ):
                task["status"] = "pending"
        return snapshot

    def bind_runtime(
        self,
        execution_id: str,
        *,
        run_id: str,
        task_id_by_orchestrator_task_id: dict[str, str],
    ) -> None:
        execution = self._executions.get(execution_id)
        if not execution:
            return
        execution["runId"] = run_id
        execution.setdefault("runtime", {})["runId"] = run_id
        for task in execution.get("tasks") or []:
            task_id = str(task.get("taskId"))
            run_task_id = task_id_by_orchestrator_task_id.get(task_id)
            if run_task_id:
                task["runId"] = run_id
                task["runTaskId"] = run_task_id
        execution["updatedAt"] = self._now()

    def bind_control_message(
        self,
        execution_id: str,
        message_id: str,
    ) -> None:
        execution = self._executions.get(execution_id)
        if not execution:
            return
        execution["controlMessageId"] = message_id
        execution["updatedAt"] = self._now()

    def start_execution(self, execution_id: str) -> None:
        if execution_id in self._executions:
            self._start_background_scheduler(execution_id)

    async def cancel_execution(self, execution_id: str) -> dict[str, Any] | None:
        execution = self._executions.get(execution_id)
        if execution is None:
            return None
        if execution.get("status") in {"completed", "failed", "cancelled"}:
            return copy.deepcopy(execution)

        cancelled_at = self._now()
        execution["cancelRequested"] = True
        execution["status"] = "cancelling"
        execution["updatedAt"] = cancelled_at
        execution["events"].append({
            "type": "execution_cancel_requested",
            "status": "cancelling",
            "timestamp": cancelled_at,
            "message": "用户请求停止当前调度执行。",
        })
        terminated = await cli_runtime_registry.terminate_session(execution["sessionId"])
        if execution.get("runId"):
            async with self._session_factory() as db:
                await RunService(db).cancel_run(execution["runId"], "用户请求停止当前调度执行")
        self._mark_cancelled(execution, terminated_process_count=terminated)
        await self._mark_cancelled_visible_messages(execution, "用户请求停止当前调度执行")
        await self._persist_execution_snapshot(execution)
        return copy.deepcopy(execution)

    async def confirm_waiting_task(
        self,
        execution_id: str,
        task_id: str,
        *,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        execution = self._executions.get(execution_id)
        if execution is None:
            return None
        target = next(
            (task for task in execution.get("tasks") or [] if task.get("taskId") == task_id),
            None,
        )
        if not target or target.get("status") != "awaiting_user_input":
            return None
        confirmed_at = self._now()
        target["status"] = "completed"
        target["completedAt"] = confirmed_at
        target["updatedAt"] = confirmed_at
        summary = note.strip() if note and note.strip() else target.get("summary") or "用户已确认该访谈节点。"
        target["summary"] = summary
        if not target.get("resultMessageId"):
            target["resultMessageId"] = await self._persist_task_result(execution, target, summary)
        await self._mark_runtime_task_status(
            execution,
            target,
            "completed",
            message_id=target.get("visibleMessageId"),
            metadata_patch={
                "awaitingUserInput": False,
                "userConfirmed": True,
                "confirmationNote": note,
            },
        )
        execution["status"] = "running"
        execution["updatedAt"] = confirmed_at
        execution["events"].append({
            "type": "task_user_confirmed",
            "status": "completed",
            "timestamp": confirmed_at,
            "taskId": task_id,
            "message": f"{task_id} 已由用户确认，Scheduler 将继续释放下游任务。",
        })
        await self._append_dialog_closed_message(
            execution,
            target,
            status="handoff_confirmed",
            content=f"{target.get('title') or task_id} 已确认，继续后续调度。",
        )
        await self._mark_runtime_run_status(execution, "running")
        await self._persist_execution_snapshot(execution)
        self.start_execution(execution_id)
        return copy.deepcopy(execution)

    async def _merge_visible_message_metadata(
        self,
        message_id: str,
        *,
        metadata: dict[str, Any],
    ) -> None:
        async with self._session_factory() as db:
            message = await db.get(DBMessage, message_id)
            if not message:
                return
            current = _loads_metadata(message.metadata_json)
            current.update(metadata)
            message.metadata_json = json.dumps(current, ensure_ascii=False)
            await db.commit()

    def mark_cancelled_by_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        for execution in self._executions.values():
            if execution.get("runId") != run_id:
                continue
            if execution.get("status") in {"completed", "failed", "cancelled"}:
                return copy.deepcopy(execution)
            cancelled_at = self._now()
            execution["cancelRequested"] = True
            execution["status"] = "cancelling"
            execution["updatedAt"] = cancelled_at
            execution["events"].append({
                "type": "execution_cancel_requested",
                "status": "cancelling",
                "timestamp": cancelled_at,
                "message": reason or "用户通过运行控制停止当前调度执行。",
            })
            self._mark_cancelled(execution)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._persist_cancelled_execution(execution, reason))
            else:
                loop.create_task(self._persist_cancelled_execution(execution, reason))
            return copy.deepcopy(execution)
        return None

    async def _persist_cancelled_execution(self, execution: dict[str, Any], reason: str | None = None) -> None:
        await self._mark_cancelled_visible_messages(execution, reason or "调度执行已停止")
        await self._persist_execution_snapshot(execution)

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
        await self._mark_runtime_run_status(execution, "running")
        tasks = execution["tasks"]
        completed: set[str] = {
            task["taskId"] for task in tasks
            if task.get("status") == "completed"
        }
        pending = {
            task["taskId"] for task in tasks
            if task.get("status") not in {"completed", "cancelled", "failed", "awaiting_user_input"}
        }
        task_by_id = {task["taskId"]: task for task in tasks}

        phase = 0
        while pending:
            if self._is_cancelled(execution):
                self._mark_cancelled(execution)
                await self._cancel_runtime_execution(execution)
                await self._mark_cancelled_visible_messages(execution, "调度执行已停止")
                await self._persist_execution_snapshot(execution)
                return
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
                await self._mark_runtime_run_status(execution, "failed")
                await self._persist_execution_snapshot(execution)
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
                task["status"] = "running"
                task["phase"] = phase
                task["startedAt"] = running_at
                task["updatedAt"] = running_at
                await self._mark_runtime_task_status(
                    execution,
                    task,
                    "running",
                    metadata_patch={"phase": phase},
                )
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
                if self._is_cancelled(execution):
                    self._mark_cancelled(execution)
                    await self._cancel_runtime_execution(execution)
                    await self._mark_cancelled_visible_messages(execution, "调度执行已停止")
                    await self._persist_execution_snapshot(execution)
                    return
                failed_at = self._now()
                execution["status"] = "failed"
                execution["updatedAt"] = failed_at
                await self._mark_runtime_run_status(execution, "failed")
                execution["events"].append({
                    "type": "execution_failed",
                    "status": "failed",
                    "timestamp": failed_at,
                    "phase": phase,
                    "taskIds": ready,
                    "message": f"Scheduler 执行失败：{exc}",
                })
                for task_id in ready:
                    task = task_by_id[task_id]
                    task["status"] = "failed"
                    task["updatedAt"] = failed_at
                    await self._mark_runtime_task_status(
                        execution,
                        task,
                        "failed",
                        metadata_patch={"error": str(exc)},
                    )
                await self._persist_execution_snapshot(execution)
                return
            completed_at = self._now()
            execution["updatedAt"] = completed_at
            for task_id, summary in zip(ready, summaries):
                task = task_by_id[task_id]
                if self._task_waits_for_user(task):
                    task["status"] = "awaiting_user_input"
                    task["summary"] = summary
                    task["updatedAt"] = completed_at
                    if task.get("visibleMessageId"):
                        await self._merge_visible_message_metadata(
                            task["visibleMessageId"],
                            metadata={
                                "runStatus": "paused",
                                "awaitingUserInput": True,
                                "groupDialog": {
                                    "mode": "direct_dialog",
                                    "status": "awaiting_user_input",
                                    "activeAgentId": task.get("assignedAgentId"),
                                    "activeAgentName": task.get("assignedAgentName"),
                                    "goal": task.get("goal") or task.get("title") or "",
                                    "source": "orchestrator_task",
                                    "executionId": execution.get("executionId"),
                                    "taskId": task.get("taskId"),
                                },
                            },
                        )
                    await self._mark_runtime_task_status(
                        execution,
                        task,
                        "paused",
                        message_id=task.get("visibleMessageId"),
                        metadata_patch={
                            "interactionPolicy": task.get("interactionPolicy"),
                            "handoffPolicy": task.get("handoffPolicy"),
                            "awaitingUserInput": True,
                            "blocksDownstreamUntil": task.get("blocksDownstreamUntil"),
                        },
                    )
                    execution["status"] = "awaiting_user_input"
                    execution["updatedAt"] = completed_at
                    execution["events"].append({
                        "type": "task_awaiting_user_input",
                        "status": "awaiting_user_input",
                        "timestamp": completed_at,
                        "phase": phase,
                        "taskId": task_id,
                        "message": f"{task_id} 等待用户回答或确认后再继续下游任务。",
                    })
                    await self._mark_runtime_run_status(
                        execution,
                        "paused",
                        current_message_id=task.get("visibleMessageId"),
                    )
                    await self._persist_execution_snapshot(execution)
                    await _broadcast_ws(execution["sessionId"], {
                        "type": "task.awaiting_user_input",
                        "executionId": execution["executionId"],
                        "planId": execution["planId"],
                        "taskId": task_id,
                        "messageId": task.get("visibleMessageId"),
                        "agentId": task.get("assignedAgentId"),
                        "agentName": task.get("assignedAgentName"),
                        "task": task,
                        "token": "",
                        "done": False,
                    })
                    return
                task["status"] = "completed"
                task["completedAt"] = completed_at
                task["updatedAt"] = completed_at
                task["summary"] = summary
                task["resultMessageId"] = await self._persist_task_result(execution, task, summary)
                await self._mark_runtime_task_status(
                    execution,
                    task,
                    "completed",
                    message_id=task.get("visibleMessageId"),
                )
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
            if self._is_cancelled(execution):
                self._mark_cancelled(execution)
                await self._cancel_runtime_execution(execution)
                await self._mark_cancelled_visible_messages(execution, "调度执行已停止")
                await self._persist_execution_snapshot(execution)
                return

            phase += 1

        completed_at = self._now()
        final_execution = copy.deepcopy(execution)
        final_execution["status"] = "completed"
        final_execution["completedAt"] = completed_at
        final_execution["updatedAt"] = completed_at
        await self._mark_runtime_run_status(
            final_execution,
            "completed",
            current_message_id=self._latest_visible_message_id(final_execution),
        )
        final_execution["events"].append({
            "type": "execution_completed",
            "status": "completed",
            "timestamp": completed_at,
            "message": "Scheduler 已按 DAG 完成全部任务。",
        })
        await self._persist_execution_snapshot(final_execution)
        execution.clear()
        execution.update(final_execution)

    @staticmethod
    def _is_cancelled(execution: dict[str, Any]) -> bool:
        return bool(execution.get("cancelRequested")) or execution.get("status") in {"cancelling", "cancelled"}

    def _mark_cancelled(
        self,
        execution: dict[str, Any],
        *,
        terminated_process_count: int | None = None,
    ) -> None:
        already_cancelled = execution.get("status") == "cancelled"
        cancelled_at = self._now()
        for task in execution.get("tasks") or []:
            if task.get("status") == "running":
                task["status"] = "cancelled"
                task["updatedAt"] = cancelled_at
            elif task.get("status") == "pending":
                task["updatedAt"] = cancelled_at
        execution["status"] = "cancelled"
        execution["completedAt"] = cancelled_at
        execution["updatedAt"] = cancelled_at
        if already_cancelled:
            return
        event = {
            "type": "execution_cancelled",
            "status": "cancelled",
            "timestamp": cancelled_at,
            "message": "调度执行已停止。",
        }
        if terminated_process_count is not None:
            event["terminatedProcessCount"] = terminated_process_count
            event["message"] = f"调度执行已停止，已终止 {terminated_process_count} 个 CLI 进程。"
        execution["events"].append(event)

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

    async def _append_dialog_closed_message(
        self,
        execution: dict[str, Any],
        task: dict[str, Any],
        *,
        status: str,
        content: str,
    ) -> None:
        metadata = {
            "groupDialog": {
                "mode": "direct_dialog",
                "status": status,
                "activeAgentId": task.get("assignedAgentId"),
                "activeAgentName": task.get("assignedAgentName"),
                "goal": task.get("goal") or task.get("title") or "",
                "source": "orchestrator_task",
                "executionId": execution.get("executionId"),
                "taskId": task.get("taskId"),
            }
        }
        async with self._session_factory() as db:
            db.add(DBMessage(
                id=f"msg_system_{uuid.uuid4().hex[:12]}",
                session_id=execution["sessionId"],
                role="system",
                content=content,
                content_type="text",
                source_type="system",
                source_name="调度控制",
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            ))
            await db.commit()

    async def _persist_execution_snapshot(self, execution: dict[str, Any]) -> None:
        message_id = execution.get("controlMessageId")
        if not message_id:
            return
        async with self._session_factory() as db:
            message = await db.get(DBMessage, message_id)
            if not message:
                return
            try:
                metadata = json.loads(message.metadata_json or "{}")
            except json.JSONDecodeError:
                metadata = {}
            metadata["orchestratorExecution"] = copy.deepcopy(execution)
            message.metadata_json = json.dumps(metadata, ensure_ascii=False)
            await db.commit()

    async def _mark_cancelled_visible_messages(
        self,
        execution: dict[str, Any],
        reason: str,
    ) -> None:
        now = self._now()
        async with self._session_factory() as db:
            changed_ids: list[str] = []
            for task in execution.get("tasks") or []:
                message_id = task.get("visibleMessageId")
                if not message_id:
                    continue
                message = await db.get(DBMessage, message_id)
                if not message:
                    continue
                metadata = _loads_metadata(message.metadata_json)
                trace = metadata.get("executionTrace")
                if isinstance(trace, dict):
                    trace["status"] = "cancelled"
                    trace["completedAt"] = trace.get("completedAt") or now
                    trace["items"] = [
                        *(trace.get("items") if isinstance(trace.get("items"), list) else []),
                        {
                            "id": f"trace_{uuid.uuid4().hex[:12]}",
                            "kind": "info",
                            "text": "调度执行已停止",
                            "source": "system",
                            "chunkType": "cancelled",
                            "level": "warning",
                            "timestamp": now,
                        },
                    ][-300:]
                    metadata["executionTrace"] = trace
                metadata["runStatus"] = "cancelled"
                metadata["cancelReason"] = reason
                if not message.content:
                    message.content = "任务已中止，未产生可见输出。"
                message.metadata_json = json.dumps(metadata, ensure_ascii=False)
                changed_ids.append(message_id)
            if changed_ids:
                await db.commit()
        for message_id in changed_ids:
            await _broadcast_ws(execution["sessionId"], {
                "type": "message.completed",
                "sessionId": execution["sessionId"],
                "messageId": message_id,
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
            "interactionPolicy": str(task.get("interaction_policy") or "auto_run"),
            "handoffPolicy": str(task.get("handoff_policy") or "auto"),
            "awaitsUserInput": bool(task.get("awaits_user_input")),
            "blocksDownstreamUntil": str(task.get("blocks_downstream_until") or "task_completed"),
            "taskWorkspacePath": None,
        }

    async def _run_task(self, task: dict[str, Any], execution: dict[str, Any]) -> str:
        runner = self._cli_runner if task.get("runnerType") == "cli" else self._task_runner
        return await runner.run(task, execution, task.get("upstreamResults") or [])

    async def _mark_runtime_run_status(
        self,
        execution: dict[str, Any],
        status: str,
        *,
        current_message_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        run_id = execution.get("runId")
        if not run_id:
            return
        async with self._session_factory() as db:
            run = await RunService(db).mark_run_status(
                run_id,
                status,
                current_message_id=current_message_id,
                reason=reason,
            )
            await _broadcast_ws(execution["sessionId"], {
                "type": "run.status_changed",
                "runId": run.id,
                "sessionId": run.session_id,
                "status": run.status,
                "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
                "token": "",
                "done": False,
            })

    async def _mark_runtime_task_status(
        self,
        execution: dict[str, Any],
        task: dict[str, Any],
        status: str,
        *,
        message_id: str | None = None,
        metadata_patch: dict[str, Any] | None = None,
    ) -> None:
        run_task_id = task.get("runTaskId")
        if not run_task_id:
            return
        async with self._session_factory() as db:
            task_row = await RunService(db).mark_task_status(
                run_task_id,
                status,
                message_id=message_id,
                metadata_patch=metadata_patch,
            )
            await _broadcast_ws(execution["sessionId"], {
                "type": "task.status_changed",
                "runId": task_row.run_id,
                "taskId": task_row.id,
                "sessionId": task_row.session_id,
                "status": task_row.status,
                "task": task_to_read(task_row).model_dump(by_alias=True, mode="json"),
                "token": "",
                "done": False,
            })

    async def _cancel_runtime_execution(self, execution: dict[str, Any]) -> None:
        run_id = execution.get("runId")
        if not run_id:
            return
        async with self._session_factory() as db:
            run = await RunService(db).cancel_run(run_id, "调度执行已停止")
            await _broadcast_ws(execution["sessionId"], {
                "type": "run.status_changed",
                "runId": run.id,
                "sessionId": run.session_id,
                "status": run.status,
                "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
                "token": "",
                "done": False,
            })

    @staticmethod
    def _latest_visible_message_id(execution: dict[str, Any]) -> str | None:
        for task in reversed(execution.get("tasks") or []):
            if task.get("visibleMessageId"):
                return task["visibleMessageId"]
        return None

    @staticmethod
    def _runner_type_for(execution: dict[str, Any]) -> str:
        runner_type = str(execution.get("runnerType") or "cli").strip().lower()
        return "mock" if runner_type == "mock" else "cli"

    @staticmethod
    def _task_waits_for_user(task: dict[str, Any]) -> bool:
        if task.get("awaitsUserInput"):
            return True
        if task.get("blocksDownstreamUntil") == "user_confirms":
            return True
        return task.get("interactionPolicy") in {"ask_user_once", "ask_user_until_confirmed"}

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


def _bounded_visible_chunk(
    chunk: str,
    current_visible: str,
    notice_sent: bool,
) -> tuple[str, bool]:
    remaining = TASK_VISIBLE_OUTPUT_LIMIT - len(current_visible)
    if remaining <= 0:
        if notice_sent:
            return "", True
        return TASK_OUTPUT_TRUNCATION_NOTICE, True
    if len(chunk) <= remaining:
        return chunk, notice_sent
    suffix = "" if notice_sent else TASK_OUTPUT_TRUNCATION_NOTICE
    return chunk[:remaining].rstrip() + suffix, True


def _safe_path_part(value: object) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return clean or "task"


def _markdown_list(items: list[Any]) -> str:
    if not items:
        return "- 未声明"
    return "\n".join(f"- {item}" for item in items)


def _summary_text(content: str, limit: int = 1200) -> str:
    clean = content.strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "\n...(已截断，完整内容见 Agent 消息)"


def _loads_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _broadcast_ws(session_id: str, payload: dict[str, Any]) -> None:
    try:
        from ..api.ws_manager import manager as ws_manager
        await ws_manager.broadcast(session_id, payload)
    except Exception:
        pass
