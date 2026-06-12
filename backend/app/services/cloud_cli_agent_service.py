"""云端 CLI Agent 事件适配层。

本服务把云端 sandbox/runner 的准备、配额、Secret、workspace 同步封装起来，
对上层仍然暴露桌面端已使用的 CliAgentService 事件接口。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from types import SimpleNamespace
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.cli_defaults import DEFAULT_CLI_AGENTS
from ..agents.cli_events import CliEvent
from ..agents.cli_runtime_registry import cli_runtime_registry
from ..core.timezone import china_now
from ..event_bus.event_types import EventType
from ..models import AgentConfig, Project, RuntimeLog, RuntimeRun, Sandbox, User
from .cli_agent_service import CliAgentService
from .cli_credential_service import CliCredentialRequiredError, CliCredentialService
from .file_change_detector import FileChangeDetector
from .quota_service import QuotaExceededError, QuotaService
from .runner_provider import (
    collect_workspace_sync,
    ensure_workspace_volume,
    get_runner_provider,
    workspace_path_for_sandbox,
)
from .sandbox_service import SandboxNotFoundError, SandboxService
from .secret_service import SecretRedactor, SecretService


DOCUMENT_RUNTIME_CONTEXT = """
<agenthub_cloud_runtime>
当前云端 Runtime 面向真实 CLI Agent 执行，工作目录就是当前 Project 的云端 workspace。
生成文档、表格、演示稿、PDF 或图片时，请直接把文件写入 workspace，并在回复里给出相对路径。
Runtime Image 应预装 python3、python-docx、pandoc 与 LibreOffice Writer；生成 .docx 时优先使用 python-docx。
不要为了常见文档格式在任务中临时执行长时间 pip install / apt install；如果依赖缺失，请使用标准库降级生成 OOXML，或明确报告运行时缺失。
</agenthub_cloud_runtime>
""".strip()


class CloudCliAgentService:
    """让桌面群聊编排器以标准 CliEvent 驱动云端真实 CLI。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        actor: User,
        project: Project,
        event_bus: Any = None,
        base_cli_agents: CliAgentService | None = None,
    ):
        self.db = db
        self.actor = actor
        self.project = project
        self.event_bus = event_bus
        self._base = base_cli_agents or CliAgentService(event_bus=event_bus)
        self._file_changes = FileChangeDetector()

    def supports_engine_session_resume(self, agent: AgentConfig) -> bool:
        return self._base.supports_engine_session_resume(agent)

    def engine_session_resume_policy(self, agent: AgentConfig):
        return self._base.engine_session_resume_policy(agent)

    def supports_persistent_process(self, agent: AgentConfig) -> bool:
        if str(getattr(agent, "cli_tool", "") or "") == "codex":
            return False
        return self._base.supports_persistent_process(agent)

    def persistent_process_policy(self, agent: AgentConfig):
        return self._base.persistent_process_policy(agent)

    def execution_workspace_path(self, workspace_path: str, **_: Any) -> str:
        return workspace_path

    def metadata_workspace_path(self, workspace_path: str, **_: Any) -> str:
        return self.project.workspace_path or workspace_path

    async def stream(
        self,
        *,
        agent: AgentConfig,
        session_id: str,
        runtime_session_id: str | None = None,
        workspace_path: str,
        messages: list[dict],
        system_prompt: str,
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
        persistent_process: bool = False,
    ) -> AsyncIterator[CliEvent]:
        del workspace_path
        if not self.project.workspace_id:
            yield CliEvent("error", "", error="cloud workspace not found")
            return
        try:
            await CliCredentialService(self.db).assert_ready_for_agent(
                agent,
                actor=self.actor,
                project=self.project,
            )
            await QuotaService(self.db, event_bus=self.event_bus).assert_can_start(self.actor)
            sandbox = await SandboxService(self.db, event_bus=self.event_bus).reuse_or_create(
                workspace_id=self.project.workspace_id,
                actor=self.actor,
            )
        except (CliCredentialRequiredError, QuotaExceededError, SandboxNotFoundError) as exc:
            yield CliEvent("error", "", error=str(exc))
            return

        provider = get_runner_provider()
        workspace = workspace_path_for_sandbox(sandbox)
        runtime_run = RuntimeRun(
            id=f"rt_{uuid.uuid4().hex}",
            session_id=session_id,
            agent_id=agent.id,
            actor_user_id=self.actor.id,
            sandbox_id=sandbox.id,
            runtime_mode="cloud",
            status="queued",
            queued_at=china_now(),
        )
        self.db.add(runtime_run)
        await self.db.commit()

        redactor = await SecretService(self.db).redactor_for_project(
            actor=self.actor,
            project=self.project,
        )
        sequence = 0

        def next_sequence() -> int:
            nonlocal sequence
            sequence += 1
            return sequence

        await self._log(runtime_run.id, next_sequence(), "system", f"sandbox {sandbox.id} ready", redactor)
        process_id = ""
        exit_code: int | None = None
        snapshot_id: str | None = None
        cli_output_error = ""
        start_time = time.monotonic()
        sync_completed = False

        try:
            runtime_agent = await self._runtime_agent(agent, workspace_path=workspace)
            runner_process = await provider.prepare_process(
                sandbox=sandbox,
                agent=runtime_agent,
                run_id=runtime_run.id,
                workspace_path=workspace,
            )
            runtime_agent = runner_process.agent
            workspace = runner_process.workspace_path
            use_persistent_process = persistent_process and _cloud_persistent_process_supported(
                runtime_agent,
                runner_process.metadata,
                self._base,
            )
            metadata = self._runtime_metadata(
                agent=agent,
                sandbox=sandbox,
                provider_name=provider.name,
                runner_metadata=runner_process.metadata,
                artifact_workspace_path=workspace,
            )
            try:
                snapshot = self._file_changes.create_snapshot(
                    workspace,
                    f"cloud-group:{session_id}:{agent.id}:{runtime_run.id}",
                )
                snapshot_id = snapshot.snapshot_id
                metadata["workspaceSnapshotId"] = snapshot_id
                metadata["snapshotError"] = None
            except Exception:
                metadata["snapshotError"] = "执行前 cloud workspace 快照创建失败"
            yield CliEvent("agent.metadata", "", metadata=metadata)

            runtime_run.status = "running"
            runtime_run.started_at = china_now()
            sandbox.status = "running"
            await self.db.commit()
            await self._publish(EventType.RUNTIME_LOG, {
                "runId": runtime_run.id,
                "sequence": sequence,
                "stream": "system",
                "text": f"sandbox {sandbox.id} ready",
            })

            cloud_runtime_session_id = runtime_session_id or f"cloud:{sandbox.id}:{runtime_run.id}"
            async with asyncio.timeout(QuotaService(self.db).runtime_seconds_limit):
                async for event in self._base.stream(
                    agent=runtime_agent,
                    session_id=session_id,
                    runtime_session_id=f"cloud:{sandbox.id}:{runtime_run.id}:{cloud_runtime_session_id}",
                    workspace_path=workspace,
                    messages=messages,
                    system_prompt=_append_cloud_runtime_context(system_prompt),
                    engine_session_id=engine_session_id,
                    engine_session_mode=engine_session_mode,
                    persistent_process=use_persistent_process,
                ):
                    process_id = event.process_id or process_id
                    if event.type == "agent.metadata":
                        yield CliEvent(
                            event.type,
                            event.process_id,
                            metadata=_sanitize_cloud_metadata(
                                _redact_json(event.metadata or {}, redactor),
                                workspace,
                                self.project.workspace_path or "",
                            ),
                        )
                        continue
                    if event.type == "agent.process.started":
                        await self._log(
                            runtime_run.id,
                            next_sequence(),
                            "system",
                            f"process {event.process_id or process_id} started",
                            redactor,
                        )
                        yield _cloud_event(event, redactor, workspace, self.project.workspace_path or "")
                        continue
                    if event.type == "agent.output":
                        chunk = redactor.redact(event.chunk)
                        if _is_fatal_cli_output(chunk):
                            cli_output_error = chunk
                            await self._log(runtime_run.id, next_sequence(), "stderr", chunk, redactor)
                            runtime_run.status = "failed"
                            runtime_run.finished_at = china_now()
                            runtime_run.error_summary = _fatal_cli_output_message(chunk)[:500]
                            await self.db.commit()
                            yield CliEvent(
                                "error",
                                process_id,
                                error=_fatal_cli_output_message(chunk),
                                trace=_sanitize_cloud_metadata(
                                    _redact_json(event.trace, redactor),
                                    workspace,
                                    self.project.workspace_path or "",
                                ) if event.trace else None,
                            )
                            return
                        if _should_log_cli_output(event.chunk_type):
                            await self._log(
                                runtime_run.id,
                                next_sequence(),
                                "stderr" if event.chunk_type == "error" else "stdout",
                                chunk,
                                redactor,
                            )
                        yield CliEvent(
                            event.type,
                            event.process_id,
                            chunk=chunk,
                            chunk_type=event.chunk_type,
                            exit_code=event.exit_code,
                            error=redactor.redact(event.error or "") or None,
                            prompt_type=event.prompt_type,
                            trace=_sanitize_cloud_metadata(
                                _redact_json(event.trace, redactor),
                                workspace,
                                self.project.workspace_path or "",
                            ) if event.trace else None,
                            metadata=_sanitize_cloud_metadata(
                                _redact_json(event.metadata, redactor),
                                workspace,
                                self.project.workspace_path or "",
                            ) if event.metadata else None,
                        )
                        continue
                    if event.type == "interactive_prompt":
                        runtime_run.status = "waiting_input"
                        await self.db.commit()
                        prompt = redactor.redact(event.chunk)
                        await self._log(runtime_run.id, next_sequence(), "system", prompt, redactor)
                        yield CliEvent(
                            event.type,
                            event.process_id,
                            chunk=prompt,
                            prompt_type=event.prompt_type,
                            trace=_sanitize_cloud_metadata(
                                _redact_json(event.trace, redactor),
                                workspace,
                                self.project.workspace_path or "",
                            ) if event.trace else None,
                        )
                        continue
                    if event.type in {"agent.process.timeout", "error"}:
                        error = redactor.redact(event.error or "CLI Agent 执行失败")
                        await self._log(runtime_run.id, next_sequence(), "stderr", error, redactor)
                        runtime_run.status = "timed_out" if event.type == "agent.process.timeout" else "failed"
                        runtime_run.finished_at = china_now()
                        runtime_run.error_summary = error[:500]
                        await self.db.commit()
                        yield CliEvent(
                            event.type,
                            event.process_id or process_id,
                            error=error,
                            trace=_sanitize_cloud_metadata(
                                _redact_json(event.trace, redactor),
                                workspace,
                                self.project.workspace_path or "",
                            ) if event.trace else None,
                        )
                        return
                    if event.type in {"agent.process.completed", "agent.process.turn_completed"}:
                        exit_code = event.exit_code
                        await self._log(
                            runtime_run.id,
                            next_sequence(),
                            "system",
                            f"process completed exitCode={exit_code}",
                            redactor,
                        )
                        yield _cloud_event(event, redactor, workspace, self.project.workspace_path or "")
                        break
        except TimeoutError:
            await provider.cancel(sandbox, run_id=runtime_run.id, reason="timeout")
            error = _cloud_timeout_error(QuotaService(self.db).runtime_seconds_limit)
            runtime_run.status = "timed_out"
            runtime_run.finished_at = china_now()
            runtime_run.error_summary = error[:500]
            await self.db.commit()
            yield CliEvent("agent.process.timeout", process_id, error=error)
            return
        except Exception as exc:
            error = redactor.redact(f"{type(exc).__name__}: {exc}")
            runtime_run.status = "failed"
            runtime_run.finished_at = china_now()
            runtime_run.error_summary = error[:500]
            await self.db.commit()
            yield CliEvent("error", process_id, error=error)
            return
        finally:
            if not sync_completed:
                terminal_status = (
                    runtime_run.status
                    if runtime_run.status in {"failed", "timed_out", "cancelled"}
                    else None
                )
                try:
                    await self._sync_and_dispose(
                        runtime_run=runtime_run,
                        sandbox=sandbox,
                        run_id=runtime_run.id,
                        workspace_path=workspace,
                        snapshot_id=snapshot_id,
                        redactor=redactor,
                        next_sequence=next_sequence,
                        reason="run completed",
                    )
                    sync_completed = True
                except Exception:
                    pass
                if terminal_status:
                    runtime_run.status = terminal_status
                    runtime_run.finished_at = runtime_run.finished_at or china_now()
                    await self.db.commit()
                await QuotaService(self.db, event_bus=self.event_bus).record_runtime_seconds(
                    self.actor,
                    int(max(0, time.monotonic() - start_time)),
                )

        if cli_output_error:
            yield CliEvent("error", process_id, error=_fatal_cli_output_message(cli_output_error))
            return
        if exit_code not in (0, None):
            error = _cloud_failure_message(exit_code, start_time, QuotaService(self.db).runtime_seconds_limit)
            runtime_run.status = "failed"
            runtime_run.finished_at = china_now()
            runtime_run.error_summary = error[:500]
            await self.db.commit()
            yield CliEvent("error", process_id, error=error)
            return

        runtime_run.status = "completed"
        runtime_run.finished_at = china_now()
        await self.db.commit()

    async def _runtime_agent(self, agent: AgentConfig, *, workspace_path: str):
        base_env = _json_dict(agent.env_vars)
        secret_env = await SecretService(self.db).env_for_project(actor=self.actor, project=self.project)
        env_vars = {**base_env, **secret_env}
        env_vars = await CliCredentialService(self.db).prepare_env_for_agent(
            agent,
            actor=self.actor,
            project=self.project,
            workspace_path=workspace_path,
            env_vars=env_vars,
        )
        return SimpleNamespace(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            rules=agent.rules,
            agent_type=agent.agent_type,
            cli_tool=agent.cli_tool,
            executable=_native_cli_executable(agent),
            init_args=_native_cli_init_args(agent),
            env_vars=json.dumps(env_vars, ensure_ascii=False),
            primary_skill=agent.primary_skill,
            auxiliary_skills=agent.auxiliary_skills,
            toolset=agent.toolset,
            context_policy=agent.context_policy,
        )

    def _runtime_metadata(
        self,
        *,
        agent: AgentConfig,
        sandbox: Sandbox,
        provider_name: str,
        runner_metadata: dict[str, Any],
        artifact_workspace_path: str,
    ) -> dict[str, Any]:
        return {
            "agentType": agent.agent_type or "cli_wrapper",
            "cliTool": agent.cli_tool or "custom",
            "workspacePath": self.project.workspace_path,
            "runtimeMode": "cloud",
            "sandboxId": sandbox.id,
            "workspaceId": self.project.workspace_id,
            "artifactWorkspacePath": artifact_workspace_path,
            "cloudRuntime": {
                "runnerNodeId": sandbox.runner_node_id,
                "image": sandbox.image,
                "provider": sandbox.provider or provider_name,
                "externalId": sandbox.external_id,
                "region": sandbox.region,
                "network": _network_policy_label(),
                **runner_metadata,
            },
        }

    async def _sync_and_dispose(
        self,
        *,
        runtime_run: RuntimeRun,
        sandbox: Sandbox,
        run_id: str,
        workspace_path: str,
        snapshot_id: str | None,
        redactor: SecretRedactor,
        next_sequence,
        reason: str,
    ) -> None:
        runtime_run.status = "syncing"
        sandbox.status = "syncing"
        await self.db.commit()
        changed_files: list[dict[str, Any]] = []
        if snapshot_id:
            try:
                changed_files = self._file_changes.diff_from_snapshot(workspace_path, snapshot_id)
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

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)


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


def _json_dict(raw: str | None) -> dict[str, str]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if str(k)}


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _cloud_persistent_process_supported(
    agent: Any,
    runner_metadata: dict[str, Any],
    cli_agents: CliAgentService,
) -> bool:
    cli_tool = str(getattr(agent, "cli_tool", "") or "")
    if cli_tool == "codex":
        return False
    if not cli_agents.supports_persistent_process(agent):
        return False
    provider = str(runner_metadata.get("provider") or "").strip()
    if provider == "local_dev":
        return True
    if not bool(getattr(agent, "prepared_invocation", False)):
        return True
    return cli_tool == "opencode"


def _append_cloud_runtime_context(system_prompt: str) -> str:
    clean = system_prompt.strip()
    if DOCUMENT_RUNTIME_CONTEXT in clean:
        return clean
    if not clean:
        return DOCUMENT_RUNTIME_CONTEXT
    return f"{clean}\n\n{DOCUMENT_RUNTIME_CONTEXT}"


def _cloud_timeout_error(runtime_limit: int) -> str:
    return f"云端运行超时（{runtime_limit} 秒），已中止 CLI 进程。"


def _cloud_failure_message(exit_code: int | None, start_time: float, runtime_limit: int) -> str:
    if exit_code in {143, -15} and time.monotonic() - start_time >= max(0, min(runtime_limit - 5, runtime_limit * 0.9)):
        return _cloud_timeout_error(runtime_limit)
    return f"CLI 进程异常退出（exit code: {exit_code}）"


def _should_log_cli_output(chunk_type: str) -> bool:
    return chunk_type != "text"


def _is_fatal_cli_output(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return False
    patterns = (
        r"stream disconnected before completion",
        r"concurrency limit exceeded",
        r"cloud runtime concurrent quota exceeded",
        r"separator is not found",
        r"chunk exceed(?:ed)? the limit",
        r"cli rpc .*(通信失败|communication failed)",
    )
    return any(re.search(pattern, clean, re.I) for pattern in patterns)


def _fatal_cli_output_message(text: str) -> str:
    clean = str(text or "").strip()
    return clean or "CLI Agent 执行失败。"


def _network_policy_label() -> str:
    from ..config import settings

    value = (settings.agenthub_runner_network_policy or "").strip().lower()
    return "bridge" if value == "bridge" else "none"


def _redact_json(value: Any, redactor: SecretRedactor) -> Any:
    if isinstance(value, str):
        return redactor.redact(value)
    if isinstance(value, list):
        return [_redact_json(item, redactor) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_json(item, redactor) for key, item in value.items()}
    return value


def _cloud_event(
    event: CliEvent,
    redactor: SecretRedactor,
    physical_workspace: str,
    logical_workspace: str,
) -> CliEvent:
    return CliEvent(
        event.type,
        event.process_id,
        chunk=redactor.redact(event.chunk),
        chunk_type=event.chunk_type,
        exit_code=event.exit_code,
        error=redactor.redact(event.error or "") or None,
        prompt_type=event.prompt_type,
        trace=_sanitize_cloud_metadata(
            _redact_json(event.trace, redactor),
            physical_workspace,
            logical_workspace,
        ) if event.trace else None,
        metadata=_sanitize_cloud_metadata(
            _redact_json(event.metadata, redactor),
            physical_workspace,
            logical_workspace,
        ) if event.metadata else None,
    )


def _sanitize_cloud_metadata(value: Any, physical_workspace: str, logical_workspace: str) -> Any:
    if isinstance(value, str):
        return _sanitize_cloud_text(value, physical_workspace, logical_workspace)
    if isinstance(value, list):
        return [_sanitize_cloud_metadata(item, physical_workspace, logical_workspace) for item in value]
    if isinstance(value, dict):
        sanitized = {
            str(key): _sanitize_cloud_metadata(item, physical_workspace, logical_workspace)
            for key, item in value.items()
        }
        if "target" in sanitized:
            sanitized["target"] = logical_workspace or "cloud workspace"
        if "command" in sanitized:
            sanitized["command"] = _cloud_command_label(str(sanitized.get("command") or ""))
        return sanitized
    return value


def _sanitize_cloud_text(text: str, physical_workspace: str, logical_workspace: str) -> str:
    clean = text
    replacements = {physical_workspace, physical_workspace.replace("/", "\\"), physical_workspace.replace("\\", "/")}
    for item in replacements:
        if item:
            clean = clean.replace(item, logical_workspace or "cloud workspace")
    clean = re.sub(r"[A-Za-z]:\\[^\n`\"']+", "[cloud-runtime-path]", clean)
    clean = re.sub(r"/(?:srv|tmp|home|root|workspace)/[^\n`\"']+", "[cloud-runtime-path]", clean)
    return clean


def _cloud_command_label(command: str) -> str:
    if not command.strip():
        return ""
    return "cloud runtime command"
