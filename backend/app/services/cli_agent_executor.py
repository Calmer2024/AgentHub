"""Bridge CLI adapter events into AgentExecutor TokenEvent streams."""

from __future__ import annotations

from typing import AsyncIterator

from ..domain.execution_planner import AgentCall
from ..agents.cli_trace import trace_text
from .execution_trace import utc_iso
from .cli_agent_service import CliAgentService
from .streaming_text import iter_stream_pieces
from .token_event import TokenEvent


class CliAgentCallRunner:
    def __init__(self, event_bus=None):
        self._cli_agents = CliAgentService(event_bus=event_bus)

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

        full = ""
        exit_code = None
        async for event in self._cli_agents.stream(
            agent=agent,
            session_id=session_id,
            workspace_path=workspace_path,
            messages=call.input_messages,
            system_prompt=system_prompt,
        ):
            event_meta = {**meta, "processId": event.process_id}
            if event.type == "agent.process.started":
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
                            **meta,
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
                    metadata={**meta, "trace": _trace_item(event, "error")},
                )
                return

            if event.type == "agent.process.completed":
                exit_code = event.exit_code
                yield TokenEvent(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    event_type="agent.process.completed",
                    metadata={
                        **event_meta,
                        "sessionId": session_id,
                        "exitCode": exit_code,
                        "trace": _trace_item(event, "process"),
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
                metadata=meta,
            )
            return

        yield TokenEvent(
            agent_id=agent.id,
            agent_name=agent.name,
            token="",
            done=True,
            message_id=msg_id,
            metadata={**meta, "token_count": len(full)},
        )

    @staticmethod
    def _metadata(call: AgentCall) -> dict:
        return {
            "task": call.task,
            "role": call.role,
            "phase": call.phase,
            "depends_on": list(call.depends_on),
        }


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
