"""Phase 10 云端 Agent Runtime。

当前实现使用本机隔离目录模拟 cloud sandbox 的挂载路径，外层 API/DB/事件契约
保持与将来 Docker/microVM runner 可替换。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..agents.cli_defaults import DEFAULT_CLI_AGENTS
from ..agents.cli_runtime_registry import cli_runtime_registry
from ..core.timezone import china_now
from ..domain.context_manager import ContextManager, PromptAssemblyInput
from ..event_bus.event_types import EventType
from ..models import (
    AgentConfig,
    Message,
    Project,
    RuntimeLog,
    RuntimeRun,
    Sandbox,
    Session as DBSession,
    SessionMember,
    User,
)
from .artifact_output_bridge import ArtifactOutputBridge, artifact_to_event_payload
from .chat_service_impl import _approval_requested
from .cli_agent_service import CliAgentService
from .cli_credential_service import CliCredentialRequiredError, CliCredentialService
from .collaboration_service import CollaborationNotFoundError, attachment_context_metadata
from .context_pack_service import ContextPackService
from .execution_trace import ExecutionTraceBuilder, merge_trace_metadata
from .file_change_detector import FileChangeDetector
from .message_service_sqlalchemy import SqlAlchemyMessageService, build_reply_reference_metadata
from .phase10_schemas import RuntimeLogsRead, RuntimeLogChunkRead, SessionRunCreate, SessionRunQueuedRead
from .quota_service import QuotaExceededError, QuotaService
from .runner_provider import (
    collect_workspace_sync,
    ensure_workspace_volume,
    get_runner_provider,
    workspace_path_for_sandbox,
)
from .run_service import RunService, run_to_read, task_to_read
from .sandbox_service import SandboxNotFoundError, SandboxService, sandbox_to_read
from .secret_service import SecretRedactor, SecretService
from .session_service import SessionService
from .single_cli_chat_stream import _split_system_prompt
from .streaming_text import iter_stream_pieces


TERMINAL_RUNTIME_STATUSES = {"completed", "failed", "cancelled", "timed_out"}


class CloudRuntimeError(ValueError):
    pass


class CloudRunNotFoundError(LookupError):
    pass


class CloudAgentRuntimeService:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus
        self.context_manager = ContextManager()
        self.cli_agents = CliAgentService(event_bus=event_bus)
        self.file_changes = FileChangeDetector()

    async def stream_chat(
        self,
        session_id: str,
        content: str,
        *,
        actor: User,
        parent_message_id: str | None = None,
        attachment_ids: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        session, project = await self._session_project(session_id)
        if project.workspace_mode != "cloud" or not project.workspace_id:
            yield self._err("当前会话不是云端 Project")
            return
        reply_metadata = await self._reply_metadata(session_id, parent_message_id)
        metadata = dict(reply_metadata or {})
        try:
            attachment_metadata = await attachment_context_metadata(
                self.db,
                session_id=session_id,
                attachment_ids=attachment_ids,
            )
        except CollaborationNotFoundError as exc:
            yield self._err(str(exc))
            return
        if attachment_metadata:
            metadata.update(attachment_metadata)
        user_message = await self._create_user_message(
            session,
            content,
            parent_message_id=parent_message_id,
            metadata=metadata or None,
        )
        async for item in self._stream_message_run(
            session=session,
            project=project,
            actor=actor,
            agent_id=session.agent_config_id,
            user_message=user_message,
            content=content,
        ):
            yield item

    async def stream_group_chat(
        self,
        session_id: str,
        content: str,
        *,
        actor: User,
        mentions: list[str] | None = None,
        parent_message_id: str | None = None,
        attachment_ids: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        session, project = await self._session_project(session_id)
        if session.mode != "group":
            async for item in self.stream_chat(
                session_id,
                content,
                actor=actor,
                parent_message_id=parent_message_id,
                attachment_ids=attachment_ids,
            ):
                yield item
            return
        if project.workspace_mode != "cloud" or not project.workspace_id:
            yield self._err("当前会话不是云端 Project")
            return
        agents = await self._group_runtime_agents(session, mentions)
        if not agents:
            yield self._err("群聊没有可运行的 Agent")
            return
        reply_metadata = await self._reply_metadata(session_id, parent_message_id)
        metadata = dict(reply_metadata or {})
        try:
            attachment_metadata = await attachment_context_metadata(
                self.db,
                session_id=session_id,
                attachment_ids=attachment_ids,
            )
        except CollaborationNotFoundError as exc:
            yield self._err(str(exc))
            return
        if attachment_metadata:
            metadata.update(attachment_metadata)
        user_message = await self._create_user_message(
            session,
            content,
            parent_message_id=parent_message_id,
            metadata=metadata or None,
        )
        yield self._sse({
            "type": "orchestrator.route",
            "agents": [
                {
                    "agentId": agent.id,
                    "agentName": agent.name,
                    "role": "executor",
                    "phase": index,
                    "task": content,
                }
                for index, agent in enumerate(agents)
            ],
            "sessionId": session.id,
            "mode": "cloud",
            "token": "",
            "done": False,
        })
        for index, agent in enumerate(agents):
            yield self._sse({
                "type": "orchestrator.task_started",
                "sessionId": session.id,
                "agentId": agent.id,
                "agentName": agent.name,
                "phase": index,
                "task": content,
                "token": "",
                "done": False,
            })
            async for item in self._stream_message_run(
                session=session,
                project=project,
                actor=actor,
                agent_id=agent.id,
                user_message=user_message,
                content=content,
            ):
                yield self._group_stream_item(item, agent)
            yield self._sse({
                "type": "orchestrator.task_completed",
                "sessionId": session.id,
                "agentId": agent.id,
                "agentName": agent.name,
                "phase": index,
                "summary": f"{agent.name} completed",
                "token": "",
                "done": False,
            })
        yield self._sse({
            "token": "",
            "done": True,
            "sessionId": session.id,
            "mode": "cloud",
        })

    async def stream_existing_message(
        self,
        session_id: str,
        data: SessionRunCreate,
        *,
        actor: User,
    ) -> AsyncGenerator[str, None]:
        session, project = await self._session_project(session_id)
        if project.workspace_mode != "cloud" or not project.workspace_id:
            yield self._err("当前会话不是云端 Project")
            return
        user_message = await self._message_for_run(session, data)
        async for item in self._stream_message_run(
            session=session,
            project=project,
            actor=actor,
            agent_id=data.agent_id,
            user_message=user_message,
            content=user_message.content,
        ):
            yield item

    async def stream_regenerate_message(
        self,
        message_id: str,
        *,
        actor: User,
    ) -> AsyncGenerator[str, None]:
        message = await self.db.get(Message, message_id)
        if not message:
            yield self._err("message not found", message_id=message_id)
            return
        if message.role != "assistant":
            yield self._err("only assistant messages can be regenerated", message_id=message_id)
            return
        session, project = await self._session_project(message.session_id)
        if project.workspace_mode != "cloud" or not project.workspace_id:
            yield self._err("当前会话不是云端 Project", message_id=message_id)
            return
        agent = await self._agent_for_message(message, session)
        if not agent:
            yield self._err("agent not found for message", message_id=message_id)
            return
        user_message = await self._previous_user_message(message)
        if not user_message:
            yield self._err("message has no user prompt to regenerate", message_id=message_id)
            return
        async for item in self._stream_message_run(
            session=session,
            project=project,
            actor=actor,
            agent_id=agent.id,
            user_message=user_message,
            content=user_message.content,
            assistant_message_id=message.id,
            history_before_message_id=message.id,
            replace_assistant=message,
        ):
            yield item

    async def run_existing_message(
        self,
        session_id: str,
        data: SessionRunCreate,
        *,
        actor: User,
    ) -> SessionRunQueuedRead:
        run_id = ""
        sandbox_id = None
        status = "completed"
        async for item in self.stream_existing_message(session_id, data, actor=actor):
            payload = _parse_sse(item)
            if not payload:
                continue
            if payload.get("type") == "run.started":
                run_id = str(payload.get("runId") or "")
                run = payload.get("run")
                if isinstance(run, dict):
                    metadata = run.get("metadata")
                    if isinstance(metadata, dict):
                        sandbox_id = metadata.get("sandboxId")
            if payload.get("type") == "run.status_changed":
                status = str(payload.get("status") or status)
            if payload.get("type") == "error":
                status = "failed"
        if not run_id:
            raise CloudRuntimeError("cloud runtime failed before run was created")
        return SessionRunQueuedRead(
            run_id=run_id,
            sandbox_id=str(sandbox_id) if sandbox_id else None,
            status=status,
            runtime="cloud",
        )

    async def create_local_placeholder_run(
        self,
        session_id: str,
        data: SessionRunCreate,
    ) -> SessionRunQueuedRead:
        session = await self.db.get(DBSession, session_id)
        if not session:
            raise CloudRuntimeError("session not found")
        run = await RunService(self.db, event_bus=self.event_bus).create_run(
            session,
            mode="single",
            metadata={
                "runtimeMode": "local",
                "agentId": data.agent_id,
                "messageId": data.message_id,
            },
        )
        return SessionRunQueuedRead(run_id=run.id, sandbox_id=None, status=run.status, runtime="local")

    async def cancel_cloud_run(self, run_id: str, reason: str | None = None):
        runtime_run = await self.db.get(RuntimeRun, run_id)
        if not runtime_run or runtime_run.runtime_mode != "cloud":
            return None
        if runtime_run.status not in TERMINAL_RUNTIME_STATUSES:
            runtime_run.status = "cancelling"
            await self.db.commit()
        run = await RunService(self.db, event_bus=self.event_bus).cancel_run(run_id, reason)
        runtime_run = await self.db.get(RuntimeRun, run_id)
        if runtime_run:
            runtime_run.status = "cancelled"
            runtime_run.finished_at = runtime_run.finished_at or china_now()
            if reason:
                runtime_run.error_summary = reason
        if runtime_run and runtime_run.sandbox_id:
            sandbox = await self.db.get(Sandbox, runtime_run.sandbox_id)
            if sandbox:
                await get_runner_provider().cancel(sandbox, run_id=run_id, reason=reason)
                await SandboxService(self.db, event_bus=self.event_bus).mark_stopped(
                    sandbox,
                    run_id=run_id,
                    reason=reason,
                )
        await self.db.commit()
        return run

    async def get_logs(self, run_id: str) -> RuntimeLogsRead:
        runtime_run = await self.db.get(RuntimeRun, run_id)
        if not runtime_run:
            raise CloudRunNotFoundError(run_id)
        result = await self.db.execute(
            select(RuntimeLog)
            .where(RuntimeLog.run_id == run_id)
            .order_by(RuntimeLog.sequence.asc())
        )
        chunks = [
            RuntimeLogChunkRead(
                sequence=log.sequence,
                stream=log.stream,
                text=log.text,
                created_at=log.created_at,
            )
            for log in result.scalars().all()
        ]
        return RuntimeLogsRead(run_id=run_id, chunks=chunks)

    async def _stream_message_run(
        self,
        *,
        session: DBSession,
        project: Project,
        actor: User,
        agent_id: str | None,
        user_message: Message,
        content: str,
        assistant_message_id: str | None = None,
        history_before_message_id: str | None = None,
        replace_assistant: Message | None = None,
    ) -> AsyncGenerator[str, None]:
        if not agent_id:
            yield self._err("会话未关联 Agent")
            return
        agent = await self.db.get(AgentConfig, agent_id)
        if not agent or not agent.is_active:
            yield self._err("agent not found")
            return
        if not project.workspace_id:
            yield self._err("cloud workspace not found")
            return

        try:
            await CliCredentialService(self.db).assert_ready_for_agent(agent, actor=actor, project=project)
        except CliCredentialRequiredError as exc:
            yield self._err(str(exc))
            return

        try:
            await QuotaService(self.db, event_bus=self.event_bus).assert_can_start(actor)
            sandbox = await SandboxService(self.db, event_bus=self.event_bus).reuse_or_create(
                workspace_id=project.workspace_id,
                actor=actor,
            )
        except (QuotaExceededError, SandboxNotFoundError) as exc:
            yield self._err(str(exc))
            return

        provider = get_runner_provider()
        workspace_path = workspace_path_for_sandbox(sandbox)
        assistant_msg_id = assistant_message_id or str(uuid.uuid4())
        replace_existing = replace_assistant is not None
        previous_content = replace_assistant.content if replace_assistant else None
        run_service = RunService(self.db, event_bus=self.event_bus)
        approval_required = _approval_requested(content)
        run = await run_service.create_run(
            session,
            mode="cloud",
            metadata={
                "runtimeMode": "cloud",
                "sandboxId": sandbox.id,
                "workspaceId": project.workspace_id,
                "userMessageId": user_message.id,
                "requiresHumanApproval": approval_required,
            },
        )
        task = await run_service.create_task(
            run,
            agent_id=agent.id,
            name="primary",
            role="executor",
            phase=0,
            metadata={"runtimeMode": "cloud", "sandboxId": sandbox.id},
        )
        runtime_run = RuntimeRun(
            id=run.id,
            session_id=session.id,
            agent_id=agent.id,
            sandbox_id=sandbox.id,
            runtime_mode="cloud",
            status="queued",
            queued_at=china_now(),
        )
        self.db.add(runtime_run)
        await self.db.commit()
        await self.db.refresh(runtime_run)

        redactor = await SecretService(self.db).redactor_for_project(actor=actor, project=project)
        sequence = 0

        def next_sequence() -> int:
            nonlocal sequence
            sequence += 1
            return sequence

        await self._log(runtime_run.id, next_sequence(), "system", f"sandbox {sandbox.id} ready", redactor)
        yield self._sse({
            "type": "run.started",
            "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
            "runId": run.id,
            "sessionId": session.id,
            "mode": "cloud",
            "messageId": None,
            "token": "",
            "done": False,
        })
        yield self._task_status_changed(run.id, task)
        yield self._sandbox_event("sandbox.created", sandbox)
        yield self._sandbox_event("sandbox.ready", sandbox)

        if history_before_message_id:
            history, pinned_ids = await SqlAlchemyMessageService(
                self.db,
                context_manager=self.context_manager,
            ).history_for_session(session.id, before_message_id=history_before_message_id)
        else:
            history, pinned_ids = await ContextPackService(
                self.db,
                event_bus=self.event_bus,
                context_manager=self.context_manager,
            ).runtime_context(session.id, purpose="send")
        adapter_messages, system_prompt = self._assemble_prompt(
            session.id,
            history,
            pinned_ids,
            agent.system_prompt or "",
        )
        runtime_agent = await self._runtime_agent(
            agent,
            actor=actor,
            project=project,
            workspace_path=workspace_path,
        )
        runner_process = await provider.prepare_process(
            sandbox=sandbox,
            agent=runtime_agent,
            run_id=run.id,
            workspace_path=workspace_path,
        )
        runtime_agent = runner_process.agent
        workspace_path = runner_process.workspace_path
        use_persistent_process = _cloud_persistent_process_supported(
            runtime_agent,
            runner_process.metadata,
            self.cli_agents,
        )
        trace = ExecutionTraceBuilder(
            agent_name=agent.name,
            cli_tool=agent.cli_tool or "custom",
            workspace_path=project.workspace_path,
        )
        metadata: dict[str, Any] = {
            "agentType": agent.agent_type or "cli_wrapper",
            "cliTool": agent.cli_tool or "custom",
            "workspacePath": project.workspace_path,
            "runtimeMode": "cloud",
            "sandboxId": sandbox.id,
            "workspaceId": project.workspace_id,
            "cloudRuntime": {
                "runnerNodeId": sandbox.runner_node_id,
                "image": sandbox.image,
                "provider": sandbox.provider or provider.name,
                "externalId": sandbox.external_id,
                "region": sandbox.region,
                "network": _network_policy_label(),
                **runner_process.metadata,
            },
        }
        visible = ""
        raw_output = ""
        process_id = ""
        exit_code: int | None = None
        snapshot_id = None
        persisted = False
        start_time = time.monotonic()

        try:
            snapshot = self.file_changes.create_snapshot(workspace_path, f"cloud:{session.id}:{assistant_msg_id}")
            snapshot_id = snapshot.snapshot_id
        except Exception:
            metadata["snapshotError"] = "执行前 cloud workspace 快照创建失败"

        try:
            runtime_run.status = "running"
            runtime_run.started_at = china_now()
            sandbox.status = "running"
            await self.db.commit()
            run = await run_service.mark_run_status(run.id, "running")
            yield self._run_status_changed(run)

            async with asyncio.timeout(QuotaService(self.db).runtime_seconds_limit):
                async for event in self.cli_agents.stream(
                    agent=runtime_agent,
                    session_id=session.id,
                    runtime_session_id=f"cloud:{sandbox.id}:{run.id}",
                    workspace_path=workspace_path,
                    messages=adapter_messages,
                    system_prompt=system_prompt,
                    persistent_process=use_persistent_process,
                ):
                    process_id = event.process_id or process_id
                    if event.type == "agent.metadata":
                        if event.metadata:
                            metadata.update(_redact_json(event.metadata, redactor))
                        continue
                    if event.type == "agent.process.started":
                        await self._log(run.id, next_sequence(), "system", f"process {process_id} started", redactor)
                        metadata["processId"] = process_id
                        trace.set_process(process_id)
                        trace_item = trace.add(
                            kind="process",
                            text=f"{agent.name} 已启动云端 CLI 进程",
                            source="system",
                            chunk_type="process",
                            process_id=process_id,
                            trace={
                                "title": f"{agent.name} 已启动",
                                "detail": "云端 Runtime 已进入真实 CLI 进程执行阶段。",
                                "action": "start",
                                "level": "info",
                            },
                        )
                        run = await run_service.bind_current_message(run.id, assistant_msg_id)
                        task = await run_service.mark_task_status(
                            task.id,
                            "running",
                            message_id=assistant_msg_id,
                        )
                        yield self._task_status_changed(run.id, task)
                        await run_service.bind_process(
                            run_id=run.id,
                            task_id=task.id,
                            session_id=session.id,
                            agent_id=agent.id,
                            message_id=assistant_msg_id,
                            process_id=process_id,
                            snapshot={
                                "executable": agent.executable,
                                "cwd": project.workspace_path,
                            },
                        )
                        yield self._run_status_changed(run)
                        if trace_item:
                            yield self._trace_delta(session.id, agent, assistant_msg_id, process_id, trace_item)
                        yield self._process_started(session.id, agent, assistant_msg_id, process_id, sandbox)
                        continue
                    if event.type == "agent.output":
                        chunk = redactor.redact(event.chunk)
                        raw_output += chunk
                        if event.chunk_type in {"text", "artifact_signal"}:
                            visible += chunk
                        await self._log(run.id, next_sequence(), "stdout", chunk, redactor)
                        trace_item = trace.add(
                            kind="output" if event.chunk_type == "text" else event.chunk_type,
                            text=chunk,
                            source="cli",
                            chunk_type=event.chunk_type,
                            process_id=process_id,
                            trace=_redact_json(event.trace, redactor),
                        )
                        if trace_item and event.chunk_type != "text":
                            yield self._trace_delta(session.id, agent, assistant_msg_id, process_id, trace_item)
                        if event.chunk_type == "text":
                            for token in iter_stream_pieces(chunk):
                                yield self._agent_output(
                                    session.id, agent, assistant_msg_id, process_id,
                                    token, event.chunk_type, token,
                                )
                        else:
                            yield self._agent_output(
                                session.id, agent, assistant_msg_id, process_id,
                                chunk, event.chunk_type, "",
                            )
                        continue
                    if event.type == "interactive_prompt":
                        runtime_run.status = "waiting_input"
                        await self.db.commit()
                        prompt = redactor.redact(event.chunk)
                        await self._log(run.id, next_sequence(), "system", prompt, redactor)
                        yield self._sse({
                            "type": "interactive_prompt",
                            "sessionId": session.id,
                            "agentId": agent.id,
                            "agentName": agent.name,
                            "messageId": assistant_msg_id,
                            "processId": process_id,
                            "content": prompt,
                            "promptType": event.prompt_type,
                            "token": "",
                            "done": False,
                        })
                        continue
                    if event.type in {"agent.process.timeout", "error"}:
                        error = redactor.redact(event.error or "CLI Agent 执行失败")
                        await self._log(run.id, next_sequence(), "stderr", error, redactor)
                        trace_item = trace.add(kind="error", text=error, process_id=process_id)
                        if trace_item:
                            yield self._trace_delta(session.id, agent, assistant_msg_id, process_id, trace_item)
                        trace.complete(status="error", exit_code=exit_code)
                        metadata["error"] = error
                        if not replace_existing:
                            await self._persist_assistant(
                                session,
                                agent,
                                assistant_msg_id,
                                visible or f"CLI Agent 执行失败：{error}",
                                self._run_metadata(
                                    merge_trace_metadata(metadata, trace),
                                    run_id=run.id,
                                    task_id=task.id,
                                    run_status="failed",
                                ),
                            )
                            persisted = True
                        await self._mark_failed(run_service, runtime_run, run.id, task.id, assistant_msg_id, error, process_id, exit_code)
                        await self._dispose_sandbox(sandbox, run.id, reason=error)
                        yield self._run_status_changed(await run_service.get_run(run.id))
                        yield self._err(error, message_id=assistant_msg_id)
                        return
                    if event.type in {"agent.process.completed", "agent.process.turn_completed"}:
                        exit_code = event.exit_code
                        await self._log(run.id, next_sequence(), "system", f"process completed exitCode={exit_code}", redactor)
                        if process_id:
                            await run_service.complete_process(
                                process_id,
                                exit_code=exit_code,
                                run_id=run.id,
                                task_id=task.id,
                                message_id=assistant_msg_id,
                            )
                        status = "completed" if exit_code in (0, None) else "error"
                        trace_item = trace.add(
                            kind="process",
                            text=f"{agent.name} 已结束，exit code: {exit_code}",
                            source="system",
                            chunk_type="process",
                            process_id=process_id,
                            trace={
                                "title": f"{agent.name} 已结束",
                                "detail": "exit code: 0" if exit_code in (0, None) else f"exit code: {exit_code}",
                                "action": "complete",
                                "level": "success" if exit_code in (0, None) else "error",
                            },
                        )
                        trace.complete(status=status, exit_code=exit_code)
                        if trace_item:
                            yield self._trace_delta(session.id, agent, assistant_msg_id, process_id, trace_item)
                        yield self._process_completed(session.id, agent, assistant_msg_id, process_id, exit_code)
                        break
        except TimeoutError:
            await provider.cancel(sandbox, run_id=run.id, reason="timeout")
            await cli_runtime_registry.terminate_session(session.id)
            error = _cloud_timeout_error(QuotaService(self.db).runtime_seconds_limit)
            await self._log(run.id, next_sequence(), "stderr", error, redactor)
            metadata["error"] = error
            trace.complete(status="error", exit_code=exit_code)
            if not replace_existing:
                await self._persist_assistant(
                    session,
                    agent,
                    assistant_msg_id,
                    visible or "云端运行超时，已中止 CLI 进程。",
                    self._run_metadata(
                        merge_trace_metadata(metadata, trace),
                        run_id=run.id,
                        task_id=task.id,
                        run_status="failed",
                    ),
                )
                persisted = True
            await self._mark_failed(
                run_service,
                runtime_run,
                run.id,
                task.id,
                assistant_msg_id,
                error,
                process_id,
                exit_code,
                runtime_status="timed_out",
            )
            await self._dispose_sandbox(sandbox, run.id, reason=error)
            yield self._err(error, message_id=assistant_msg_id)
            return
        except Exception as exc:
            error = redactor.redact(f"{type(exc).__name__}: {exc}")
            await self._log(run.id, next_sequence(), "stderr", error, redactor)
            metadata["error"] = error
            trace.complete(status="error", exit_code=exit_code)
            if not replace_existing:
                await self._persist_assistant(
                    session,
                    agent,
                    assistant_msg_id,
                    visible or f"CLI Agent 执行失败：{error}",
                    self._run_metadata(
                        merge_trace_metadata(metadata, trace),
                        run_id=run.id,
                        task_id=task.id,
                        run_status="failed",
                    ),
                )
                persisted = True
            await self._mark_failed(run_service, runtime_run, run.id, task.id, assistant_msg_id, error, process_id, exit_code)
            await self._dispose_sandbox(sandbox, run.id, reason=error)
            yield self._err(error, message_id=assistant_msg_id)
            return

        run = await run_service.get_run(run.id)
        if run.status == "cancelled":
            runtime_run.status = "cancelled"
            runtime_run.finished_at = runtime_run.finished_at or china_now()
            await self.db.commit()
            await self._dispose_sandbox(sandbox, run.id, reason="cancelled")
            yield self._run_status_changed(run)
            yield self._sse({"token": "", "done": True, "messageId": assistant_msg_id, "agentName": agent.name})
            return

        if exit_code not in (0, None):
            runtime_limit = QuotaService(self.db).runtime_seconds_limit
            if _looks_like_runtime_timeout(exit_code, start_time, runtime_limit):
                error = _cloud_timeout_error(runtime_limit)
                runtime_status = "timed_out"
            else:
                error = f"CLI 进程异常退出（exit code: {exit_code}）"
                runtime_status = "failed"
            metadata["error"] = error
            if not replace_existing:
                await self._persist_assistant(
                    session,
                    agent,
                    assistant_msg_id,
                    visible or error,
                    self._run_metadata(
                        merge_trace_metadata(metadata, trace),
                        run_id=run.id,
                        task_id=task.id,
                        run_status="failed",
                    ),
                )
                persisted = True
            await self._mark_failed(
                run_service,
                runtime_run,
                run.id,
                task.id,
                assistant_msg_id,
                error,
                process_id,
                exit_code,
                runtime_status=runtime_status,
            )
            await self._dispose_sandbox(sandbox, run.id, reason=error)
            yield self._run_status_changed(await run_service.get_run(run.id))
            yield self._err(error, message_id=assistant_msg_id)
            return

        if raw_output and raw_output != visible:
            metadata["rawOutputPreview"] = raw_output[-4000:]
        final_metadata = self._run_metadata(
            merge_trace_metadata(metadata, trace),
            run_id=run.id,
            task_id=task.id,
            run_status="running",
        )
        if not persisted:
            await self._persist_assistant(
                session,
                agent,
                assistant_msg_id,
                visible,
                final_metadata,
                replace_existing=replace_existing,
                previous_content=previous_content,
            )
        async for bridge_event in self._scan_artifacts(
            session=session,
            message_id=assistant_msg_id,
            agent=agent,
            process_id=process_id,
            workspace_path=workspace_path,
            visible=visible,
            raw_output=raw_output,
            metadata=final_metadata,
            snapshot_id=snapshot_id,
        ):
            yield bridge_event

        yield self._sse({
            "type": "workspace.sync.started",
            "workspaceId": sandbox.workspace_id,
            "sandboxId": sandbox.id,
            "runId": run.id,
            "token": "",
            "done": False,
        })
        sync = await self._sync_workspace(
            runtime_run=runtime_run,
            sandbox=sandbox,
            run_id=run.id,
            workspace_path=workspace_path,
            snapshot_id=snapshot_id,
            redactor=redactor,
            next_sequence=next_sequence,
        )
        metadata["workspaceSync"] = {
            "changedFiles": sync.changed_files,
            "diskBytes": sync.disk_bytes,
        }
        yield self._sse({
            "type": "workspace.sync.completed",
            "workspaceId": sandbox.workspace_id,
            "sandboxId": sandbox.id,
            "runId": run.id,
            "changedFiles": sync.changed_files,
            "diskBytes": sync.disk_bytes,
            "token": "",
            "done": False,
        })

        task = await run_service.mark_task_status(task.id, "completed", message_id=assistant_msg_id)
        yield self._task_status_changed(run.id, task)
        run = await run_service.mark_run_status(run.id, "completed", current_message_id=assistant_msg_id)
        runtime_run.status = "completed"
        runtime_run.finished_at = china_now()
        await self.db.commit()
        await self._dispose_sandbox(sandbox, run.id, reason="run completed")
        yield self._sandbox_event("sandbox.disposed", sandbox)
        yield self._run_status_changed(run)
        await QuotaService(self.db, event_bus=self.event_bus).record_runtime_seconds(
            actor,
            int(max(0, time.monotonic() - start_time)),
        )
        yield self._sse({
            "token": "",
            "done": True,
            "messageId": assistant_msg_id,
            "agentName": agent.name,
        })

    async def _create_user_message(
        self,
        session: DBSession,
        content: str,
        *,
        parent_message_id: str | None,
        metadata: dict | None,
    ) -> Message:
        SessionService.clear_unread(session)
        message = Message(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role="user",
            content=content,
            content_type="text",
            source_type="user",
            source_name="用户",
            parent_message_id=parent_message_id,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def _message_for_run(self, session: DBSession, data: SessionRunCreate) -> Message:
        if data.message_id:
            message = await self.db.get(Message, data.message_id)
            if not message or message.session_id != session.id:
                raise CloudRuntimeError("message not found")
            return message
        content = (data.content or "").strip()
        if not content:
            raise CloudRuntimeError("messageId or content is required")
        return await self._create_user_message(session, content, parent_message_id=None, metadata=None)

    async def _agent_for_message(self, message: Message, session: DBSession) -> AgentConfig | None:
        if message.source_id:
            agent = await self.db.get(AgentConfig, message.source_id)
            if agent:
                return agent
        if session.agent_config_id:
            return await self.db.get(AgentConfig, session.agent_config_id)
        return None

    async def _previous_user_message(self, message: Message) -> Message | None:
        filters = [Message.session_id == message.session_id, Message.role == "user"]
        if message.created_at:
            filters.append(Message.created_at < message.created_at)
        result = await self.db.execute(
            select(Message)
            .where(*filters)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def _group_runtime_agents(self, session: DBSession, mentions: list[str] | None) -> list[AgentConfig]:
        mentioned = {str(item) for item in mentions or [] if str(item).strip()}
        result = await self.db.execute(
            select(SessionMember)
            .where(SessionMember.session_id == session.id)
            .order_by(SessionMember.joined_at.asc())
        )
        member_ids = [member.agent_config_id for member in result.scalars().all()]
        if not member_ids and session.agent_config_id:
            member_ids = [session.agent_config_id]

        agents: list[AgentConfig] = []
        seen: set[str] = set()
        for agent_id in member_ids:
            if mentioned and agent_id not in mentioned:
                continue
            agent = await self.db.get(AgentConfig, agent_id)
            if not agent or not agent.is_active or agent.id in seen:
                continue
            if (agent.primary_skill or "") == "orchestrator_planner":
                continue
            agents.append(agent)
            seen.add(agent.id)
        if not agents and mentioned:
            return await self._group_runtime_agents(session, None)
        return agents

    def _group_stream_item(self, item: str, agent: AgentConfig) -> str:
        payload = _parse_sse(item)
        if not payload:
            return item
        if payload.get("done") is True and not payload.get("type"):
            payload["type"] = "agent.turn_completed"
            payload["agentId"] = agent.id
            payload["agentName"] = agent.name
            payload["done"] = False
            return self._sse(payload)
        if payload.get("type") == "error":
            payload["agentId"] = agent.id
            payload["agentName"] = agent.name
            payload["done"] = False
            return self._sse(payload)
        return item

    async def _reply_metadata(self, session_id: str, parent_message_id: str | None) -> dict | None:
        if not parent_message_id:
            return None
        parent = await self.db.get(Message, parent_message_id)
        if not parent:
            raise CloudRuntimeError("quoted message not found")
        if parent.session_id != session_id:
            raise CloudRuntimeError("quoted message belongs to another session")
        return build_reply_reference_metadata(parent)

    async def _session_project(self, session_id: str) -> tuple[DBSession, Project]:
        session = await self.db.get(DBSession, session_id)
        if not session:
            raise CloudRuntimeError("session not found")
        if not session.project_id:
            raise CloudRuntimeError("session has no project")
        project = await self.db.get(Project, session.project_id)
        if not project or project.status == "archived":
            raise CloudRuntimeError("project not found")
        return session, project

    def _assemble_prompt(
        self,
        session_id: str,
        history: list[dict],
        pinned_message_ids: list[str],
        fallback_system_prompt: str,
    ) -> tuple[list[dict], str]:
        assembled = self.context_manager.assemble(PromptAssemblyInput(
            session_id=session_id,
            system_prompt=fallback_system_prompt,
            messages=history,
            pinned_message_ids=pinned_message_ids,
            max_tokens=100_000,
        ))
        return _split_system_prompt(assembled.assembled_messages, fallback_system_prompt)

    async def _runtime_agent(
        self,
        agent: AgentConfig,
        *,
        actor: User,
        project: Project,
        workspace_path: str,
    ):
        base_env = _json_dict(agent.env_vars)
        secret_env = await SecretService(self.db).env_for_project(actor=actor, project=project)
        env_vars = {**base_env, **secret_env}
        env_vars = await CliCredentialService(self.db).prepare_env_for_agent(
            agent,
            actor=actor,
            project=project,
            workspace_path=workspace_path,
            env_vars=env_vars,
        )
        executable = _native_cli_executable(agent)
        init_args = _native_cli_init_args(agent)
        return SimpleNamespace(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            rules=agent.rules,
            agent_type=agent.agent_type,
            cli_tool=agent.cli_tool,
            executable=executable,
            init_args=init_args,
            env_vars=json.dumps(env_vars, ensure_ascii=False),
            primary_skill=agent.primary_skill,
            auxiliary_skills=agent.auxiliary_skills,
            toolset=agent.toolset,
            context_policy=agent.context_policy,
        )

    async def _persist_assistant(
        self,
        session: DBSession,
        agent: AgentConfig,
        message_id: str,
        content: str,
        metadata: dict,
        *,
        replace_existing: bool = False,
        previous_content: str | None = None,
    ) -> None:
        if replace_existing:
            message = await self.db.get(Message, message_id)
            if not message or message.session_id != session.id or message.role != "assistant":
                raise CloudRuntimeError("message not found")
            existing_metadata = _metadata_dict(message)
            if previous_content is not None:
                versions = list(existing_metadata.get("versions", []))
                versions.append({
                    "content": previous_content,
                    "createdAt": china_now().isoformat(),
                    "reason": "regenerate",
                })
                existing_metadata["versions"] = versions[-5:]
            existing_metadata.update(metadata)
            message.content = content
            message.content_type = "text"
            message.agent_name = agent.name
            message.source_type = "agent"
            message.source_id = agent.id
            message.source_name = agent.name
            message.metadata_json = json.dumps(existing_metadata, ensure_ascii=False)
            session.updated_at = china_now()
            SessionService.increment_unread(session)
            await self.db.commit()
            return

        self.db.add(Message(
            id=message_id,
            session_id=session.id,
            role="assistant",
            content=content,
            content_type="text",
            agent_name=agent.name,
            source_type="agent",
            source_id=agent.id,
            source_name=agent.name,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ))
        session.updated_at = china_now()
        SessionService.increment_unread(session)
        await self.db.commit()

    async def _scan_artifacts(
        self,
        *,
        session: DBSession,
        message_id: str,
        agent: AgentConfig,
        process_id: str,
        workspace_path: str,
        visible: str,
        raw_output: str,
        metadata: dict,
        snapshot_id: str | None,
    ) -> AsyncGenerator[str, None]:
        message = await self.db.get(Message, message_id)
        if not message or not session.project_id:
            return
        yield self._sse({
            "type": "artifact.scan.started",
            "sessionId": session.id,
            "messageId": message_id,
            "projectId": session.project_id,
            "agentId": agent.id,
            "agentName": agent.name,
            "processId": process_id,
            "token": "",
            "done": False,
        })
        try:
            result = await ArtifactOutputBridge(self.db, event_bus=self.event_bus).scan_completed_message(
                session=session,
                message=message,
                workspace_path=workspace_path,
                visible_content=visible,
                raw_output_preview=raw_output[-4000:] if raw_output else "",
                execution_trace=metadata.get("executionTrace") if isinstance(metadata.get("executionTrace"), dict) else None,
                snapshot_id=snapshot_id,
            )
            for artifact in result.created:
                payload = artifact_to_event_payload(artifact)
                yield self._sse({
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
            yield self._sse({
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
        except Exception as exc:
            yield self._sse({
                "type": "artifact.detection_failed",
                "sessionId": session.id,
                "messageId": message_id,
                "projectId": session.project_id,
                "reason": f"{type(exc).__name__}: {exc}",
                "recoverable": True,
                "token": "",
                "done": False,
            })

    async def _mark_failed(
        self,
        run_service: RunService,
        runtime_run: RuntimeRun,
        run_id: str,
        task_id: str,
        message_id: str,
        error: str,
        process_id: str,
        exit_code: int | None,
        runtime_status: str = "failed",
    ) -> None:
        if process_id:
            await run_service.complete_process(
                process_id,
                exit_code=exit_code,
                status="failed",
                run_id=run_id,
                task_id=task_id,
                message_id=message_id,
            )
        await run_service.mark_task_status(task_id, "failed", message_id=message_id, metadata_patch={"error": error})
        await run_service.mark_run_status(run_id, "failed", current_message_id=message_id)
        runtime_run.status = runtime_status
        runtime_run.finished_at = china_now()
        runtime_run.error_summary = error[:500]
        await self.db.commit()

    async def _sync_workspace(
        self,
        *,
        runtime_run: RuntimeRun,
        sandbox: Sandbox,
        run_id: str,
        workspace_path: str,
        snapshot_id: str | None,
        redactor: SecretRedactor,
        next_sequence,
    ):
        runtime_run.status = "syncing"
        sandbox.status = "syncing"
        await self.db.commit()
        await self._publish(EventType.WORKSPACE_SYNC_STARTED, {
            "workspaceId": sandbox.workspace_id,
            "sandboxId": sandbox.id,
            "runId": run_id,
        })
        changed_files: list[dict[str, Any]] = []
        if snapshot_id:
            try:
                changed_files = self.file_changes.diff_from_snapshot(workspace_path, snapshot_id)
            except Exception:
                changed_files = []
        result = collect_workspace_sync(workspace_path, changed_files)
        await ensure_workspace_volume(self.db, sandbox.workspace_id, provider=sandbox.provider or "local_dev")
        runtime_run.sync_completed_at = china_now()
        await self._log(
            run_id,
            next_sequence(),
            "system",
            f"workspace sync completed: {len(result.changed_files)} files",
            redactor,
        )
        await self._publish(EventType.WORKSPACE_SYNC_COMPLETED, {
            "workspaceId": sandbox.workspace_id,
            "sandboxId": sandbox.id,
            "runId": run_id,
            "changedFiles": result.changed_files,
        })
        return result

    async def _dispose_sandbox(self, sandbox: Sandbox, run_id: str, *, reason: str) -> None:
        await cli_runtime_registry.terminate_session(f"cloud:{sandbox.id}:{run_id}")
        await SandboxService(self.db, event_bus=self.event_bus).mark_stopped(
            sandbox,
            run_id=run_id,
            reason=reason,
        )

    async def _log(self, run_id: str, sequence: int, stream: str, text: str, redactor: SecretRedactor) -> None:
        clean_text = redactor.redact(text)
        self.db.add(RuntimeLog(
            id=str(uuid.uuid4()),
            run_id=run_id,
            sequence=sequence,
            stream=stream,
            text=clean_text,
        ))
        await self.db.commit()
        await self._publish(EventType.RUNTIME_LOG, {
            "runId": run_id,
            "sequence": sequence,
            "stream": stream,
            "text": clean_text,
        })

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)

    @staticmethod
    def _run_metadata(metadata: dict, *, run_id: str, task_id: str, run_status: str) -> dict:
        metadata["runId"] = run_id
        metadata["taskId"] = task_id
        metadata["runStatus"] = run_status
        return metadata

    def _sandbox_event(self, event_type: str, sandbox: Sandbox) -> str:
        payload = sandbox_to_read(sandbox).model_dump(by_alias=True, mode="json")
        return self._sse({
            "type": event_type,
            "sandboxId": sandbox.id,
            "workspaceId": sandbox.workspace_id,
            "sandbox": payload,
            "token": "",
            "done": False,
        })

    def _task_status_changed(self, run_id: str, task) -> str:
        return self._sse({
            "type": "task.status_changed",
            "runId": run_id,
            "taskId": task.id,
            "sessionId": task.session_id,
            "status": task.status,
            "task": task_to_read(task).model_dump(by_alias=True, mode="json"),
            "token": "",
            "done": False,
        })

    def _run_status_changed(self, run) -> str:
        return self._sse({
            "type": "run.status_changed",
            "runId": run.id,
            "sessionId": run.session_id,
            "status": run.status,
            "updatedAt": run.updated_at.isoformat() if run.updated_at else "",
            "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
            "token": "",
            "done": False,
        })

    def _process_started(
        self,
        session_id: str,
        agent: AgentConfig,
        message_id: str,
        process_id: str,
        sandbox: Sandbox,
    ) -> str:
        return self._sse({
            "type": "agent.process.started",
            "sessionId": session_id,
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "processId": process_id,
            "sandboxId": sandbox.id,
            "runtimeMode": "cloud",
            "token": "",
            "done": False,
        })

    def _agent_output(
        self,
        session_id: str,
        agent: AgentConfig,
        message_id: str,
        process_id: str,
        chunk: str,
        chunk_type: str,
        token: str,
    ) -> str:
        return self._sse({
            "type": "agent.output",
            "sessionId": session_id,
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "processId": process_id,
            "runtimeMode": "cloud",
            "chunk": chunk,
            "chunkType": chunk_type,
            "token": token,
            "done": False,
        })

    def _trace_delta(
        self,
        session_id: str,
        agent: AgentConfig,
        message_id: str,
        process_id: str,
        item: dict,
    ) -> str:
        return self._sse({
            "type": "agent.trace.delta",
            "sessionId": session_id,
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "processId": process_id,
            "item": item,
            "runtimeMode": "cloud",
            "token": "",
            "done": False,
        })

    def _process_completed(
        self,
        session_id: str,
        agent: AgentConfig,
        message_id: str,
        process_id: str,
        exit_code: int | None,
    ) -> str:
        return self._sse({
            "type": "agent.process.completed",
            "sessionId": session_id,
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "processId": process_id,
            "runtimeMode": "cloud",
            "exitCode": exit_code,
            "token": "",
            "done": False,
        })

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    @staticmethod
    def _err(msg: str, message_id: str | None = None) -> str:
        data = {"type": "error", "token": "", "done": True, "error": msg}
        if message_id:
            data["messageId"] = message_id
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _json_dict(raw: str | None) -> dict[str, str]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if str(k)}


def _native_cli_executable(agent: AgentConfig) -> str:
    cli_tool = str(agent.cli_tool or "")
    default = DEFAULT_CLI_AGENTS.get(cli_tool)
    executable = str(agent.executable or "").strip()
    if default and not executable:
        return str(default.get("executable") or "")
    return executable


def _native_cli_init_args(agent: AgentConfig) -> str:
    cli_tool = str(agent.cli_tool or "")
    raw = agent.init_args
    if cli_tool not in DEFAULT_CLI_AGENTS:
        return raw or "[]"
    args = _json_list(raw)
    if args:
        return raw or json.dumps(args, ensure_ascii=False)
    return json.dumps(DEFAULT_CLI_AGENTS[cli_tool].get("init_args", []), ensure_ascii=False)


def _cloud_persistent_process_supported(
    agent: Any,
    runner_metadata: dict[str, Any],
    cli_agents: CliAgentService,
) -> bool:
    """云端持久进程策略必须同时满足 adapter 能力与 runner 包裹命令兼容性。"""
    if not cli_agents.supports_persistent_process(agent):
        return False
    provider = str(runner_metadata.get("provider") or "").strip()
    if provider == "local_dev":
        return True
    if not bool(getattr(agent, "prepared_invocation", False)):
        return True
    # Docker/SSH Docker 会把 CLI 包成外层命令。OpenCode ACP 沿用既有云端持久路径；
    # Codex MCP 已适配当前线上使用的本机 Docker 参数包裹；Claude stdio helper 仍按裸 CLI 参数解析。
    cli_tool = str(getattr(agent, "cli_tool", "") or "")
    if cli_tool == "opencode":
        return True
    return provider == "docker" and cli_tool == "codex"


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _parse_sse(item: str) -> dict[str, Any] | None:
    if not item.startswith("data: "):
        return None
    try:
        value = json.loads(item[6:])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _cloud_timeout_error(runtime_limit: int) -> str:
    return f"云端运行超时（{runtime_limit} 秒），已中止 CLI 进程。"


def _looks_like_runtime_timeout(exit_code: int | None, start_time: float, runtime_limit: int) -> bool:
    if exit_code not in {143, -15}:
        return False
    return time.monotonic() - start_time >= max(0, runtime_limit - 5)


def _metadata_dict(message: Message) -> dict[str, Any]:
    raw = getattr(message, "metadata_json", None)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _redact_json(value: Any, redactor: SecretRedactor) -> Any:
    if isinstance(value, str):
        return redactor.redact(value)
    if isinstance(value, list):
        return [_redact_json(item, redactor) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_json(item, redactor) for key, item in value.items()}
    return value


def _network_policy_label() -> str:
    value = (settings.agenthub_runner_network_policy or "").strip().lower()
    return "bridge" if value == "bridge" else "none"
