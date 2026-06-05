"""Single-chat CLI execution stream.

This module owns the narrow single-Agent path: resolve the CLI friend, assemble
chat context, execute the real local CLI process, stream SSE events, and persist
the assistant message.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.context_manager import ContextManager, PromptAssemblyInput
from ..models import AgentConfig, Message as DBMessage, Session as DBSession
from ..agents.cli_trace import trace_text
from .cli_agent_service import CliAgentService
from .execution_trace import ExecutionTraceBuilder, merge_trace_metadata
from .session_service import SessionService
from .streaming_text import iter_stream_pieces


class SingleCliChatStream:
    """Stream a single Project-bound chat through one CLI Agent."""

    def __init__(
        self,
        db: AsyncSession,
        context_manager: ContextManager,
        event_bus=None,
    ):
        self.db = db
        self._context_manager = context_manager
        self._cli_agents = CliAgentService(event_bus=event_bus)

    async def send(
        self,
        session_id: str,
        history: list[dict],
        pinned_message_ids: list[str],
        session: DBSession,
    ) -> AsyncGenerator[str, None]:
        agent_config = await self._agent_for_session(session)
        if not agent_config:
            yield self._err("会话未关联 Agent")
            return

        try:
            workspace_path = await SessionService(self.db).get_workspace_path(session_id)
        except Exception:
            yield self._err("当前会话未绑定项目，无法启动 CLI Agent")
            return

        adapter_messages, system_prompt = self._assemble_prompt(
            session_id,
            history,
            pinned_message_ids,
            agent_config.system_prompt or "",
        )

        assistant_msg_id = str(uuid.uuid4())
        visible = ""
        raw_output = ""
        process_id = ""
        exit_code = None
        metadata: dict = {
            "agentType": agent_config.agent_type or "cli_wrapper",
            "cliTool": agent_config.cli_tool or "custom",
            "workspacePath": workspace_path,
        }
        trace = ExecutionTraceBuilder(
            agent_name=agent_config.name,
            cli_tool=agent_config.cli_tool or "custom",
            workspace_path=workspace_path,
        )
        persisted = False

        try:
            async for event in self._cli_agents.stream(
                agent=agent_config,
                session_id=session_id,
                workspace_path=workspace_path,
                messages=adapter_messages,
                system_prompt=system_prompt,
            ):
                process_id = event.process_id or process_id
                if event.type == "agent.process.started":
                    metadata["processId"] = process_id
                    trace.set_process(process_id)
                    item = trace.add(
                        kind="process",
                        text=trace_text(event.trace or {}, f"正在启动 {agent_config.name}"),
                        process_id=process_id,
                        trace=event.trace,
                    )
                    if item:
                        yield self._trace_delta(
                            session_id, agent_config, assistant_msg_id, process_id, item,
                        )
                    yield self._process_started(
                        session_id, agent_config, assistant_msg_id, process_id,
                    )
                    continue

                if event.type == "agent.output":
                    raw_output += event.chunk
                    if event.chunk_type in {"text", "artifact_signal"}:
                        visible += event.chunk
                    trace_item = None
                    if event.chunk_type != "text":
                        if event.chunk_type == "artifact_signal":
                            kind = "artifact"
                        elif event.chunk_type == "error":
                            kind = "error"
                        else:
                            kind = "progress"
                        trace_item = trace.add(
                            kind=kind,
                            text=event.chunk,
                            source="cli",
                            chunk_type=event.chunk_type,
                            process_id=process_id,
                            trace=event.trace,
                        )
                    if trace_item:
                        yield self._trace_delta(
                            session_id, agent_config, assistant_msg_id, process_id, trace_item,
                        )
                    if event.chunk_type == "text":
                        for token in iter_stream_pieces(event.chunk):
                            yield self._agent_output(
                                session_id, agent_config, assistant_msg_id,
                                process_id, token, event.chunk_type, token,
                            )
                            await _broadcast_ws(session_id, {
                                "type": "token",
                                "token": token,
                                "messageId": assistant_msg_id,
                            })
                    else:
                        yield self._agent_output(
                            session_id, agent_config, assistant_msg_id,
                            process_id, event.chunk, event.chunk_type, "",
                        )
                    continue

                if event.type == "interactive_prompt":
                    item = trace.add(
                        kind="prompt",
                        text=event.chunk,
                        source="cli",
                        chunk_type="interactive_prompt",
                        process_id=process_id,
                        trace=event.trace,
                    )
                    if item:
                        yield self._trace_delta(
                            session_id, agent_config, assistant_msg_id, process_id, item,
                        )
                    yield self._interactive_prompt(
                        session_id, agent_config, assistant_msg_id,
                        process_id, event.chunk, event.prompt_type,
                    )
                    continue

                if event.type in {"agent.process.timeout", "error"}:
                    error = event.error or "CLI Agent 执行失败"
                    trace.add(
                        kind="error",
                        text=error,
                        process_id=process_id,
                        trace=event.trace,
                    )
                    trace.complete(status="error", exit_code=exit_code)
                    metadata["error"] = error
                    await self._persist_message(
                        session, session_id, assistant_msg_id, agent_config,
                        visible or f"CLI Agent 执行失败：{error}",
                        merge_trace_metadata(metadata, trace),
                    )
                    persisted = True
                    yield self._err(error, message_id=assistant_msg_id)
                    return

                if event.type == "agent.process.completed":
                    exit_code = event.exit_code
                    metadata["exitCode"] = exit_code
                    status = "completed" if exit_code in (0, None) else "error"
                    item = trace.add(
                        kind="process",
                        text=trace_text(event.trace or {}, f"{agent_config.name} 已结束"),
                        process_id=process_id,
                        trace=event.trace,
                    )
                    trace.complete(status=status, exit_code=exit_code)
                    if item:
                        yield self._trace_delta(
                            session_id, agent_config, assistant_msg_id, process_id, item,
                        )
                    yield self._process_completed(
                        session_id, agent_config, assistant_msg_id,
                        process_id, exit_code,
                    )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            trace.add(kind="error", text=error, process_id=process_id)
            trace.complete(status="error", exit_code=exit_code)
            metadata["error"] = error
            await self._persist_message(
                session, session_id, assistant_msg_id, agent_config,
                visible or f"CLI Agent 执行失败：{error}",
                merge_trace_metadata(metadata, trace),
            )
            persisted = True
            yield self._err(error, message_id=assistant_msg_id)
            return

        if exit_code not in (0, None):
            error = self._exit_error(exit_code, raw_output)
            trace.complete(status="error", exit_code=exit_code)
            metadata["error"] = error
            if not persisted:
                await self._persist_message(
                    session, session_id, assistant_msg_id, agent_config,
                    visible or f"CLI Agent 执行失败：{error}",
                    merge_trace_metadata(metadata, trace),
                )
            yield self._err(error, message_id=assistant_msg_id)
            return

        if raw_output and raw_output != visible:
            metadata["rawOutputPreview"] = raw_output[-4000:]
        metadata = merge_trace_metadata(metadata, trace)

        await self._persist_message(
            session, session_id, assistant_msg_id, agent_config, visible, metadata,
        )

        await _broadcast_ws(session_id, {
            "type": "message.completed",
            "sessionId": session_id,
            "messageId": assistant_msg_id,
        })
        yield self._sse({
            "token": "",
            "done": True,
            "messageId": assistant_msg_id,
            "agentName": agent_config.name,
        })

    async def _agent_for_session(self, session: DBSession) -> AgentConfig | None:
        if not session.agent_config_id:
            return None
        return await self.db.get(AgentConfig, session.agent_config_id)

    def _assemble_prompt(
        self,
        session_id: str,
        history: list[dict],
        pinned_message_ids: list[str],
        fallback_system_prompt: str,
    ) -> tuple[list[dict], str]:
        assembled = self._context_manager.assemble(PromptAssemblyInput(
            session_id=session_id,
            system_prompt=fallback_system_prompt,
            messages=history,
            pinned_message_ids=pinned_message_ids,
            max_tokens=100_000,
        ))
        return _split_system_prompt(
            assembled.assembled_messages,
            fallback_system_prompt,
        )

    def _process_started(
        self,
        session_id: str,
        agent: AgentConfig,
        message_id: str,
        process_id: str,
    ) -> str:
        return self._sse({
            "type": "agent.process.started",
            "sessionId": session_id,
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "processId": process_id,
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
            "chunk": chunk,
            "chunkType": chunk_type,
            "token": token,
            "done": False,
        })

    def _interactive_prompt(
        self,
        session_id: str,
        agent: AgentConfig,
        message_id: str,
        process_id: str,
        content: str,
        prompt_type: str,
    ) -> str:
        return self._sse({
            "type": "interactive_prompt",
            "sessionId": session_id,
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "processId": process_id,
            "content": content,
            "promptType": prompt_type,
            "token": "",
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
            "exitCode": exit_code,
            "token": "",
            "done": False,
        })

    async def _persist_message(
        self,
        session: DBSession,
        session_id: str,
        message_id: str,
        agent: AgentConfig,
        content: str,
        metadata: dict,
    ) -> None:
        self.db.add(DBMessage(
            id=message_id,
            session_id=session_id,
            role="assistant",
            content=content,
            content_type="text",
            agent_name=agent.name,
            source_type="agent",
            source_id=agent.id,
            source_name=agent.name,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ))
        session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.commit()

    @staticmethod
    def _exit_error(exit_code: int | None, raw_output: str) -> str:
        tail = raw_output.strip()[-500:]
        detail = f"CLI 进程异常退出（exit code: {exit_code}）"
        return f"{detail}: {tail}" if tail else detail

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    @staticmethod
    def _err(msg: str, message_id: str | None = None) -> str:
        data = {"type": "error", "token": "", "done": True, "error": msg}
        if message_id:
            data["messageId"] = message_id
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _split_system_prompt(messages: list[dict], fallback: str) -> tuple[list[dict], str]:
    if messages and messages[0].get("role") == "system":
        return messages[1:], str(messages[0].get("content") or fallback)
    return messages, fallback


async def _broadcast_ws(session_id: str, payload: dict) -> None:
    try:
        from ..api.ws_manager import manager as ws_manager
        await ws_manager.broadcast(session_id, payload)
    except Exception:
        pass
