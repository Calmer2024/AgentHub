"""Bridge CLI adapter events into AgentExecutor TokenEvent streams."""

from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.execution_planner import AgentCall
from ..agents.cli_trace import trace_text
from .engine_session_service import EngineSessionService
from .execution_trace import utc_iso
from .file_change_detector import FileChangeDetector
from .cli_agent_service import CliAgentService
from .streaming_text import iter_stream_pieces
from .token_event import TokenEvent


class CliAgentCallRunner:
    def __init__(self, db: AsyncSession | None = None, event_bus=None, cli_agents: CliAgentService | None = None):
        self.db = db
        self._cli_agents = cli_agents or CliAgentService(event_bus=event_bus)
        self._file_changes = FileChangeDetector()

    async def execute(
        self,
        call: AgentCall,
        *,
        session_id: str,
        workspace_path: str,
    ) -> AsyncIterator[TokenEvent]:
        agent = call.agent
        msg_id = f"agent-{agent.id}"
        meta = self._metadata(call)
        system_prompt = agent.system_prompt or ""
        if call.role_prompt_override:
            system_prompt = f"{system_prompt}\n\n{call.role_prompt_override}"

        execution_workspace_path = _service_path(
            self._cli_agents,
            "execution_workspace_path",
            workspace_path,
            session_id=session_id,
            agent=agent,
        )
        metadata_workspace_path = _service_path(
            self._cli_agents,
            "metadata_workspace_path",
            workspace_path,
            session_id=session_id,
            agent=agent,
        )
        cli_tool = agent.cli_tool or "custom"
        resume_policy = self._cli_agents.engine_session_resume_policy(agent)
        supports_persistent_process = self._cli_agents.supports_persistent_process(agent)
        runtime_session_id = _runtime_session_id(session_id, agent.id)
        engine_invocation = None
        if self.db:
            engine_invocation = await EngineSessionService(self.db).resolve_invocation(
                session_id=session_id,
                agent_config_id=agent.id,
                cli_tool=cli_tool,
                workspace_path=metadata_workspace_path,
                supported=resume_policy.supported,
                caller_assigned_id=resume_policy.caller_assigned_id,
            )
        adapter_messages = (
            _resume_delta_messages(call.input_messages)
            if engine_invocation and engine_invocation.is_resume
            else call.input_messages
        )
        runtime_mode = (
            "persistent_process"
            if supports_persistent_process
            else "engine_session_resume" if resume_policy.supported else "oneshot_process"
        )
        call_meta = {
            **meta,
            "agentType": agent.agent_type or "cli_wrapper",
            "cliTool": cli_tool,
            "workspacePath": metadata_workspace_path,
            "engineRuntime": {
                "mode": runtime_mode,
                "processScope": "one_group_session_agent_one_process"
                if supports_persistent_process else "per_turn_process",
                "turnIsolation": "session_agent_lock"
                if supports_persistent_process else "request_stream",
                "runtimeSessionId": runtime_session_id if supports_persistent_process else None,
            },
            "engineSessionPolicy": {
                "supported": resume_policy.supported,
                "strategy": resume_policy.strategy,
                "startStrategy": resume_policy.start_strategy,
                "idSource": resume_policy.id_source,
                "callerAssignedId": resume_policy.caller_assigned_id,
            },
        }
        if engine_invocation and engine_invocation.engine_session_id:
            call_meta["engineSession"] = {
                "mode": engine_invocation.mode,
                "id": engine_invocation.engine_session_id,
                "adapter": cli_tool,
                "strategy": (
                    resume_policy.strategy
                    if engine_invocation.is_resume else resume_policy.start_strategy
                ),
            }
            if engine_invocation.assigned_by_agenthub:
                call_meta["engineSession"]["source"] = "agenthub_assigned"

        snapshot_id = None
        try:
            snapshot = self._file_changes.create_snapshot(
                execution_workspace_path,
                f"group-chat:{session_id}:{agent.id}:{call.task}",
            )
            snapshot_id = snapshot.snapshot_id
            call_meta["workspaceSnapshotId"] = snapshot_id
        except Exception:
            call_meta["snapshotError"] = "执行前 workspace 快照创建失败"

        full = ""
        exit_code = None
        engine_session_remembered = False
        async for event in self._cli_agents.stream(
            agent=agent,
            session_id=session_id,
            runtime_session_id=runtime_session_id,
            workspace_path=execution_workspace_path,
            messages=adapter_messages,
            system_prompt=system_prompt,
            engine_session_id=(
                engine_invocation.engine_session_id if engine_invocation else None
            ),
            engine_session_mode=engine_invocation.mode if engine_invocation else "resume",
            persistent_process=supports_persistent_process,
        ):
            if event.type == "agent.metadata":
                _merge_metadata(call_meta, event.metadata)
                remembered = await self._remember_engine_session_from_event(
                    event,
                    call_meta,
                    session_id=session_id,
                    agent_id=agent.id,
                    cli_tool=cli_tool,
                    workspace_path=metadata_workspace_path,
                    resume_policy=resume_policy,
                )
                engine_session_remembered = engine_session_remembered or remembered
                continue

            event_meta = {**call_meta, "processId": event.process_id}
            if event.type == "agent.process.started":
                runtime_metadata = event.metadata or {}
                if runtime_metadata:
                    event_meta["engineRuntime"] = {
                        **dict(call_meta.get("engineRuntime") or {}),
                        **{
                            key: runtime_metadata[key]
                            for key in (
                                "persistentProcess",
                                "persistentProtocol",
                                "reused",
                                "recovered",
                                "engineSessionMode",
                                "engineSessionId",
                            )
                            if key in runtime_metadata
                        },
                    }
                yield TokenEvent(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    event_type="agent.process.started",
                    metadata={
                        **event_meta,
                        "sessionId": session_id,
                        "trace": _trace_item(event, "process"),
                    },
                )
                continue

            if event.type == "agent.output":
                if event.chunk_type == "progress":
                    yield TokenEvent(
                        agent_id=agent.id,
                        agent_name=agent.name,
                        event_type="agent.output",
                        metadata={
                            **event_meta,
                            "chunk": event.chunk,
                            "chunkType": "progress",
                            "trace": _trace_item(event, "progress"),
                        },
                    )
                    continue
                full += event.chunk
                for token in iter_stream_pieces(event.chunk):
                    yield TokenEvent(
                        agent_id=agent.id,
                        agent_name=agent.name,
                        token=token,
                        metadata={
                            **event_meta,
                            "chunkType": event.chunk_type,
                            "trace": _trace_item(event, "artifact")
                            if event.chunk_type == "artifact_signal" else None,
                        },
                    )
                continue

            if event.type == "interactive_prompt":
                yield TokenEvent(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    event_type="interactive_prompt",
                    metadata={
                        **event_meta,
                        "sessionId": session_id,
                        "content": event.chunk,
                        "promptType": event.prompt_type,
                        "trace": _trace_item(event, "prompt"),
                    },
                )
                continue

            if event.type in {"agent.process.timeout", "error"}:
                yield TokenEvent(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    token=f"[{agent.name} 错误: {event.error}]",
                    done=True,
                    message_id=msg_id,
                    error=event.error or "CLI Agent 执行失败",
                    metadata={**event_meta, "trace": _trace_item(event, "error")},
                )
                return

            if event.type in {"agent.process.completed", "agent.process.turn_completed"}:
                exit_code = event.exit_code
                turn_completed = event.type == "agent.process.turn_completed"
                if turn_completed:
                    event_meta["engineRuntime"] = {
                        **dict(call_meta.get("engineRuntime") or {}),
                        "turnCompleted": True,
                        "processKeptAlive": True,
                    }
                yield TokenEvent(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    event_type=event.type,
                    metadata={
                        **event_meta,
                        "sessionId": session_id,
                        "exitCode": exit_code,
                        "trace": _trace_item(event, "process"),
                    },
                )

        if (
            self.db
            and engine_invocation
            and engine_invocation.assigned_by_agenthub
            and engine_invocation.engine_session_id
            and resume_policy.supported
            and not engine_session_remembered
        ):
            await EngineSessionService(self.db).remember(
                session_id=session_id,
                agent_config_id=agent.id,
                cli_tool=cli_tool,
                workspace_path=metadata_workspace_path,
                engine_session_id=engine_invocation.engine_session_id,
                metadata={
                    "source": "agenthub_assigned",
                    "strategy": resume_policy.strategy,
                    "startStrategy": resume_policy.start_strategy,
                    "idSource": resume_policy.id_source,
                    "lastGroupTask": call.task,
                },
            )

        if exit_code not in (0, None):
            error = f"CLI 进程异常退出（exit code: {exit_code}）"
            yield TokenEvent(
                agent_id=agent.id,
                agent_name=agent.name,
                token=f"[{agent.name} {error}]",
                done=True,
                message_id=msg_id,
                error=error,
                metadata=call_meta,
            )
            return

        yield TokenEvent(
            agent_id=agent.id,
            agent_name=agent.name,
            token="",
            done=True,
            message_id=msg_id,
            metadata={**call_meta, "token_count": len(full)},
        )

    @staticmethod
    def _metadata(call: AgentCall) -> dict:
        return {
            "task": call.task,
            "role": call.role,
            "phase": call.phase,
            "depends_on": list(call.depends_on),
        }

    async def _remember_engine_session_from_event(
        self,
        event,
        metadata: dict,
        *,
        session_id: str,
        agent_id: str,
        cli_tool: str,
        workspace_path: str,
        resume_policy,
    ) -> bool:
        if not self.db or not event.metadata or not resume_policy.supported:
            return False
        engine_id = str(event.metadata.get("engineSessionId") or "").strip()
        if not engine_id:
            return False
        prior = metadata.get("engineSession") if isinstance(metadata.get("engineSession"), dict) else {}
        metadata["engineSession"] = {
            "mode": prior.get("mode") if prior.get("mode") in {"start", "resume"} else "captured",
            "id": engine_id,
            "adapter": event.metadata.get("cliTool") or cli_tool,
            "source": event.metadata.get("engineSessionSource"),
            "strategy": prior.get("strategy") or resume_policy.strategy,
        }
        await EngineSessionService(self.db).remember(
            session_id=session_id,
            agent_config_id=agent_id,
            cli_tool=cli_tool,
            workspace_path=workspace_path,
            engine_session_id=engine_id,
            metadata={
                "source": event.metadata.get("engineSessionSource"),
                "strategy": resume_policy.strategy,
                "startStrategy": resume_policy.start_strategy,
                "idSource": resume_policy.id_source,
            },
        )
        return True


def _trace_item(event, fallback_kind: str) -> dict | None:
    if not getattr(event, "trace", None):
        return None
    trace = dict(event.trace)
    kind = str(trace.get("kind") or fallback_kind)
    text = trace_text(trace, getattr(event, "chunk", "") or getattr(event, "error", "") or kind)
    return {
        "id": f"trace_{utc_iso().replace('-', '').replace(':', '').replace('.', '')}",
        "kind": kind,
        "text": text,
        "source": "cli" if fallback_kind not in {"process"} else "system",
        "chunkType": getattr(event, "chunk_type", None),
        "processId": getattr(event, "process_id", None),
        "timestamp": utc_iso(),
        **trace,
    }


def _runtime_session_id(session_id: str, agent_id: str) -> str:
    return f"{session_id}:agent:{agent_id}"


def _service_path(service, method_name: str, fallback: str, **kwargs) -> str:
    method = getattr(service, method_name, None)
    if not callable(method):
        return fallback
    try:
        value = method(fallback, **kwargs)
    except TypeError:
        value = method(fallback)
    return str(value or fallback)


def _merge_metadata(target: dict, metadata: dict | None) -> None:
    if not isinstance(metadata, dict):
        return
    for key, value in metadata.items():
        if value is None:
            target.pop(str(key), None)
            continue
        target[str(key)] = value


def _resume_delta_messages(messages: list[dict]) -> list[dict]:
    result: list[dict] = []
    for message in messages:
        if message.get("context_priority") in {"current_reference", "current_turn"}:
            result.append(message)
            continue
        if message.get("is_pinned_context"):
            result.append(message)
            continue
        if message.get("is_reply_context") and message.get("context_priority") == "current_reference":
            result.append(message)
    return result or messages[-1:]
