"""已审批 Orchestrator 静态 DAG 的唯一执行引擎。"""

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
from ..domain.orchestrator_plan import extract_json_object, normalize_plan, validate_plan
from ..models import AgentConfig, Message as DBMessage, Project, Session as DBSession, User
from ..agents.cli_trace import trace_text
from .artifact_output_bridge import ArtifactOutputBridge, artifact_to_event_payload
from .cloud_cli_agent_service import CloudCliAgentService
from .cloud_storage import ensure_cloud_workspace
from .cli_agent_service import CliAgentService
from .execution_trace import ExecutionTraceBuilder, merge_trace_metadata
from .run_service import RunService, run_to_read, task_to_read
from .orchestrator_plan_service import OrchestratorPlanNotFoundError, OrchestratorPlanService
from .session_service import SessionService
from .streaming_text import iter_stream_pieces


TASK_VISIBLE_OUTPUT_LIMIT = 3000
TASK_OUTPUT_TRUNCATION_NOTICE = "\n\n[后续输出已折叠：请查看任务工作包中的交付文件。]"
LIVE_EXECUTION_STATUSES = {"pending", "running", "cancelling"}
TERMINAL_EXECUTION_STATUSES = {"completed", "failed", "cancelled"}


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


class PhaseReviewer(Protocol):
    async def review(
        self,
        execution: dict[str, Any],
        phase: int,
        tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """由 Orchestrator 对一个批次的 Worker 提交做统一验收。"""


class AcceptingPhaseReviewer:
    """仅供显式 mock 执行使用的确定性验收器。"""

    async def review(
        self,
        execution: dict[str, Any],
        phase: int,
        tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "phaseSummary": f"Phase {phase + 1} 的 {len(tasks)} 个任务已通过测试验收器。",
            "tasks": [
                {"taskId": task["taskId"], "decision": "accepted", "feedback": ""}
                for task in tasks
            ],
        }


class OrchestratorPhaseReviewer:
    """调用群聊项目 Leader，对 Worker 结果进行语义验收。"""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        cli_agents: CliAgentService | None = None,
    ):
        self._session_factory = session_factory
        self._cli_agents = cli_agents or CliAgentService()

    async def review(
        self,
        execution: dict[str, Any],
        phase: int,
        tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        orchestrator_id = str(execution.get("orchestratorAgentId") or "")
        if not orchestrator_id:
            raise RuntimeError("执行缺少 orchestratorAgentId，无法验收 Worker 结果")
        async with self._session_factory() as db:
            orchestrator = await db.get(AgentConfig, orchestrator_id)
            if not orchestrator or not orchestrator.is_active:
                raise RuntimeError("Orchestrator 不存在或未启用")
            cloud_project = getattr(self._cli_agents, "project", None)
            if cloud_project is not None and getattr(cloud_project, "workspace_mode", None) == "cloud":
                workspace_path = (
                    cloud_project.workspace_path
                    or f"cloud://agenthub/workspaces/{cloud_project.workspace_id}"
                )
            else:
                workspace_path = await SessionService(db).get_workspace_path(execution["sessionId"])

        raw = ""
        prompt = self._prompt(execution, phase, tasks)
        async for event in self._cli_agents.stream(
            agent=orchestrator,
            session_id=execution["sessionId"],
            workspace_path=workspace_path,
            messages=[
                *(execution.get("groupContext") or []),
                {"role": "user", "content": prompt},
            ],
            system_prompt=orchestrator.system_prompt or "",
        ):
            if event.type == "agent.output" and event.chunk_type in {"text", "artifact_signal"}:
                raw += event.chunk
            elif event.type in {"agent.process.timeout", "error"}:
                raise RuntimeError(event.error or "Orchestrator 验收失败")
            elif event.type in {"agent.process.completed", "agent.process.turn_completed"}:
                if event.exit_code not in (0, None):
                    raise RuntimeError(f"Orchestrator 验收进程异常退出：{event.exit_code}")

        result = extract_json_object(raw)
        decisions = result.get("tasks")
        if not isinstance(decisions, list):
            raise RuntimeError("Orchestrator 验收输出缺少 tasks")
        expected = {str(task["taskId"]) for task in tasks}
        actual = {
            str(item.get("taskId") or item.get("task_id"))
            for item in decisions if isinstance(item, dict)
        }
        if expected != actual:
            raise RuntimeError("Orchestrator 验收结果未覆盖当前 Phase 的全部任务")
        for item in decisions:
            decision = str(item.get("decision") or "")
            if decision not in {"accepted", "retry", "blocked"}:
                raise RuntimeError(f"无效验收结论：{decision}")
        return result

    @staticmethod
    def _prompt(
        execution: dict[str, Any],
        phase: int,
        tasks: list[dict[str, Any]],
    ) -> str:
        payload = [{
            "taskId": task.get("taskId"),
            "title": task.get("title"),
            "goal": task.get("goal"),
            "acceptanceCriteria": task.get("acceptanceCriteria") or [],
            "attempt": task.get("attempt"),
            "summary": task.get("summary"),
            "resultMessageId": task.get("resultMessageId"),
            "upstreamResults": task.get("upstreamResults") or [],
        } for task in tasks]
        schema = {
            "phaseSummary": "给用户看的阶段验收汇报",
            "tasks": [{
                "taskId": "T1",
                "decision": "accepted | retry | blocked",
                "feedback": "不通过时给 Worker 的可执行修改意见",
                "decisionRequired": None,
            }],
        }
        return (
            "你是 AgentHub 群聊唯一的 Orchestrator。请验收当前 Phase 的 Worker 提交。\n"
            "只输出 JSON，不修改文件。逐条对照 acceptanceCriteria；CLI 退出不代表验收通过。\n"
            "accepted 表示可释放下游；retry 表示原节点按反馈重做；blocked 表示必须由你统一询问用户。\n\n"
            f"Plan:\n{json.dumps(execution.get('plan') or {}, ensure_ascii=False, indent=2)}\n\n"
            f"Phase: {phase}\nWorker submissions:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            f"输出结构:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )


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
        return f"{task['taskId']} 已完成：模拟执行 {agent}"


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
            messages=[
                *(execution.get("groupContext") or []),
                {
                    "role": "user",
                    "content": self._task_prompt(
                    execution,
                    task,
                    upstream_results,
                    project_workspace_path=workspace_path,
                    task_workspace_path=task_workspace_path,
                ),
                },
            ],
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
            f"期望输出: {', '.join(task.get('expectedOutputs') or []) or '未声明'}\n"
            f"验收标准: {', '.join(task.get('acceptanceCriteria') or []) or '未声明'}\n\n"
            f"当前尝试: {int(task.get('attempt') or 0) + 1}/{int(task.get('maxAttempts') or 3)}\n"
            f"Orchestrator 重做反馈: {task.get('retryFeedback') or '无'}\n"
            "你是 Worker，不能直接向用户申请批准。若缺少用户决策，请在结果中清楚列出阻塞问题，"
            "由 Orchestrator 统一协调用户。\n\n"
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


class CloudCliTaskRunner(CliTaskRunner):
    """云端 Orchestrator 计划任务 runner，复用桌面任务可见消息契约。"""

    def __init__(
        self,
        *,
        actor_id: str,
        project_id: str,
        event_bus: Any = None,
        session_factory: Callable[[], AsyncSession] = AsyncSessionLocal,
    ):
        super().__init__(session_factory)
        self._actor_id = actor_id
        self._project_id = project_id
        self._event_bus = event_bus

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
            project = await db.get(Project, self._project_id)
            actor = await db.get(User, self._actor_id)
            if not agent or not agent.is_active:
                raise RuntimeError(f"{task['taskId']} 分配的 Agent 不存在或未启用: {agent_id}")
            if not session:
                raise RuntimeError(f"Session 不存在: {execution['sessionId']}")
            if not project or project.workspace_mode != "cloud" or not project.workspace_id:
                raise RuntimeError("云端计划任务需要 cloud Project")
            if not actor:
                raise RuntimeError("云端计划任务缺少执行用户")

            physical_workspace = str(ensure_cloud_workspace(project.workspace_id, {
                "projectId": project.id,
                "executionId": execution.get("executionId"),
            }))
            physical_task_workspace = self._ensure_task_workspace(
                physical_workspace,
                execution,
                task,
                upstream_results,
            )
            task_workspace_rel = _relative_workspace_path(physical_workspace, physical_task_workspace)
            task["taskWorkspacePath"] = task_workspace_rel
            message_id = f"msg_agent_{uuid.uuid4().hex[:12]}"
            visible = ""
            raw_output = ""
            process_id = ""
            exit_code = None
            artifact_workspace_path = physical_workspace
            metadata: dict[str, Any] = {
                "agentType": agent.agent_type or "cli_wrapper",
                "cliTool": agent.cli_tool or "custom",
                "workspacePath": project.workspace_path,
                "taskWorkspacePath": task_workspace_rel,
                "runtimeMode": "cloud",
                "workspaceId": project.workspace_id,
            }
            trace = ExecutionTraceBuilder(
                agent_name=agent.name,
                cli_tool=agent.cli_tool or "custom",
                workspace_path=project.workspace_path or "",
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

            cloud_cli_agents = CloudCliAgentService(
                db,
                actor=actor,
                project=project,
                event_bus=self._event_bus,
            )
            truncated_notice_sent = False
            async for event in cloud_cli_agents.stream(
                agent=agent,
                session_id=execution["sessionId"],
                workspace_path=project.workspace_path or "",
                messages=[
                    *(execution.get("groupContext") or []),
                    {
                        "role": "user",
                        "content": self._task_prompt(
                        execution,
                        task,
                        upstream_results,
                        project_workspace_path=".",
                        task_workspace_path=task_workspace_rel,
                    ),
                    },
                ],
                system_prompt=agent.system_prompt or "",
            ):
                process_id = event.process_id or process_id
                if event.type == "agent.metadata":
                    if isinstance(event.metadata, dict):
                        artifact_workspace_path = str(
                            event.metadata.get("artifactWorkspacePath")
                            or artifact_workspace_path
                        )
                        metadata.update({
                            key: value
                            for key, value in event.metadata.items()
                            if key != "artifactWorkspacePath"
                        })
                    continue
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
                        kind = (
                            "artifact" if event.chunk_type == "artifact_signal"
                            else "error" if event.chunk_type == "error"
                            else "progress"
                        )
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
                    elif event.chunk_type != "text":
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
                            "chunk": event.chunk,
                            "chunkType": event.chunk_type,
                            "token": "",
                            "done": False,
                        })
                    continue
                if event.type in {"agent.process.completed", "agent.process.turn_completed"}:
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
                    await self._complete_runtime_process(process_id, exit_code=exit_code, status="failed")
                    item = trace.add(kind="error", text=error, process_id=process_id, trace=event.trace)
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
                    raise RuntimeError(error)

            if exit_code not in (0, None):
                error = f"{agent.name} 执行失败，exitCode={exit_code}"
                await self._complete_runtime_process(process_id, exit_code=exit_code, status="failed")
                trace.complete(status="error", exit_code=exit_code)
                metadata["error"] = error
                await self._update_visible_message(
                    message_id,
                    content=visible.strip() or f"CLI Agent 执行失败：{error}",
                    metadata=merge_trace_metadata(metadata, trace),
                )
                await self._broadcast_message_changed(execution["sessionId"], message_id)
                raise RuntimeError(error)

            content = visible.strip() or raw_output.strip() or f"{task['taskId']} 已完成，但没有可见输出。"
            final_metadata = merge_trace_metadata(metadata, trace)
            await self._update_visible_message(
                message_id,
                content=content,
                metadata=final_metadata,
            )
            await self._scan_visible_message_artifacts(
                db=db,
                session=session,
                project=project,
                agent=agent,
                message_id=message_id,
                content=content,
                metadata=final_metadata,
                workspace_path=artifact_workspace_path,
                snapshot_id=str(metadata.get("workspaceSnapshotId") or "") or None,
            )
            await self._broadcast_message_changed(execution["sessionId"], message_id)
            await _broadcast_ws(execution["sessionId"], {
                "type": "message.completed",
                "sessionId": execution["sessionId"],
                "messageId": message_id,
            })
            return _summary_text(content)

    async def _scan_visible_message_artifacts(
        self,
        *,
        db: AsyncSession,
        session: DBSession,
        project: Project,
        agent: AgentConfig,
        message_id: str,
        content: str,
        metadata: dict[str, Any],
        workspace_path: str,
        snapshot_id: str | None,
    ) -> None:
        if not session.project_id:
            return
        message = await db.get(DBMessage, message_id)
        if not message:
            return
        await _broadcast_ws(session.id, {
            "type": "artifact.scan.started",
            "sessionId": session.id,
            "messageId": message_id,
            "projectId": session.project_id,
            "agentId": agent.id,
            "agentName": agent.name,
            "token": "",
            "done": False,
        })
        bridge = ArtifactOutputBridge(db, event_bus=self._event_bus)
        try:
            result = await bridge.scan_completed_message(
                session=session,
                message=message,
                project=project,
                workspace_path=workspace_path,
                visible_content=content,
                execution_trace=metadata.get("executionTrace")
                if isinstance(metadata.get("executionTrace"), dict)
                else None,
                snapshot_id=snapshot_id,
            )
        except Exception as exc:
            await _broadcast_ws(session.id, {
                "type": "artifact.detection_failed",
                "sessionId": session.id,
                "messageId": message_id,
                "projectId": session.project_id,
                "reason": f"{type(exc).__name__}: {exc}",
                "recoverable": True,
                "token": "",
                "done": False,
            })
            return

        for artifact in result.created:
            payload = artifact_to_event_payload(artifact)
            await _broadcast_ws(session.id, {
                "type": "artifact.created",
                "artifact": payload,
                "artifactId": payload["id"],
                "sessionId": payload["sessionId"],
                "messageId": payload["messageId"],
                "projectId": payload["projectId"],
                "artifactType": payload["type"],
                "title": payload["title"],
                "version": payload["version"],
                "filePath": payload["filePath"],
                "source": payload["source"],
                "token": "",
                "done": False,
            })
        await _broadcast_ws(session.id, {
            "type": "artifact.scan.completed",
            "sessionId": session.id,
            "messageId": message_id,
            "projectId": session.project_id,
            "createdCount": len(result.created),
            "candidateCount": len(result.candidates),
            "skippedCount": len(result.skipped),
            "token": "",
            "done": False,
        })


class OrchestratorExecutionRegistry:
    def __init__(
        self,
        task_runner: TaskRunner | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
    ):
        self._executions: dict[str, dict[str, Any]] = {}
        self._execution_task_runners: dict[str, TaskRunner] = {}
        self._execution_phase_reviewers: dict[str, PhaseReviewer] = {}
        self._task_runner = task_runner or MockTaskRunner()
        self._session_factory = session_factory or AsyncSessionLocal
        self._cli_runner = CliTaskRunner(self._session_factory)
        self._phase_reviewer = OrchestratorPhaseReviewer(self._session_factory)

    def create_execution(
        self,
        *,
        session_id: str,
        plan: dict[str, Any],
        active_agent_ids: set[str],
        auto_start: bool = True,
        task_runner: TaskRunner | None = None,
        phase_reviewer: PhaseReviewer | None = None,
        orchestrator_agent_id: str | None = None,
        group_context: list[dict[str, Any]] | None = None,
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
        phase_by_task = self._phase_depths(tasks)
        for task in tasks:
            task["phase"] = phase_by_task.get(task["taskId"], 0)
        execution = {
            "executionId": execution_id,
            "sessionId": session_id,
            "planId": normalized.get("plan_id"),
            "orchestratorAgentId": orchestrator_agent_id,
            "groupContext": self._normalize_group_context(group_context or []),
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
        if task_runner is not None:
            self._execution_task_runners[execution_id] = task_runner
        if phase_reviewer is not None:
            self._execution_phase_reviewers[execution_id] = phase_reviewer
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

    def restore_execution(self, execution: dict[str, Any]) -> dict[str, Any]:
        execution_id = str(execution.get("executionId") or "")
        if not execution_id:
            return copy.deepcopy(execution)
        restored = copy.deepcopy(execution)
        self._executions[execution_id] = restored
        return copy.deepcopy(restored)

    def interrupted_snapshot(self, execution: dict[str, Any], *, reason: str) -> dict[str, Any]:
        snapshot = copy.deepcopy(execution)
        self._mark_snapshot_interrupted(snapshot, reason=reason)
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

    async def request_worker_revision(
        self,
        *,
        session_id: str,
        agent_id: str,
        feedback: str,
        run_id: str | None = None,
    ) -> dict[str, Any] | None:
        """将用户对 Worker 的点名反馈映射为原静态 DAG 节点的新一次尝试。"""
        candidates = sorted(
            (
                execution for execution in self._executions.values()
                if execution.get("sessionId") == session_id
                and execution.get("status") in {"running", "completed", "failed", "waiting_user", "interrupted"}
            ),
            key=lambda item: str(item.get("createdAt") or ""),
            reverse=True,
        )
        for execution in candidates:
            target = next(
                (
                    task for task in execution.get("tasks") or []
                    if task.get("assignedAgentId") == agent_id
                    and task.get("status") not in {"cancelled"}
                ),
                None,
            )
            if target is None:
                continue
            reset_ids = self._task_and_descendants(execution, str(target["taskId"]))
            if execution.get("status") == "running":
                reset_ids.update(
                    str(task.get("taskId"))
                    for task in execution.get("tasks") or []
                    if task.get("status") in {"running", "submitted", "reviewing"}
                )
                execution["revisionGeneration"] = int(execution.get("revisionGeneration") or 0) + 1
                await cli_runtime_registry.terminate_session(session_id)
            revised_at = self._now()
            runtime_ids: dict[str, str] = {}
            if run_id:
                async with self._session_factory() as db:
                    run_service = RunService(db)
                    run = await run_service.get_run(run_id)
                    for task in execution.get("tasks") or []:
                        if task.get("taskId") not in reset_ids:
                            continue
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
                                "revision": True,
                            },
                        )
                        runtime_ids[str(task["taskId"])] = runtime_task.id

            for task in execution.get("tasks") or []:
                if task.get("taskId") not in reset_ids:
                    continue
                for attempt in reversed(task.get("attempts") or []):
                    if attempt.get("status") == "superseded":
                        continue
                    attempt["status"] = "superseded"
                    attempt["supersededAt"] = revised_at
                    attempt["supersededReason"] = feedback.strip()
                    break
                task["status"] = "pending"
                task["completedAt"] = None
                task["updatedAt"] = revised_at
                task["summary"] = None
                task["resultMessageId"] = None
                task["orchestratorReview"] = None
                task["retryFeedback"] = (
                    feedback.strip()
                    if task is target
                    else f"上游任务 {target['taskId']} 因用户反馈返工，本节点旧结果已失效，请基于新上游结果重做。"
                )
                task["maxAttempts"] = max(
                    int(task.get("maxAttempts") or 3),
                    int(task.get("attempt") or 0) + 1,
                )
                if task.get("taskId") in runtime_ids:
                    task["runTaskId"] = runtime_ids[str(task["taskId"])]
                    task["runId"] = run_id

            execution["status"] = "running"
            execution["completedAt"] = None
            execution["updatedAt"] = revised_at
            execution["cancelRequested"] = False
            execution["interruptRequested"] = False
            if run_id:
                execution["runId"] = run_id
                execution.setdefault("runtime", {})["runId"] = run_id
            execution.setdefault("events", []).append({
                "type": "user_revision_requested",
                "status": "running",
                "timestamp": revised_at,
                "taskId": target["taskId"],
                "taskIds": sorted(reset_ids),
                "message": f"用户要求 @{target.get('assignedAgentName') or agent_id} 返工；目标节点及下游结果已失效。",
            })
            await self._persist_execution_snapshot(execution)
            self.start_execution(execution["executionId"])
            return copy.deepcopy(execution)
        return None

    @staticmethod
    def _task_and_descendants(execution: dict[str, Any], task_id: str) -> set[str]:
        affected = {task_id}
        changed = True
        while changed:
            changed = False
            for task in execution.get("tasks") or []:
                current_id = str(task.get("taskId"))
                if current_id in affected:
                    continue
                if any(str(dep) in affected for dep in task.get("dependsOn") or []):
                    affected.add(current_id)
                    changed = True
        return affected

    @staticmethod
    def _normalize_group_context(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        context: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "user")
            content = str(message.get("content") or "").strip()
            if role not in {"user", "assistant", "system"} or not content:
                continue
            context.append({"role": role, "content": content})
        return context

    @staticmethod
    def _phase_depths(tasks: list[dict[str, Any]]) -> dict[str, int]:
        by_id = {str(task["taskId"]): task for task in tasks}
        cache: dict[str, int] = {}

        def depth(task_id: str) -> int:
            if task_id in cache:
                return cache[task_id]
            dependencies = by_id[task_id].get("dependsOn") or []
            value = 0 if not dependencies else 1 + max(depth(str(dep)) for dep in dependencies)
            cache[task_id] = value
            return value

        return {task_id: depth(task_id) for task_id in by_id}

    async def interrupt_execution(
        self,
        execution_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        execution = self._executions.get(execution_id)
        if execution is None:
            return None
        if execution.get("status") in TERMINAL_EXECUTION_STATUSES:
            return copy.deepcopy(execution)
        if execution.get("status") == "interrupted":
            return copy.deepcopy(execution)

        interrupted_at = self._now()
        execution["interruptRequested"] = True
        execution["cancelRequested"] = False
        execution["status"] = "interrupted"
        execution["updatedAt"] = interrupted_at
        execution["interruptReason"] = reason or "用户中断当前调度执行"
        interrupted_tasks: list[str] = []
        for task in execution.get("tasks") or []:
            if task.get("status") in {"running", "cancelling"}:
                task["status"] = "interrupted"
                task["updatedAt"] = interrupted_at
                interrupted_tasks.append(str(task.get("taskId")))
                await self._mark_runtime_task_status(
                    execution,
                    task,
                    "paused",
                    message_id=task.get("visibleMessageId"),
                    metadata_patch={
                        "runStatus": "interrupted",
                        "interrupted": True,
                        "interruptReason": reason,
                    },
                )
        terminated = await cli_runtime_registry.terminate_session(execution["sessionId"])
        if execution.get("runId"):
            async with self._session_factory() as db:
                await RunService(db).interrupt_run(execution["runId"], reason or "用户中断当前调度执行")
        execution["events"].append({
            "type": "execution_interrupted",
            "status": "interrupted",
            "timestamp": interrupted_at,
            "taskIds": interrupted_tasks,
            "message": "调度执行已中断，可从执行面板继续或放弃。",
            "terminatedProcessCount": terminated,
        })
        await self._mark_interrupted_visible_messages(execution, reason or "调度执行已中断")
        await self._persist_execution_snapshot(execution)
        return copy.deepcopy(execution)

    async def resume_execution(self, execution_id: str) -> dict[str, Any] | None:
        execution = self._executions.get(execution_id)
        if execution is None:
            return None
        if execution.get("status") in TERMINAL_EXECUTION_STATUSES:
            return copy.deepcopy(execution)
        resumed_at = self._now()
        if execution.get("status") in LIVE_EXECUTION_STATUSES:
            self._mark_snapshot_interrupted(execution, reason="服务重启或运行态丢失后恢复")
        resumable = execution.get("status") in {"interrupted", "paused"}
        if not resumable:
            return copy.deepcopy(execution)

        reset_tasks: list[str] = []
        for task in execution.get("tasks") or []:
            if task.get("status") == "interrupted":
                task["status"] = "pending"
                task["updatedAt"] = resumed_at
                reset_tasks.append(str(task.get("taskId")))
                await self._mark_runtime_task_status(
                    execution,
                    task,
                    "pending",
                    metadata_patch={
                        "runStatus": "running",
                        "resumed": True,
                    },
                )
        execution["status"] = "running"
        execution["cancelRequested"] = False
        execution["interruptRequested"] = False
        execution["updatedAt"] = resumed_at
        execution["events"].append({
            "type": "execution_resumed",
            "status": "running",
            "timestamp": resumed_at,
            "taskIds": reset_tasks,
            "message": "调度执行已从断点恢复，Scheduler 将从未完成任务继续。",
        })
        await self._mark_runtime_run_status(execution, "running")
        await self._persist_execution_snapshot(execution)
        self.start_execution(execution_id)
        return copy.deepcopy(execution)

    async def cancel_execution(self, execution_id: str) -> dict[str, Any] | None:
        execution = self._executions.get(execution_id)
        if execution is None:
            return None
        if execution.get("status") in TERMINAL_EXECUTION_STATUSES:
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
            if task.get("status") in {"accepted", "completed"}
        }
        pending = {
            task["taskId"] for task in tasks
            if task.get("status") not in {"accepted", "completed", "cancelled", "failed", "blocked"}
        }
        task_by_id = {task["taskId"]: task for task in tasks}
        scheduler_generation = int(execution.get("revisionGeneration") or 0)

        while pending:
            if scheduler_generation != int(execution.get("revisionGeneration") or 0):
                return
            if self._is_interrupted(execution):
                await self._persist_execution_snapshot(execution)
                return
            if self._is_cancelled(execution):
                self._mark_cancelled(execution)
                await self._cancel_runtime_execution(execution)
                await self._mark_cancelled_visible_messages(execution, "调度执行已停止")
                await self._persist_execution_snapshot(execution)
                return
            ready_candidates = sorted(
                task_id
                for task_id in pending
                if all(dep in completed for dep in task_by_id[task_id]["dependsOn"])
            )
            if not ready_candidates:
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

            phase = min(int(task_by_id[task_id].get("phase") or 0) for task_id in ready_candidates)
            ready: list[str] = []
            assigned_agents: set[str] = set()
            for task_id in ready_candidates:
                task = task_by_id[task_id]
                if int(task.get("phase") or 0) != phase:
                    continue
                agent_id = str(task.get("assignedAgentId") or "")
                if agent_id and agent_id in assigned_agents:
                    continue
                ready.append(task_id)
                if agent_id:
                    assigned_agents.add(agent_id)
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
                if scheduler_generation != int(execution.get("revisionGeneration") or 0):
                    return
                if self._is_interrupted(execution):
                    await self._persist_execution_snapshot(execution)
                    return
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
            if scheduler_generation != int(execution.get("revisionGeneration") or 0):
                return
            if self._is_interrupted(execution):
                await self._persist_execution_snapshot(execution)
                return
            submitted_at = self._now()
            execution["updatedAt"] = submitted_at
            for task_id, summary in zip(ready, summaries):
                task = task_by_id[task_id]
                task["attempt"] = int(task.get("attempt") or 0) + 1
                task["status"] = "submitted"
                task["updatedAt"] = submitted_at
                task["summary"] = summary
                task["resultMessageId"] = await self._persist_task_result(execution, task, summary)
                task.setdefault("attempts", []).append({
                    "attempt": task["attempt"],
                    "status": "submitted",
                    "summary": summary,
                    "resultMessageId": task["resultMessageId"],
                    "submittedAt": submitted_at,
                })
                await self._mark_runtime_task_status(
                    execution,
                    task,
                    "submitted",
                    message_id=task.get("visibleMessageId"),
                    metadata_patch={
                        "attempt": task["attempt"],
                        "taskResultMessageId": task["resultMessageId"],
                    },
                )
                execution["events"].append({
                    "type": "task_submitted",
                    "status": "submitted",
                    "timestamp": submitted_at,
                    "phase": phase,
                    "taskId": task_id,
                    "message": summary,
                })

            try:
                review = await self._review_phase(execution, phase, [task_by_id[item] for item in ready])
            except Exception as exc:
                review = {
                    "phaseSummary": f"Orchestrator 验收失败：{exc}",
                    "tasks": [
                        {"taskId": item, "decision": "retry", "feedback": str(exc)}
                        for item in ready
                    ],
                }
            if scheduler_generation != int(execution.get("revisionGeneration") or 0):
                return
            decisions = {
                str(item.get("taskId") or item.get("task_id")): item
                for item in review.get("tasks") or []
                if isinstance(item, dict)
            }
            blocked_items: list[dict[str, Any]] = []
            failed_items: list[str] = []
            reviewed_at = self._now()
            for task_id in ready:
                task = task_by_id[task_id]
                decision = decisions.get(task_id) or {
                    "decision": "retry",
                    "feedback": "Orchestrator 未返回该任务的验收结论",
                }
                verdict = str(decision.get("decision") or "retry")
                feedback = str(decision.get("feedback") or "").strip()
                attempt_entry = task["attempts"][-1]
                attempt_entry["reviewedAt"] = reviewed_at
                attempt_entry["decision"] = verdict
                attempt_entry["feedback"] = feedback
                task["orchestratorReview"] = decision
                if verdict == "accepted":
                    task["status"] = "accepted"
                    task["completedAt"] = reviewed_at
                    attempt_entry["status"] = "accepted"
                    pending.remove(task_id)
                    completed.add(task_id)
                    await self._mark_runtime_task_status(
                        execution,
                        task,
                        "accepted",
                        message_id=task.get("visibleMessageId"),
                        metadata_patch={"orchestratorReview": decision},
                    )
                    event_type = "task_accepted"
                elif verdict == "blocked":
                    task["status"] = "blocked"
                    attempt_entry["status"] = "blocked"
                    blocked_items.append(decision)
                    await self._mark_runtime_task_status(
                        execution,
                        task,
                        "paused",
                        message_id=task.get("visibleMessageId"),
                        metadata_patch={"orchestratorReview": decision},
                    )
                    event_type = "task_blocked"
                elif int(task.get("attempt") or 0) >= int(task.get("maxAttempts") or 3):
                    task["status"] = "failed"
                    task["completedAt"] = reviewed_at
                    attempt_entry["status"] = "failed"
                    failed_items.append(task_id)
                    await self._mark_runtime_task_status(
                        execution,
                        task,
                        "failed",
                        message_id=task.get("visibleMessageId"),
                        metadata_patch={"orchestratorReview": decision},
                    )
                    event_type = "task_retry_exhausted"
                else:
                    task["status"] = "pending"
                    task["retryFeedback"] = feedback
                    attempt_entry["status"] = "retry"
                    await self._mark_runtime_task_status(
                        execution,
                        task,
                        "pending",
                        message_id=task.get("visibleMessageId"),
                        metadata_patch={"orchestratorReview": decision, "retryFeedback": feedback},
                    )
                    event_type = "task_retry_requested"
                task["updatedAt"] = reviewed_at
                execution["events"].append({
                    "type": event_type,
                    "status": task["status"],
                    "timestamp": reviewed_at,
                    "phase": phase,
                    "taskId": task_id,
                    "attempt": task.get("attempt"),
                    "message": feedback or verdict,
                })

            await self._persist_phase_review(execution, phase, review, [task_by_id[item] for item in ready])
            if blocked_items:
                execution["status"] = "waiting_user"
                execution["updatedAt"] = reviewed_at
                await self._mark_runtime_run_status(execution, "paused")
                await self._persist_execution_snapshot(execution)
                return
            if failed_items:
                execution["status"] = "failed"
                execution["updatedAt"] = reviewed_at
                await self._mark_runtime_run_status(execution, "failed")
                await self._persist_execution_snapshot(execution)
                return
            if self._is_cancelled(execution):
                self._mark_cancelled(execution)
                await self._cancel_runtime_execution(execution)
                await self._mark_cancelled_visible_messages(execution, "调度执行已停止")
                await self._persist_execution_snapshot(execution)
                return

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
        await self._persist_completion_summary(final_execution)
        await self._persist_execution_snapshot(final_execution)
        execution.clear()
        execution.update(final_execution)

    @staticmethod
    def _is_cancelled(execution: dict[str, Any]) -> bool:
        return bool(execution.get("cancelRequested")) or execution.get("status") in {"cancelling", "cancelled"}

    @staticmethod
    def _is_interrupted(execution: dict[str, Any]) -> bool:
        return bool(execution.get("interruptRequested")) or execution.get("status") == "interrupted"

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

    async def _persist_execution_snapshot(self, execution: dict[str, Any]) -> None:
        async with self._session_factory() as db:
            try:
                await OrchestratorPlanService(db).persist_execution_snapshot(execution)
            except OrchestratorPlanNotFoundError:
                pass
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
                    existing_items = trace.get("items") if isinstance(trace.get("items"), list) else []
                    total_item_count = int(trace.get("totalItemCount") or len(existing_items)) + 1
                    next_items = [
                        *existing_items,
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
                    trace["status"] = "cancelled"
                    trace["completedAt"] = trace.get("completedAt") or now
                    trace["totalItemCount"] = total_item_count
                    trace["truncated"] = bool(trace.get("truncated")) or total_item_count > len(next_items)
                    trace["items"] = next_items
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

    async def _mark_interrupted_visible_messages(
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
                if isinstance(trace, dict) and trace.get("status") == "running":
                    existing_items = trace.get("items") if isinstance(trace.get("items"), list) else []
                    total_item_count = int(trace.get("totalItemCount") or len(existing_items)) + 1
                    next_items = [
                        *existing_items,
                        {
                            "id": f"trace_{uuid.uuid4().hex[:12]}",
                            "kind": "info",
                            "text": "调度执行已中断，可从执行面板继续",
                            "source": "system",
                            "chunkType": "interrupted",
                            "level": "warning",
                            "timestamp": now,
                        },
                    ][-300:]
                    trace["status"] = "interrupted"
                    trace["completedAt"] = trace.get("completedAt") or now
                    trace["totalItemCount"] = total_item_count
                    trace["truncated"] = bool(trace.get("truncated")) or total_item_count > len(next_items)
                    trace["items"] = next_items
                    metadata["executionTrace"] = trace
                metadata["runStatus"] = "interrupted"
                metadata["interruptReason"] = reason
                if not message.content:
                    message.content = "任务已中断，可从执行面板继续。"
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
    def _mark_snapshot_interrupted(
        execution: dict[str, Any],
        *,
        reason: str,
    ) -> dict[str, Any]:
        interrupted_at = datetime.now(timezone.utc).isoformat()
        execution["status"] = "interrupted"
        execution["updatedAt"] = interrupted_at
        execution["interruptReason"] = reason
        execution["cancelRequested"] = False
        execution["interruptRequested"] = True
        interrupted_tasks: list[str] = []
        for task in execution.get("tasks") or []:
            if task.get("status") in {"running", "cancelling"}:
                task["status"] = "interrupted"
                task["updatedAt"] = interrupted_at
                interrupted_tasks.append(str(task.get("taskId")))
        execution.setdefault("events", []).append({
            "type": "execution_interrupted",
            "status": "interrupted",
            "timestamp": interrupted_at,
            "taskIds": interrupted_tasks,
            "message": "检测到执行运行态已丢失，已转为可恢复中断。",
        })
        return execution

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
            "attempt": 0,
            "maxAttempts": int(task.get("max_attempts") or 3),
            "attempts": [],
            "retryFeedback": None,
            "orchestratorReview": None,
            "resultMessageId": None,
            "visibleMessageId": None,
            "runnerType": "mock",
            "upstreamResults": [],
            "assignedAgentId": task.get("assigned_agent_id"),
            "assignedAgentName": task.get("assigned_agent_name"),
            "dependsOn": list(task.get("depends_on") or []),
            "expectedOutputs": list(task.get("expected_outputs") or []),
            "acceptanceCriteria": list(task.get("acceptance_criteria") or []),
            "taskWorkspacePath": None,
        }

    async def _run_task(self, task: dict[str, Any], execution: dict[str, Any]) -> str:
        runner = None
        if task.get("runnerType") == "cli":
            runner = self._execution_task_runners.get(str(execution.get("executionId") or ""))
        if runner is None:
            runner = self._cli_runner if task.get("runnerType") == "cli" else self._task_runner
        return await runner.run(task, execution, task.get("upstreamResults") or [])

    async def _review_phase(
        self,
        execution: dict[str, Any],
        phase: int,
        tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        execution_id = str(execution.get("executionId") or "")
        reviewer = self._execution_phase_reviewers.get(execution_id)
        if reviewer is None:
            reviewer = (
                AcceptingPhaseReviewer()
                if self._runner_type_for(execution) == "mock"
                else self._phase_reviewer
            )
        for task in tasks:
            task["status"] = "reviewing"
            await self._mark_runtime_task_status(
                execution,
                task,
                "reviewing",
                message_id=task.get("visibleMessageId"),
            )
        execution["events"].append({
            "type": "orchestrator_review_started",
            "status": "reviewing",
            "timestamp": self._now(),
            "phase": phase,
            "taskIds": [task["taskId"] for task in tasks],
            "message": "Worker 已提交，Orchestrator 正在统一验收。",
        })
        return await reviewer.review(execution, phase, tasks)

    async def _persist_phase_review(
        self,
        execution: dict[str, Any],
        phase: int,
        review: dict[str, Any],
        tasks: list[dict[str, Any]],
    ) -> str:
        summary = str(review.get("phaseSummary") or "Orchestrator 已完成阶段验收。").strip()
        message_id = f"msg_review_{uuid.uuid4().hex[:12]}"
        metadata = {
            "orchestratorPhaseReview": {
                "executionId": execution.get("executionId"),
                "planId": execution.get("planId"),
                "phase": phase,
                "taskIds": [task.get("taskId") for task in tasks],
                "review": review,
            },
            "agentRole": "orchestrator",
            "phase": phase,
            "taskName": "phase review",
        }
        async with self._session_factory() as db:
            orchestrator = await db.get(AgentConfig, execution.get("orchestratorAgentId"))
            db.add(DBMessage(
                id=message_id,
                session_id=execution["sessionId"],
                role="assistant",
                content=summary,
                content_type="orchestrator_summary",
                agent_name=orchestrator.name if orchestrator else "项目Leader",
                source_type="orchestrator",
                source_id=execution.get("orchestratorAgentId"),
                source_name=orchestrator.name if orchestrator else "项目Leader",
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            ))
            await db.commit()
        await _broadcast_ws(execution["sessionId"], {
            "type": "orchestrator.phase_review_completed",
            "sessionId": execution["sessionId"],
            "executionId": execution.get("executionId"),
            "planId": execution.get("planId"),
            "phase": phase,
            "messageId": message_id,
            "review": review,
            "token": "",
            "done": False,
        })
        return message_id

    async def _persist_completion_summary(self, execution: dict[str, Any]) -> str:
        lines = ["全部 DAG 节点已通过 Orchestrator 验收。"]
        for task in execution.get("tasks") or []:
            summary = _summary_text(str(task.get("summary") or "已完成"), limit=500)
            lines.append(
                f"- {task.get('taskId')} · {task.get('title')} · "
                f"@{task.get('assignedAgentName') or task.get('assignedAgentId')}: {summary}"
            )
        message_id = f"msg_summary_{uuid.uuid4().hex[:12]}"
        async with self._session_factory() as db:
            orchestrator = await db.get(AgentConfig, execution.get("orchestratorAgentId"))
            name = orchestrator.name if orchestrator else "项目Leader"
            db.add(DBMessage(
                id=message_id,
                session_id=execution["sessionId"],
                role="assistant",
                content="\n".join(lines),
                content_type="orchestrator_summary",
                agent_name=name,
                source_type="orchestrator",
                source_id=execution.get("orchestratorAgentId"),
                source_name=name,
                metadata_json=json.dumps({
                    "orchestratorCompletionSummary": {
                        "executionId": execution.get("executionId"),
                        "planId": execution.get("planId"),
                        "taskIds": [task.get("taskId") for task in execution.get("tasks") or []],
                    },
                }, ensure_ascii=False),
            ))
            await db.commit()
        await _broadcast_ws(execution["sessionId"], {
            "type": "orchestrator.execution_summary_completed",
            "sessionId": execution["sessionId"],
            "executionId": execution.get("executionId"),
            "messageId": message_id,
            "token": "",
            "done": False,
        })
        return message_id

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


def _relative_workspace_path(workspace_path: str, target_path: str) -> str:
    try:
        return Path(target_path).resolve().relative_to(Path(workspace_path).resolve()).as_posix()
    except ValueError:
        return str(target_path)


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
        from ..infrastructure.realtime import manager as ws_manager
        await ws_manager.broadcast(session_id, payload)
    except Exception:
        pass
