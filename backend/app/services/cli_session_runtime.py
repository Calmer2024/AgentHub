"""CLI 会话级 runtime 选择与上下文增量策略。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentConfig
from .cli_agent_service import CliAgentService
from .engine_session_service import EngineSessionInvocation, EngineSessionService


@dataclass
class CliSessionRuntime:
    """一次 AgentHub 会话内 CLI 调用的底层 runtime 决策。"""

    cli_tool: str
    runtime_session_id: str
    engine_invocation: EngineSessionInvocation
    resume_policy: Any
    supports_persistent_process: bool
    messages: list[dict]
    metadata: dict[str, Any]


async def prepare_cli_session_runtime(
    *,
    db: AsyncSession,
    cli_agents: CliAgentService,
    session_id: str,
    agent: AgentConfig,
    workspace_path: str,
    messages: list[dict],
    pinned_message_ids: list[str] | None = None,
    process_scope: str,
    turn_isolation: str,
) -> CliSessionRuntime:
    """按 CLI 能力决定本轮是否复用常驻进程或原生 Engine session。"""
    cli_tool = agent.cli_tool or "custom"
    resume_policy = cli_agents.engine_session_resume_policy(agent)
    supports_persistent_process = cli_agents.supports_persistent_process(agent)
    metadata_workspace_path = _service_path(
        cli_agents,
        "metadata_workspace_path",
        workspace_path,
        session_id=session_id,
        agent=agent,
    )
    engine_invocation = await EngineSessionService(db).resolve_invocation(
        session_id=session_id,
        agent_config_id=agent.id,
        cli_tool=cli_tool,
        workspace_path=metadata_workspace_path,
        supported=resume_policy.supported,
        caller_assigned_id=resume_policy.caller_assigned_id,
    )
    runtime_mode = (
        "persistent_process"
        if supports_persistent_process
        else "engine_session_resume" if resume_policy.supported else "oneshot_process"
    )
    selected_messages = (
        resume_delta_messages(messages, pinned_message_ids)
        if engine_invocation.is_resume else mark_pinned_messages(messages, pinned_message_ids)
    )
    runtime_session_id = session_agent_runtime_id(session_id, agent.id)
    metadata: dict[str, Any] = {
        "agentType": agent.agent_type or "cli_wrapper",
        "cliTool": cli_tool,
        "workspacePath": metadata_workspace_path,
        "engineRuntime": {
            "mode": runtime_mode,
            "processScope": process_scope if supports_persistent_process else "per_turn_process",
            "turnIsolation": turn_isolation if supports_persistent_process else "request_stream",
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
    if engine_invocation.engine_session_id:
        metadata["engineSession"] = {
            "mode": engine_invocation.mode,
            "id": engine_invocation.engine_session_id,
            "adapter": cli_tool,
            "strategy": (
                resume_policy.strategy
                if engine_invocation.is_resume else resume_policy.start_strategy
            ),
        }
        if engine_invocation.assigned_by_agenthub:
            metadata["engineSession"]["source"] = "agenthub_assigned"
    return CliSessionRuntime(
        cli_tool=cli_tool,
        runtime_session_id=runtime_session_id,
        engine_invocation=engine_invocation,
        resume_policy=resume_policy,
        supports_persistent_process=supports_persistent_process,
        messages=selected_messages,
        metadata=metadata,
    )


async def remember_engine_session_from_metadata(
    *,
    db: AsyncSession,
    runtime: CliSessionRuntime,
    session_id: str,
    agent: AgentConfig,
    workspace_path: str,
    event_metadata: dict | None,
) -> bool:
    if not event_metadata or not runtime.resume_policy.supported:
        return False
    engine_id = str(event_metadata.get("engineSessionId") or "").strip()
    if not engine_id:
        return False
    prior = runtime.metadata.get("engineSession") if isinstance(runtime.metadata.get("engineSession"), dict) else {}
    runtime.metadata["engineSession"] = {
        "mode": prior.get("mode") if prior.get("mode") in {"start", "resume"} else "captured",
        "id": engine_id,
        "adapter": event_metadata.get("cliTool") or runtime.cli_tool,
        "source": event_metadata.get("engineSessionSource"),
        "strategy": prior.get("strategy") or runtime.resume_policy.strategy,
    }
    metadata_workspace_path = _service_path(
        runtime_service_from_metadata(runtime),
        "metadata_workspace_path",
        workspace_path,
        session_id=session_id,
        agent=agent,
    )
    await EngineSessionService(db).remember(
        session_id=session_id,
        agent_config_id=agent.id,
        cli_tool=runtime.cli_tool,
        workspace_path=metadata_workspace_path,
        engine_session_id=engine_id,
        metadata={
            "source": event_metadata.get("engineSessionSource"),
            "strategy": runtime.resume_policy.strategy,
            "startStrategy": runtime.resume_policy.start_strategy,
            "idSource": runtime.resume_policy.id_source,
        },
    )
    return True


async def remember_assigned_engine_session_if_needed(
    *,
    db: AsyncSession,
    runtime: CliSessionRuntime,
    session_id: str,
    agent: AgentConfig,
    workspace_path: str,
    remembered: bool,
    metadata: dict[str, Any] | None = None,
) -> bool:
    if (
        remembered
        or not runtime.engine_invocation.assigned_by_agenthub
        or not runtime.engine_invocation.engine_session_id
        or not runtime.resume_policy.supported
    ):
        return remembered
    await EngineSessionService(db).remember(
        session_id=session_id,
        agent_config_id=agent.id,
        cli_tool=runtime.cli_tool,
        workspace_path=workspace_path,
        engine_session_id=runtime.engine_invocation.engine_session_id,
        metadata={
            "source": "agenthub_assigned",
            "strategy": runtime.resume_policy.strategy,
            "startStrategy": runtime.resume_policy.start_strategy,
            "idSource": runtime.resume_policy.id_source,
            **(metadata or {}),
        },
    )
    return True


def merge_runtime_process_metadata(target: dict[str, Any], event_metadata: dict | None) -> None:
    if not event_metadata:
        return
    runtime = dict(target.get("engineRuntime") or {})
    for key in (
        "persistentProcess",
        "persistentProtocol",
        "reused",
        "recovered",
        "engineSessionMode",
        "engineSessionId",
        "turnCompleted",
        "processKeptAlive",
    ):
        if key in event_metadata:
            runtime[key] = event_metadata[key]
    target["engineRuntime"] = runtime


def session_agent_runtime_id(session_id: str, agent_id: str) -> str:
    return f"{session_id}:agent:{agent_id}"


def resume_delta_messages(
    messages: list[dict],
    pinned_message_ids: list[str] | None = None,
) -> list[dict]:
    result: list[dict] = []
    pinned = set(pinned_message_ids or [])
    marked = mark_pinned_messages(messages, pinned_message_ids)
    for message in marked:
        if message.get("id") in pinned:
            result.append(message)
            continue
        if message.get("context_priority") in {"current_reference", "current_turn"}:
            result.append(message)
            continue
        if message.get("is_pinned_context"):
            result.append(message)
            continue
        if message.get("is_reply_context") and message.get("context_priority") == "current_reference":
            result.append(message)
    if marked and marked[-1] not in result:
        result.append(marked[-1])
    return result or marked[-1:]


def mark_pinned_messages(
    messages: list[dict],
    pinned_message_ids: list[str] | None = None,
) -> list[dict]:
    pinned = set(pinned_message_ids or [])
    if not pinned:
        return list(messages)
    result: list[dict] = []
    for message in messages:
        if message.get("id") not in pinned:
            result.append(message)
            continue
        marked = dict(message)
        content = str(marked.get("content") or "")
        if not content.startswith("[Pinned message]"):
            marked["content"] = (
                "[Pinned message]\n"
                "用户固定了这条历史消息。回答时请把它视为长期重要上下文。\n"
                f"{content}"
            )
        marked["is_pinned_context"] = True
        result.append(marked)
    return result


def current_turn_message(content: str) -> dict:
    return {
        "role": "user",
        "content": content,
        "id": f"transient-current-{uuid.uuid4().hex[:12]}",
        "context_priority": "current_turn",
    }


def _service_path(service, method_name: str, fallback: str, **kwargs) -> str:
    method = getattr(service, method_name, None)
    if not callable(method):
        return fallback
    try:
        value = method(fallback, **kwargs)
    except TypeError:
        value = method(fallback)
    return str(value or fallback)


def runtime_service_from_metadata(runtime: CliSessionRuntime):
    # 仅为保持 remember helper 统一签名；runtime metadata 已保存逻辑 workspace。
    class _RuntimeService:
        @staticmethod
        def metadata_workspace_path(workspace_path: str, **_: Any) -> str:
            return str(runtime.metadata.get("workspacePath") or workspace_path)

    return _RuntimeService()
