"""Per-CLI adapters：把真实 CLI stdout/stderr 解析成 AgentHub 事件。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import AsyncIterator, cast
from urllib.parse import urlsplit, urlunsplit

from ..models import AgentConfig
from .codex_config import CodexConnectionSettings, resolve_codex_connection_settings
from .cli_defaults import DEFAULT_CLI_AGENTS
from .cli_events import CliEvent, ParsedOutput
from .cli_output_parser import (
    CliOutputParser,
    extract_content,
    first_string,
    json_to_readable_text,
    looks_like_message_event,
)
from .cli_runtime import (
    CliExecutableNotFound,
    CliSubprocessNotSupported,
    cli_process_manager,
)
from .cli_rpc_session_runtime import (
    CliRpcSessionConfig,
    CliRpcTurnRequest,
    RpcProtocol,
    cli_rpc_session_runtime,
)
from .cli_session_runtime import (
    CliSessionProcessConfig,
    cli_session_process_runtime,
)
from .cli_stream import PromptInterceptor, StreamSanitizer
from .cli_trace import (
    artifact_trace,
    claude_event_trace,
    claude_thinking_trace,
    claude_tool_result_trace,
    claude_tool_trace,
    codex_event_trace,
    codex_stderr_trace,
    error_trace,
    generic_progress_trace,
    opencode_part_trace,
    process_completed_trace,
    process_start_trace,
    prompt_trace,
    trace_text,
)


@dataclass(frozen=True)
class EngineSessionResumePolicy:
    """Adapter 自己声明底层 CLI 的原生会话能力。"""

    supported: bool = False
    strategy: str = "stateless"
    start_strategy: str = ""
    id_source: str = ""
    caller_assigned_id: bool = False


@dataclass(frozen=True)
class PersistentProcessPolicy:
    """Adapter 声明是否能被 AgentHub 作为会话级常驻进程驱动。"""

    supported: bool = False
    strategy: str = "oneshot"
    input_format: str = ""
    output_format: str = ""
    protocol: str = "stdio_jsonl"


class CliAgentAdapter:
    cli_tool = "custom"
    display_name = "CLI Agent"
    progress_patterns: tuple[re.Pattern, ...] = ()
    close_stdin_after_prompt = False
    expects_json_lines = False
    stdin_mode = "pipe"
    engine_session_resume_policy = EngineSessionResumePolicy()
    persistent_process_policy = PersistentProcessPolicy()

    @property
    def supports_engine_session_resume(self) -> bool:
        return self.engine_session_resume_policy.supported

    @property
    def supports_persistent_process(self) -> bool:
        return self.persistent_process_policy.supported

    async def stream(
        self,
        *,
        agent: AgentConfig,
        session_id: str,
        cwd: str,
        user_prompt: str,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
        event_bus=None,
    ) -> AsyncIterator[CliEvent]:
        interceptor = PromptInterceptor()
        executable = agent.executable or DEFAULT_CLI_AGENTS.get(
            self.cli_tool, {},
        ).get("executable", "")
        args = _json_list(agent.init_args)
        env_vars = _json_dict(agent.env_vars)
        prompt = self.build_prompt(system_prompt, user_prompt)
        args, stdin_prompt, close_stdin = self.prepare_invocation(
            args,
            prompt,
            system_prompt=system_prompt,
            engine_session_id=engine_session_id,
            engine_session_mode=engine_session_mode,
        )

        if not executable:
            yield CliEvent("error", "", error="当前 Agent 未配置 executable，无法启动 CLI。")
            return

        parser = CliOutputParser(self)
        try:
            async for chunk in cli_process_manager.stream(
                session_id=session_id,
                agent_id=agent.id,
                executable=executable,
                args=args,
                env_vars=env_vars,
                cwd=cwd,
                prompt=stdin_prompt,
                close_stdin_after_prompt=close_stdin,
                stdin_mode=self.stdin_mode,
                event_bus=event_bus,
            ):
                if chunk.event_type == "started":
                    yield CliEvent(
                        "agent.process.started",
                        chunk.process_id,
                        trace=process_start_trace(
                            getattr(agent, "name", executable),
                            chunk.command,
                            chunk.cwd,
                            chunk.pid,
                            persistent=chunk.persistent,
                            engine_session_mode=engine_session_mode
                            if engine_session_id else None,
                            engine_session_id=engine_session_id,
                        ),
                        metadata={
                            "persistentProcess": False,
                            "engineSessionMode": engine_session_mode,
                            "engineSessionId": engine_session_id,
                        } if engine_session_id else None,
                    )
                    continue
                if chunk.event_type == "completed":
                    for parsed in parser.flush():
                        yield self._event_from_parsed(chunk.process_id, parsed)
                    yield CliEvent(
                        "agent.process.completed",
                        chunk.process_id,
                        exit_code=chunk.exit_code,
                        trace=process_completed_trace(
                            getattr(agent, "name", executable),
                            chunk.exit_code,
                        ),
                    )
                    continue
                if chunk.event_type == "timeout":
                    yield CliEvent(
                        "agent.process.timeout",
                        chunk.process_id,
                        error=chunk.error,
                    )
                    continue
                if chunk.event_type == "error":
                    yield CliEvent("error", chunk.process_id, error=chunk.error)
                    continue

                clean = StreamSanitizer.clean(chunk.text)
                if not clean:
                    continue
                if chunk.stream == "stderr":
                    for parsed in parser.feed_stderr(clean):
                        yield self._event_from_parsed(chunk.process_id, parsed)
                    continue
                prompt_text = interceptor.detect(clean)
                if prompt_text:
                    yield CliEvent(
                        "interactive_prompt",
                        chunk.process_id,
                        chunk=prompt_text,
                        trace=prompt_trace(prompt_text),
                    )
                    continue
                for parsed in parser.feed_stdout(clean):
                    yield self._event_from_parsed(chunk.process_id, parsed)
        except CliExecutableNotFound:
            yield CliEvent(
                "error",
                "",
                error=f"未找到 '{executable}' 命令。请安装 CLI 后重试。",
            )

        except CliSubprocessNotSupported as exc:
            yield CliEvent("error", "", error=str(exc))

    async def stream_persistent_turn(
        self,
        *,
        agent: AgentConfig,
        session_id: str,
        cwd: str,
        user_prompt: str,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
        event_bus=None,
    ) -> AsyncIterator[CliEvent]:
        if not self.supports_persistent_process:
            async for event in self.stream(
                agent=agent,
                session_id=session_id,
                cwd=cwd,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                engine_session_id=engine_session_id,
                engine_session_mode=engine_session_mode,
                event_bus=event_bus,
            ):
                yield event
            return

        interceptor = PromptInterceptor()
        executable = agent.executable or DEFAULT_CLI_AGENTS.get(
            self.cli_tool, {},
        ).get("executable", "")
        args = _json_list(agent.init_args)
        env_vars = _json_dict(agent.env_vars)
        prompt = self.build_prompt(system_prompt, user_prompt)

        if not executable:
            yield CliEvent("error", "", error="当前 Agent 未配置 executable，无法启动 CLI。")
            return

        if self.persistent_process_policy.protocol in {"mcp", "acp"}:
            async for event in self._stream_rpc_persistent_turn(
                agent=agent,
                session_id=session_id,
                executable=executable,
                args=args,
                env_vars=env_vars,
                cwd=cwd,
                prompt=prompt,
                system_prompt=system_prompt,
                engine_session_id=engine_session_id,
                engine_session_mode=engine_session_mode,
                event_bus=event_bus,
            ):
                yield event
            return

        args, stdin_prompt = self.prepare_persistent_invocation(
            args,
            prompt,
            system_prompt=system_prompt,
            engine_session_id=engine_session_id,
            engine_session_mode=engine_session_mode,
        )

        parser = CliOutputParser(self)
        try:
            async for chunk in cli_session_process_runtime.stream_turn(
                config=CliSessionProcessConfig(
                    session_id=session_id,
                    agent_id=agent.id,
                    executable=executable,
                    args=args,
                    env_vars=env_vars,
                    cwd=cwd,
                    stdin_mode=self.stdin_mode,
                ),
                prompt=stdin_prompt,
                event_bus=event_bus,
                turn_completed=self.persistent_turn_completed,
            ):
                if chunk.event_type == "started":
                    yield CliEvent(
                        "agent.process.started",
                        chunk.process_id,
                        trace=process_start_trace(
                            getattr(agent, "name", executable),
                            chunk.command,
                            chunk.cwd,
                            chunk.pid,
                            persistent=True,
                            reused=chunk.reused,
                            recovered=chunk.recovered,
                        ),
                        metadata={
                            "persistentProcess": True,
                            "reused": chunk.reused,
                            "recovered": chunk.recovered,
                            "engineSessionMode": engine_session_mode
                            if engine_session_id else None,
                            "engineSessionId": engine_session_id,
                        },
                    )
                    continue
                if chunk.event_type == "turn_completed":
                    for parsed in parser.flush():
                        yield self._event_from_parsed(chunk.process_id, parsed)
                    yield CliEvent(
                        "agent.process.turn_completed",
                        chunk.process_id,
                        exit_code=0,
                        metadata={"persistentProcess": True},
                    )
                    continue
                if chunk.event_type == "completed":
                    for parsed in parser.flush():
                        yield self._event_from_parsed(chunk.process_id, parsed)
                    yield CliEvent(
                        "agent.process.completed",
                        chunk.process_id,
                        exit_code=chunk.exit_code,
                        trace=process_completed_trace(
                            getattr(agent, "name", executable),
                            chunk.exit_code,
                        ),
                        metadata={"persistentProcess": True},
                    )
                    continue
                if chunk.event_type == "timeout":
                    yield CliEvent(
                        "agent.process.timeout",
                        chunk.process_id,
                        error=chunk.error,
                        metadata={"persistentProcess": True},
                    )
                    continue
                if chunk.event_type == "error":
                    yield CliEvent("error", chunk.process_id, error=chunk.error)
                    continue

                clean = StreamSanitizer.clean(chunk.text)
                if not clean:
                    continue
                if chunk.stream == "stderr":
                    for parsed in parser.feed_stderr(clean):
                        yield self._event_from_parsed(chunk.process_id, parsed)
                    continue
                prompt_text = interceptor.detect(clean)
                if prompt_text:
                    yield CliEvent(
                        "interactive_prompt",
                        chunk.process_id,
                        chunk=prompt_text,
                        trace=prompt_trace(prompt_text),
                    )
                    continue
                for parsed in parser.feed_stdout(clean):
                    yield self._event_from_parsed(chunk.process_id, parsed)
        except CliExecutableNotFound:
            yield CliEvent(
                "error",
                "",
                error=f"未找到 '{executable}' 命令。请安装 CLI 后重试。",
            )
        except CliSubprocessNotSupported as exc:
            yield CliEvent("error", "", error=str(exc))

    async def _stream_rpc_persistent_turn(
        self,
        *,
        agent: AgentConfig,
        session_id: str,
        executable: str,
        args: list[str],
        env_vars: dict[str, str],
        cwd: str,
        prompt: str,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
        event_bus=None,
    ) -> AsyncIterator[CliEvent]:
        try:
            rpc_args, request = self.prepare_persistent_rpc_invocation(
                args,
                prompt,
                system_prompt=system_prompt,
                engine_session_id=engine_session_id,
                engine_session_mode=engine_session_mode,
                cwd=cwd,
            )
        except ValueError as exc:
            yield CliEvent("error", "", error=str(exc))
            return

        parser = CliOutputParser(self)
        protocol = self.persistent_process_policy.protocol
        try:
            async for chunk in cli_rpc_session_runtime.stream_turn(
                config=CliRpcSessionConfig(
                    session_id=session_id,
                    agent_id=agent.id,
                    executable=executable,
                    args=rpc_args,
                    env_vars=env_vars,
                    cwd=cwd,
                    protocol=cast(RpcProtocol, protocol),
                    cli_tool=self.cli_tool,
                ),
                request=request,
                event_bus=event_bus,
            ):
                if chunk.event_type == "started":
                    yield CliEvent(
                        "agent.process.started",
                        chunk.process_id,
                        trace=process_start_trace(
                            getattr(agent, "name", executable),
                            chunk.command,
                            chunk.cwd,
                            chunk.pid,
                            persistent=True,
                            reused=chunk.reused,
                            recovered=chunk.recovered,
                        ),
                        metadata={
                            "persistentProcess": True,
                            "persistentProtocol": protocol,
                            "reused": chunk.reused,
                            "recovered": chunk.recovered,
                        },
                    )
                    continue
                if chunk.event_type == "turn_completed":
                    for parsed in parser.flush():
                        yield self._event_from_parsed(chunk.process_id, parsed)
                    yield CliEvent(
                        "agent.process.turn_completed",
                        chunk.process_id,
                        exit_code=0,
                        metadata={
                            "persistentProcess": True,
                            "persistentProtocol": protocol,
                        },
                    )
                    continue
                if chunk.event_type == "completed":
                    for parsed in parser.flush():
                        yield self._event_from_parsed(chunk.process_id, parsed)
                    yield CliEvent(
                        "agent.process.completed",
                        chunk.process_id,
                        exit_code=chunk.exit_code,
                        trace=process_completed_trace(
                            getattr(agent, "name", executable),
                            chunk.exit_code,
                        ),
                        metadata={
                            "persistentProcess": True,
                            "persistentProtocol": protocol,
                        },
                    )
                    continue
                if chunk.event_type == "timeout":
                    yield CliEvent(
                        "agent.process.timeout",
                        chunk.process_id,
                        error=chunk.error,
                        metadata={
                            "persistentProcess": True,
                            "persistentProtocol": protocol,
                        },
                    )
                    continue
                if chunk.event_type == "error":
                    yield CliEvent("error", chunk.process_id, error=chunk.error)
                    continue

                clean = StreamSanitizer.clean(chunk.text)
                if not clean:
                    continue
                if chunk.stream == "stderr":
                    for parsed in parser.feed_stderr(clean):
                        yield self._event_from_parsed(chunk.process_id, parsed)
                    continue
                for parsed in parser.feed_stdout(clean):
                    yield self._event_from_parsed(chunk.process_id, parsed)
        except CliExecutableNotFound:
            yield CliEvent(
                "error",
                "",
                error=f"未找到 '{executable}' 命令。请安装 CLI 后重试。",
            )
        except CliSubprocessNotSupported as exc:
            yield CliEvent("error", "", error=str(exc))

    def build_prompt(self, system_prompt: str, user_prompt: str) -> str:
        if system_prompt.strip():
            return f"{system_prompt.strip()}\n\n{user_prompt.rstrip()}\n"
        return f"{user_prompt.rstrip()}\n"

    def render_prompt_messages(self, messages: list[dict]) -> str:
        return render_transcript_prompt(messages)

    def prepare_invocation(
        self,
        args: list[str],
        prompt: str,
        *,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
    ) -> tuple[list[str], str, bool]:
        del system_prompt
        del engine_session_id
        del engine_session_mode
        return args, prompt, self.close_stdin_after_prompt

    def prepare_persistent_invocation(
        self,
        args: list[str],
        prompt: str,
        *,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
    ) -> tuple[list[str], str]:
        one_shot_args, stdin_prompt, _ = self.prepare_invocation(
            args,
            prompt,
            system_prompt=system_prompt,
            engine_session_id=engine_session_id,
            engine_session_mode=engine_session_mode,
        )
        return one_shot_args, stdin_prompt

    def prepare_persistent_rpc_invocation(
        self,
        args: list[str],
        prompt: str,
        *,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
        cwd: str = "",
    ) -> tuple[list[str], CliRpcTurnRequest]:
        del args
        del prompt
        del system_prompt
        del engine_session_id
        del engine_session_mode
        del cwd
        raise ValueError("当前 CLI Adapter 未实现 JSON-RPC 常驻进程协议")

    def persistent_turn_completed(self, line: str) -> bool:
        del line
        return False

    def classify(self, chunk: str) -> str:
        stripped = chunk.strip()
        if not stripped:
            return "text"
        if self.is_progress(stripped):
            return "progress"
        if self.is_artifact_signal(stripped):
            return "artifact_signal"
        return "text"

    def is_progress(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.progress_patterns)

    @staticmethod
    def is_artifact_signal(text: str) -> bool:
        return any(marker in text for marker in ("```html", "```diff", "```tsx", "```jsx")) or (
            "diff --git " in text or "@@ -" in text
        )

    def parse_json_event(self, data: object, seen_text: bool) -> list[ParsedOutput]:
        del seen_text
        text = json_to_readable_text(data)
        return [self.parsed(text)] if text else []

    def parse_stderr_output(self, text: str) -> list[ParsedOutput]:
        return [self.parsed(text, "progress")]

    def parse_raw_line(self, line: str) -> list[ParsedOutput]:
        return [self.parsed(line, self.classify(line))]

    def parsed(
        self,
        text: str,
        chunk_type: str | None = None,
        trace: dict | None = None,
    ) -> ParsedOutput:
        next_type = chunk_type or self.classify(text)
        return ParsedOutput(text, next_type, trace or self.trace_for_output(text, next_type))

    @staticmethod
    def _event_from_parsed(process_id: str, parsed: ParsedOutput) -> CliEvent:
        if parsed.chunk_type == "metadata":
            return CliEvent(
                "agent.metadata",
                process_id,
                chunk="",
                chunk_type=parsed.chunk_type,
                trace=parsed.trace,
                metadata=parsed.metadata,
            )
        return CliEvent(
            "agent.output",
            process_id,
            chunk=parsed.text,
            chunk_type=parsed.chunk_type,
            trace=parsed.trace,
            metadata=parsed.metadata,
        )

    def trace_for_output(self, text: str, chunk_type: str) -> dict | None:
        if chunk_type == "text":
            return None
        if chunk_type == "artifact_signal":
            return artifact_trace(text)
        if chunk_type == "error":
            return error_trace(text)
        return generic_progress_trace(text, provider=self.display_name)


class ClaudeCodeAdapter(CliAgentAdapter):
    cli_tool = "claude_code"
    display_name = "Claude Code"
    close_stdin_after_prompt = True
    expects_json_lines = True
    engine_session_resume_policy = EngineSessionResumePolicy(
        supported=True,
        strategy="claude --resume <session_id>",
        start_strategy="claude --session-id <uuid>",
        id_source="AgentHub assigned UUID / result.session_id",
        caller_assigned_id=True,
    )
    persistent_process_policy = PersistentProcessPolicy(
        supported=True,
        strategy="claude -p --input-format stream-json --output-format stream-json --session-id/--resume",
        input_format="stream-json",
        output_format="stream-json",
    )
    progress_patterns = (
        re.compile(r"^(?:⏺|⎿)\s+", re.M),
        re.compile(r"调用工具|正在读取|正在写入"),
    )

    def build_prompt(self, system_prompt: str, user_prompt: str) -> str:
        if not system_prompt.strip():
            return super().build_prompt(system_prompt, user_prompt)
        return (
            "<agenthub_system_context>\n"
            f"{system_prompt.strip()}\n"
            "</agenthub_system_context>\n\n"
            "上面的 AgentHub system context 定义了你在当前会话中的 Agent Profile 身份、"
            "Skill 和上下文策略。回答用户询问身份或职责时，优先使用这个 Agent Profile，"
            "不要只回答底层 CLI Engine 名称。\n\n"
            f"{user_prompt.rstrip()}\n"
        )

    def prepare_invocation(
        self,
        args: list[str],
        prompt: str,
        *,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
    ) -> tuple[list[str], str, bool]:
        del system_prompt
        normalized = _normalize_claude_print_args(args)
        if engine_session_id:
            session_flag = "--session-id" if engine_session_mode == "start" else "--resume"
            normalized = [*_without_claude_session_args(normalized), session_flag, engine_session_id]
        return normalized, prompt, self.close_stdin_after_prompt

    def prepare_persistent_invocation(
        self,
        args: list[str],
        prompt: str,
        *,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
    ) -> tuple[list[str], str]:
        del system_prompt
        normalized = _normalize_claude_streaming_input_args(args)
        if engine_session_id:
            session_flag = "--session-id" if engine_session_mode == "start" else "--resume"
            normalized = [*_without_claude_session_args(normalized), session_flag, engine_session_id]
        return normalized, _claude_sdk_user_message(prompt)

    @staticmethod
    def persistent_turn_completed(line: str) -> bool:
        try:
            data = json.loads(line.strip())
        except json.JSONDecodeError:
            return False
        return isinstance(data, dict) and data.get("type") == "result"

    def parse_json_event(self, data: object, seen_text: bool) -> list[ParsedOutput]:
        if not isinstance(data, dict):
            return super().parse_json_event(data, seen_text)
        event_type = str(data.get("type") or "")
        if event_type == "stream_event":
            return self._stream_event_outputs(data.get("event"))
        if event_type == "assistant":
            outputs = self._assistant_message_outputs(data.get("message"), seen_text)
            return outputs
        if event_type == "user":
            trace = claude_tool_result_trace(data)
            return [ParsedOutput(trace_text(trace), "progress", trace)] if trace else []
        if event_type == "content_block_delta":
            delta = data.get("delta")
            return self._delta_outputs(delta)
        if event_type == "result":
            outputs = self._result_metadata_outputs(data)
            if data.get("is_error") is True:
                text = first_string(data, ("result", "message", "error"))
                if text:
                    outputs.append(ParsedOutput(text, "error", error_trace(text)))
                return outputs
            if not seen_text and isinstance(data.get("result"), str):
                text = data["result"]
                outputs.append(self.parsed(text))
            return outputs
        if event_type in {"system", "user"}:
            return []
        return self._progress_from_json(event_type, data)

    def _stream_event_outputs(self, event: object) -> list[ParsedOutput]:
        if not isinstance(event, dict):
            return []
        event_type = str(event.get("type") or "")
        if event_type == "content_block_delta":
            return self._delta_outputs(event.get("delta"))
        return []

    def _delta_outputs(self, delta: object) -> list[ParsedOutput]:
        if not isinstance(delta, dict):
            return []
        if isinstance(delta.get("text"), str):
            return [self.parsed(delta["text"])]
        if str(delta.get("type") or "") == "text_delta" and isinstance(delta.get("text"), str):
            return [self.parsed(delta["text"])]
        return []

    def _assistant_message_outputs(self, message: object, seen_text: bool) -> list[ParsedOutput]:
        if not isinstance(message, dict):
            return []
        outputs: list[ParsedOutput] = []
        content = message.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "text" and isinstance(item.get("text"), str):
                    if seen_text:
                        continue
                    text = item["text"]
                    outputs.append(self.parsed(text))
                elif item_type == "thinking" and isinstance(item.get("thinking"), str):
                    trace = claude_thinking_trace(item["thinking"])
                    outputs.append(ParsedOutput(trace_text(trace), "progress", trace))
                elif item_type == "tool_use":
                    name = item.get("name") or "tool"
                    trace = claude_tool_trace(item)
                    outputs.append(ParsedOutput(
                        f"Claude Code 调用工具: {name}",
                        "progress",
                        trace,
                    ))
        return outputs

    def _progress_from_json(self, event_type: str, data: dict) -> list[ParsedOutput]:
        trace = claude_event_trace(event_type, data)
        if trace:
            return [ParsedOutput(trace_text(trace), "progress", trace)]
        return []

    @staticmethod
    def _result_metadata_outputs(data: dict) -> list[ParsedOutput]:
        engine_session_id = _first_non_empty_string(
            data,
            ("session_id", "sessionId", "conversation_id", "conversationId"),
        )
        if not engine_session_id:
            return []
        metadata = {
            "engineSessionId": engine_session_id,
            "engineSessionSource": "claude_code_result",
            "cliTool": "claude_code",
        }
        for source_key, target_key in (
            ("total_cost_usd", "totalCostUsd"),
            ("duration_ms", "durationMs"),
            ("num_turns", "numTurns"),
        ):
            value = data.get(source_key)
            if value is not None:
                metadata[target_key] = value
        return [ParsedOutput("", "metadata", metadata=metadata)]


class CodexAdapter(CliAgentAdapter):
    cli_tool = "codex"
    display_name = "Codex"
    close_stdin_after_prompt = True
    expects_json_lines = True
    persistent_process_policy = PersistentProcessPolicy(
        supported=True,
        strategy="codex mcp-server + tools/call codex/codex-reply",
        input_format="mcp_tools_call",
        output_format="mcp_json_rpc",
        protocol="mcp",
    )
    engine_session_resume_policy = EngineSessionResumePolicy(
        supported=True,
        strategy="codex exec resume <session_id> -",
        id_source="thread/session JSON event",
    )
    progress_patterns = (
        re.compile(r"working\.\.\.", re.I),
        re.compile(r"^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]", re.M),
    )

    CODEX_ENV_PREFIX = "AGENTHUB_CODEX_"
    CODEX_PROVIDER_ID = "agenthub_proxy"
    QUIET_EVENT_TYPES = {
        "thread.started",
        "turn.started",
        "turn.completed",
        "session_configured",
        "turn.failed",
    }
    STDERR_NOISE_PATTERNS = (
        re.compile(r"codex_models_manager::manager: failed to refresh available models", re.I),
        re.compile(r"codex_core::shell_snapshot: Failed to create shell snapshot", re.I),
        re.compile(r"codex_core_plugins::manifest: ignoring interface\.defaultPrompt", re.I),
        re.compile(r"codex_core_skills::loader: ignoring interface\.icon_(?:small|large)", re.I),
        re.compile(r"rmcp::transport::worker: worker quit", re.I),
    )
    QUIET_RAW_LINES = {
        "thread.started",
        "turn.started",
        "turn.completed",
        "turn.failed",
        "session_configured",
        "item.started",
        "item.completed",
    }

    async def stream(
        self,
        *,
        agent: AgentConfig,
        session_id: str,
        cwd: str,
        user_prompt: str,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
        event_bus=None,
    ) -> AsyncIterator[CliEvent]:
        env_vars = _json_dict(agent.env_vars)
        original_args = _json_list(agent.init_args)
        try:
            args, runtime_env = self._apply_connection_settings(original_args, env_vars)
        except ValueError as exc:
            yield CliEvent("error", "", error=str(exc))
            return
        agent_for_run = _agent_with_runtime_config(agent, args, runtime_env)
        async for event in super().stream(
            agent=agent_for_run,
            session_id=session_id,
            cwd=cwd,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            engine_session_id=engine_session_id,
            engine_session_mode=engine_session_mode,
            event_bus=event_bus,
        ):
            yield event

    async def stream_persistent_turn(
        self,
        *,
        agent: AgentConfig,
        session_id: str,
        cwd: str,
        user_prompt: str,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
        event_bus=None,
    ) -> AsyncIterator[CliEvent]:
        env_vars = _json_dict(agent.env_vars)
        original_args = _json_list(agent.init_args)
        try:
            args, runtime_env = self._apply_connection_settings(original_args, env_vars)
        except ValueError as exc:
            yield CliEvent("error", "", error=str(exc))
            return
        agent_for_run = _agent_with_runtime_config(agent, args, runtime_env)
        async for event in super().stream_persistent_turn(
            agent=agent_for_run,
            session_id=session_id,
            cwd=cwd,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            engine_session_id=engine_session_id,
            engine_session_mode=engine_session_mode,
            event_bus=event_bus,
        ):
            yield event

    def build_prompt(self, system_prompt: str, user_prompt: str) -> str:
        if system_prompt.strip():
            return f"{system_prompt.strip()}\n\n{user_prompt.rstrip()}\n"
        return super().build_prompt(system_prompt, user_prompt)

    def prepare_invocation(
        self,
        args: list[str],
        prompt: str,
        *,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
    ) -> tuple[list[str], str, bool]:
        del system_prompt
        del engine_session_mode
        if not engine_session_id:
            return args, prompt, self.close_stdin_after_prompt
        return (
            _codex_exec_resume_args(args, engine_session_id),
            prompt,
            self.close_stdin_after_prompt,
        )

    def prepare_persistent_rpc_invocation(
        self,
        args: list[str],
        prompt: str,
        *,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
        cwd: str = "",
    ) -> tuple[list[str], CliRpcTurnRequest]:
        command_args = _codex_mcp_server_args(args)
        tool_args = _codex_mcp_tool_arguments(
            args,
            prompt,
            system_prompt=system_prompt,
            cwd=cwd,
        )
        reply_tool_args = {"prompt": prompt}
        initial_tool = "codex"
        if engine_session_id and engine_session_mode == "resume":
            initial_tool = "codex-reply"
            tool_args = {
                "prompt": prompt,
                "threadId": engine_session_id,
            }
        return command_args, CliRpcTurnRequest(
            method="tools/call",
            params={
                "name": initial_tool,
                "arguments": tool_args,
            },
            resume_method="tools/call",
            resume_params={
                "name": "codex-reply",
                "arguments": reply_tool_args,
            },
            native_session_param="arguments.threadId",
        )

    def _apply_connection_settings(
        self,
        args: list[str],
        env_vars: dict[str, str],
    ) -> tuple[list[str], dict[str, str]]:
        runtime_env = {
            key: value
            for key, value in env_vars.items()
            if not key.startswith(self.CODEX_ENV_PREFIX)
        }
        next_args = list(args)
        settings = resolve_codex_connection_settings(env_vars)

        if settings.connection in {"", "inherit"}:
            return next_args, runtime_env
        if settings.connection not in {"official", "proxy"}:
            return next_args, runtime_env
        settings = _normalize_codex_settings(settings)

        if settings.model:
            next_args = _with_codex_config(next_args, "model", _toml_string(settings.model))

        next_args = _ensure_codex_flag(next_args, "--ignore-user-config")
        if settings.api_key:
            runtime_env["AGENTHUB_CODEX_PROVIDER_TOKEN"] = settings.api_key
        elif settings.connection == "proxy" and settings.auth_mode != "none":
            raise ValueError(_codex_proxy_key_error(settings))

        provider = self.CODEX_PROVIDER_ID
        next_args = _with_codex_config(next_args, "model_provider", _toml_string(provider))
        next_args = _with_codex_config(
            next_args,
            f"model_providers.{provider}.name",
            _toml_string(settings.provider_name),
        )
        next_args = _with_codex_config(
            next_args,
            f"model_providers.{provider}.base_url",
            _toml_string(settings.base_url),
        )
        next_args = _with_codex_config(
            next_args,
            f"model_providers.{provider}.wire_api",
            _toml_string(settings.wire_api),
        )
        if settings.auth_mode == "openai_auth":
            next_args = _with_codex_config(
                next_args,
                f"model_providers.{provider}.requires_openai_auth",
                "true",
            )
        elif settings.api_key:
            next_args = _with_codex_config(
                next_args,
                f"model_providers.{provider}.env_key",
                _toml_string("AGENTHUB_CODEX_PROVIDER_TOKEN"),
            )
        return next_args, runtime_env

    def parse_json_event(self, data: object, seen_text: bool) -> list[ParsedOutput]:
        if not isinstance(data, dict):
            return super().parse_json_event(data, seen_text)
        event_type = str(data.get("type") or data.get("event") or "")
        metadata_outputs = _codex_session_metadata_outputs(event_type, data)
        if metadata_outputs:
            return metadata_outputs
        if event_type in self.QUIET_EVENT_TYPES:
            return []
        if event_type == "error":
            message = first_string(data, ("message", "error"))
            if message:
                return [ParsedOutput(message, "error", error_trace(message))]
            error = data.get("error")
            if isinstance(error, dict):
                text = first_string(error, ("message", "detail"))
                if text:
                    return [ParsedOutput(text, "error", error_trace(text))]
        text = self._text_from_codex_event(data)
        if text:
            return [self.parsed(text)]
        if not seen_text:
            final_text = first_string(data, ("final_output", "last_message", "result"))
            if final_text:
                return [self.parsed(final_text)]
        trace = codex_event_trace(event_type, data)
        if trace:
            return [ParsedOutput(trace_text(trace), "progress", trace)]
        return []

    def parse_stderr_output(self, text: str) -> list[ParsedOutput]:
        outputs: list[ParsedOutput] = []
        for clean in _codex_stderr_signal_lines(text):
            trace = codex_stderr_trace(clean)
            outputs.append(ParsedOutput(
                trace_text(trace, clean),
                "error" if _looks_like_cli_error(clean) else "progress",
                trace,
            ))
        return outputs

    def parse_raw_line(self, line: str) -> list[ParsedOutput]:
        if line.strip() in self.QUIET_RAW_LINES:
            return []
        if _looks_like_json_fragment_noise(line):
            return []
        return super().parse_raw_line(line)

    @staticmethod
    def _text_from_codex_event(data: dict) -> str:
        for key in ("delta", "text", "content"):
            value = data.get(key)
            if isinstance(value, str) and looks_like_message_event(data):
                return value
        message = data.get("message")
        if isinstance(message, str) and looks_like_message_event(data):
            return message
        if isinstance(message, dict):
            value = extract_content(message.get("content"))
            if value and str(message.get("role") or "assistant") != "user":
                return value
        item = data.get("item")
        if isinstance(item, dict):
            item_type = str(item.get("type") or "")
            if item_type.endswith("message") or item_type in {"message", "assistant_message"}:
                return extract_content(item.get("content")) or str(item.get("text") or "")
        return ""

    @staticmethod
    def _progress_from_codex_event(event_type: str, data: dict) -> str:
        if "command" in data and isinstance(data["command"], str):
            return f"Codex 执行命令: {data['command']}"
        item = data.get("item")
        if isinstance(item, dict):
            item_type = str(item.get("type") or "")
            if "command" in item_type or "tool" in item_type:
                return item_type
        if event_type and any(marker in event_type for marker in ("started", "tool", "exec", "command")):
            return event_type.replace("_", " ")
        return ""


class OpenCodeAdapter(CliAgentAdapter):
    cli_tool = "opencode"
    display_name = "OpenCode"
    close_stdin_after_prompt = True
    expects_json_lines = True
    stdin_mode = "inherit"
    persistent_process_policy = PersistentProcessPolicy(
        supported=True,
        strategy="opencode acp + session/new/session/prompt",
        input_format="acp_session_prompt",
        output_format="acp_json_rpc",
        protocol="acp",
    )
    engine_session_resume_policy = EngineSessionResumePolicy(
        supported=True,
        strategy="opencode run --session <session_id>",
        id_source="session JSON event / session list",
    )
    LEGACY_ARGS = (
        ["--no-color", "--plain"],
        ["run", "--format", "json"],
        ["run", "--format", "json", "--dangerously-skip-permissions"],
    )
    progress_patterns = (
        re.compile(r"\[Tool:\s*[^\]]+\]", re.I),
        re.compile(r"^(?:read|write|edit):", re.I | re.M),
    )

    def build_prompt(self, system_prompt: str, user_prompt: str) -> str:
        if system_prompt.strip():
            return f"{system_prompt.strip()}\n\n{user_prompt.rstrip()}"
        return user_prompt.rstrip()

    def render_prompt_messages(self, messages: list[dict]) -> str:
        latest = _latest_user_message(messages)
        if latest:
            return f"{latest}\n"
        fallback = next(
            (
                str(message.get("content") or "").strip()
                for message in reversed(messages)
                if str(message.get("content") or "").strip() and message.get("role") != "system"
            ),
            "",
        )
        if not fallback:
            return ""
        return f"{fallback}\n"

    def prepare_invocation(
        self,
        args: list[str],
        prompt: str,
        *,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
    ) -> tuple[list[str], str, bool]:
        del system_prompt
        del engine_session_mode
        run_args = self._normalize_run_args(args)
        if engine_session_id:
            run_args = _opencode_with_session(run_args, engine_session_id)
        if not _opencode_has_message_or_command(run_args):
            run_args = [*run_args, prompt]
        return run_args, "", True

    def prepare_persistent_rpc_invocation(
        self,
        args: list[str],
        prompt: str,
        *,
        system_prompt: str = "",
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
        cwd: str = "",
    ) -> tuple[list[str], CliRpcTurnRequest]:
        del system_prompt
        del engine_session_id
        del engine_session_mode
        return _opencode_acp_args(args, cwd), CliRpcTurnRequest(
            method="session/prompt",
            params={
                "prompt": [{"type": "text", "text": prompt.rstrip()}],
            },
            native_session_param="sessionId",
        )

    @classmethod
    def _normalize_run_args(cls, args: list[str]) -> list[str]:
        defaults = DEFAULT_CLI_AGENTS["opencode"]["init_args"]
        if not args or args in cls.LEGACY_ARGS or args[0] != "run":
            return list(defaults)
        return list(args)

    def parse_json_event(self, data: object, seen_text: bool) -> list[ParsedOutput]:
        del seen_text
        if not isinstance(data, dict):
            return super().parse_json_event(data, False)
        acp_outputs = self._parse_acp_session_update(data)
        if acp_outputs:
            return acp_outputs
        metadata_outputs = _opencode_session_metadata_outputs(data)
        if metadata_outputs:
            return metadata_outputs
        event_type = str(data.get("type") or "")
        part = data.get("part")
        if isinstance(part, dict):
            part_type = str(part.get("type") or "")
            if part_type == "text" and isinstance(part.get("text"), str):
                text = part["text"]
                return [self.parsed(text)]
            if part_type == "tool" or part_type.startswith("tool-"):
                name = part.get("tool") or part.get("name") or part_type
                trace = opencode_part_trace(part)
                return [ParsedOutput(
                    f"OpenCode 调用工具: {name}",
                    "progress",
                    trace,
                )]
            if part_type in {"step-start", "step-finish"}:
                trace = opencode_part_trace(part)
                return [ParsedOutput(trace_text(trace or {}, part_type.replace("-", " ")), "progress", trace)]
        if event_type in {"step_start", "step_finish"}:
            return [self.parsed(event_type.replace("_", " "), "progress")]
        if event_type == "error":
            text = first_string(data, ("message", "error"))
            return [ParsedOutput(text, "error", error_trace(text))] if text else []
        text = first_string(data, ("text", "message", "content"))
        if text:
            return [self.parsed(text)]
        return []

    def _parse_acp_session_update(self, data: dict) -> list[ParsedOutput]:
        session_update = str(data.get("sessionUpdate") or "")
        if not session_update:
            return []
        if session_update in {"agent_message_chunk", "agent_thought_chunk"}:
            content = data.get("content")
            text = _acp_content_text(content)
            if not text:
                return []
            if session_update == "agent_thought_chunk":
                return [self.parsed(text, "progress")]
            return [self.parsed(text)]
        if session_update == "tool_call":
            trace = opencode_part_trace(data)
            title = first_string(data, ("title", "kind", "status")) or "tool_call"
            return [ParsedOutput(f"OpenCode 调用工具: {title}", "progress", trace)]
        if session_update == "tool_call_update":
            trace = opencode_part_trace(data)
            title = first_string(data, ("title", "status", "kind")) or "tool_call_update"
            return [ParsedOutput(f"OpenCode 工具更新: {title}", "progress", trace)]
        if session_update in {
            "user_message_chunk",
            "available_commands",
            "available_commands_update",
            "mode_change",
            "current_mode_update",
        }:
            return []
        return [self.parsed(session_update.replace("_", " "), "progress")]


_ADAPTERS: dict[str, CliAgentAdapter] = {
    "claude_code": ClaudeCodeAdapter(),
    "codex": CodexAdapter(),
    "opencode": OpenCodeAdapter(),
    "custom": CliAgentAdapter(),
}


def get_cli_adapter(cli_tool: str | None) -> CliAgentAdapter:
    return _ADAPTERS.get(cli_tool or "custom", _ADAPTERS["custom"])


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if str(item)]


def _json_dict(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v is not None}


def _normalize_claude_print_args(args: list[str]) -> list[str]:
    result = list(args)
    if not _has_claude_flag(result, "-p", "--print"):
        result.insert(0, "-p")
    if not _has_claude_option_value(result, "--output-format"):
        result.extend(["--output-format", "stream-json"])
    if not _has_claude_flag(result, "--verbose"):
        result.append("--verbose")
    if not _has_claude_flag(result, "--include-partial-messages"):
        result.append("--include-partial-messages")
    return _without_claude_flag(result, "--no-session-persistence")


def _normalize_claude_streaming_input_args(args: list[str]) -> list[str]:
    result = _normalize_claude_print_args(args)
    result = _without_claude_option(result, "--input-format")
    result.extend(["--input-format", "stream-json"])
    return result


def _without_claude_session_args(args: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"-c", "--continue"}:
            index += 1
            continue
        if arg in {"-r", "--resume"}:
            index += 2 if index + 1 < len(args) and not args[index + 1].startswith("-") else 1
            continue
        if arg == "--session-id":
            index += 2
            continue
        if arg.startswith("--resume=") or arg.startswith("--session-id="):
            index += 1
            continue
        result.append(arg)
        index += 1
    return result


def _without_claude_flag(args: list[str], flag: str) -> list[str]:
    return [arg for arg in args if arg != flag and not arg.startswith(f"{flag}=")]


def _without_claude_option(args: list[str], option: str) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == option:
            index += 2 if index + 1 < len(args) else 1
            continue
        if arg.startswith(f"{option}="):
            index += 1
            continue
        result.append(arg)
        index += 1
    return result


def _has_claude_flag(args: list[str], *flags: str) -> bool:
    return any(arg in flags for arg in args)


def _has_claude_option_value(args: list[str], option: str) -> bool:
    return any(arg == option or arg.startswith(f"{option}=") for arg in args)


def _first_non_empty_string(data: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _claude_sdk_user_message(text: str) -> str:
    payload = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        },
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _agent_with_runtime_config(
    agent: AgentConfig,
    args: list[str],
    env_vars: dict[str, str],
):
    return SimpleNamespace(
        id=agent.id,
        name=agent.name,
        executable=agent.executable,
        init_args=json.dumps(args, ensure_ascii=False),
        env_vars=json.dumps(env_vars, ensure_ascii=False),
    )


def _codex_exec_resume_args(args: list[str], engine_session_id: str) -> list[str]:
    result = ["exec", "resume"]
    index = 1 if args and args[0] in {"exec", "e"} else 0
    while index < len(args):
        arg = args[index]
        if arg in {"-", "resume"} or not arg:
            index += 1
            continue
        if not arg.startswith("-"):
            index += 1
            continue
        if arg == "--color" or arg.startswith("--color="):
            index += 2 if arg == "--color" and index + 1 < len(args) else 1
            continue
        if arg in _CODEX_EXEC_ONLY_VALUE_FLAGS:
            index += 2 if index + 1 < len(args) else 1
            continue
        if arg in _CODEX_RESUME_VALUE_FLAGS:
            if index + 1 < len(args):
                result.extend([arg, args[index + 1]])
                index += 2
            else:
                result.append(arg)
                index += 1
            continue
        if _has_prefixed_option(arg, _CODEX_RESUME_VALUE_FLAGS):
            result.append(arg)
            index += 1
            continue
        if arg in _CODEX_RESUME_BOOL_FLAGS:
            result.append(arg)
            index += 1
            continue
        if _has_prefixed_option(arg, _CODEX_RESUME_BOOL_FLAGS):
            result.append(arg)
            index += 1
            continue
        index += 1

    if "--json" not in result:
        result.append("--json")
    result.extend([engine_session_id, "-"])
    return result


_CODEX_RESUME_VALUE_FLAGS = {
    "-c",
    "--config",
    "--enable",
    "--disable",
    "-i",
    "--image",
    "-m",
    "--model",
    "--output-schema",
    "-o",
    "--output-last-message",
}

_CODEX_RESUME_BOOL_FLAGS = {
    "--strict-config",
    "--dangerously-bypass-approvals-and-sandbox",
    "--dangerously-bypass-hook-trust",
    "--skip-git-repo-check",
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--json",
}

_CODEX_EXEC_ONLY_VALUE_FLAGS = {
    "-C",
    "--cd",
    "--add-dir",
    "-s",
    "--sandbox",
    "-a",
    "--ask-for-approval",
    "-p",
    "--profile",
    "--local-provider",
}

_CODEX_MCP_SERVER_VALUE_FLAGS = {
    "-c",
    "--config",
    "--enable",
    "--disable",
}

_CODEX_MCP_SERVER_BOOL_FLAGS = {
    "--strict-config",
}


def _codex_mcp_server_args(args: list[str]) -> list[str]:
    result = ["mcp-server"]
    index = 1 if args and args[0] in {"exec", "e"} else 0
    while index < len(args):
        arg = args[index]
        if arg in {"-", "resume"} or not arg:
            index += 1
            continue
        if arg in _CODEX_MCP_SERVER_VALUE_FLAGS:
            if index + 1 < len(args):
                result.extend([arg, args[index + 1]])
                index += 2
            else:
                result.append(arg)
                index += 1
            continue
        if _has_prefixed_option(arg, _CODEX_MCP_SERVER_VALUE_FLAGS):
            result.append(arg)
            index += 1
            continue
        if arg in _CODEX_MCP_SERVER_BOOL_FLAGS or _has_prefixed_option(arg, _CODEX_MCP_SERVER_BOOL_FLAGS):
            result.append(arg)
            index += 1
            continue
        index += _codex_arg_step(args, index)
    return result


def _codex_mcp_tool_arguments(
    args: list[str],
    prompt: str,
    *,
    system_prompt: str,
    cwd: str,
) -> dict:
    result: dict = {"prompt": prompt}
    if cwd:
        result["cwd"] = cwd
    if system_prompt.strip():
        result["developer-instructions"] = system_prompt.strip()
    config: dict = {}
    index = 1 if args and args[0] in {"exec", "e"} else 0
    while index < len(args):
        arg = args[index]
        value = _option_value(args, index)
        if arg in {"-m", "--model"} and value:
            result["model"] = value
        elif arg.startswith("--model="):
            result["model"] = arg.split("=", 1)[1]
        elif arg in {"-s", "--sandbox"} and value:
            result["sandbox"] = value
        elif arg.startswith("--sandbox="):
            result["sandbox"] = arg.split("=", 1)[1]
        elif arg in {"-a", "--ask-for-approval"} and value:
            result["approval-policy"] = value
        elif arg.startswith("--ask-for-approval="):
            result["approval-policy"] = arg.split("=", 1)[1]
        elif arg == "--dangerously-bypass-approvals-and-sandbox":
            result["sandbox"] = "danger-full-access"
            result["approval-policy"] = "never"
        elif arg == "--skip-git-repo-check":
            config["skip_git_repo_check"] = True
        index += _codex_arg_step(args, index)
    if config:
        result["config"] = config
    return result


def _codex_arg_step(args: list[str], index: int) -> int:
    arg = args[index]
    if arg.startswith("--") and "=" in arg:
        return 1
    if arg in {
        "-c",
        "--config",
        "--enable",
        "--disable",
        "-i",
        "--image",
        "-m",
        "--model",
        "--output-schema",
        "-o",
        "--output-last-message",
        "-C",
        "--cd",
        "--add-dir",
        "-s",
        "--sandbox",
        "-a",
        "--ask-for-approval",
        "-p",
        "--profile",
        "--local-provider",
        "--color",
    }:
        return 2 if index + 1 < len(args) else 1
    return 1


def _option_value(args: list[str], index: int) -> str:
    if index + 1 >= len(args):
        return ""
    value = args[index + 1]
    return "" if value.startswith("-") else value


def _codex_session_metadata_outputs(event_type: str, data: dict) -> list[ParsedOutput]:
    lower = event_type.lower()
    if not ("session" in lower or "thread" in lower):
        return []
    engine_session_id = _session_id_from_event(data, ("thread", "session", "conversation"))
    if not engine_session_id:
        return []
    return [_engine_session_metadata_output(
        engine_session_id,
        source=f"codex_{event_type or 'session_event'}",
        cli_tool="codex",
    )]


def _opencode_session_metadata_outputs(data: dict) -> list[ParsedOutput]:
    event_type = str(data.get("type") or data.get("event") or "").lower()
    if not ("session" in event_type or "init" in event_type):
        return []
    engine_session_id = _session_id_from_event(data, ("session",))
    if not engine_session_id:
        return []
    return [_engine_session_metadata_output(
        engine_session_id,
        source=f"opencode_{event_type or 'session_event'}",
        cli_tool="opencode",
    )]


def _engine_session_metadata_output(
    engine_session_id: str,
    *,
    source: str,
    cli_tool: str,
) -> ParsedOutput:
    return ParsedOutput(
        "",
        "metadata",
        metadata={
            "engineSessionId": engine_session_id,
            "engineSessionSource": source,
            "cliTool": cli_tool,
        },
    )


def _session_id_from_event(data: dict, nested_keys: tuple[str, ...]) -> str:
    direct = _first_non_empty_string(
        data,
        (
            "session_id",
            "sessionId",
            "sessionID",
            "thread_id",
            "threadId",
            "conversation_id",
            "conversationId",
        ),
    )
    if direct:
        return direct
    for key in nested_keys:
        nested = data.get(key)
        if isinstance(nested, dict):
            value = _first_non_empty_string(
                nested,
                ("id", "session_id", "sessionId", "sessionID", "thread_id", "threadId"),
            )
            if value:
                return value
    value = data.get("id")
    if isinstance(value, str) and (
        value.startswith("ses_")
        or value.startswith("thread_")
        or bool(re.fullmatch(r"[0-9a-fA-F-]{32,36}", value.strip()))
    ):
        return value.strip()
    return ""


def _has_prefixed_option(arg: str, options: set[str]) -> bool:
    return any(arg.startswith(f"{option}=") for option in options if option.startswith("--"))


def _with_codex_config(args: list[str], key: str, value: str) -> list[str]:
    clean_args = _without_codex_config(args, key)
    insert_at = _codex_config_insert_index(clean_args)
    return [
        *clean_args[:insert_at],
        "-c",
        f"{key}={value}",
        *clean_args[insert_at:],
    ]


def _without_codex_config(args: list[str], key: str) -> list[str]:
    result: list[str] = []
    index = 0
    prefix = f"{key}="
    while index < len(args):
        arg = args[index]
        if arg in {"-c", "--config"} and index + 1 < len(args):
            value = args[index + 1]
            if value.startswith(prefix):
                index += 2
                continue
            result.extend([arg, value])
            index += 2
            continue
        if arg.startswith("--config="):
            value = arg[len("--config="):]
            if value.startswith(prefix):
                index += 1
                continue
        result.append(arg)
        index += 1
    return result


def _ensure_codex_flag(args: list[str], flag: str) -> list[str]:
    if flag in args:
        return args
    insert_at = 1 if args and args[0] in {"exec", "e"} else 0
    return [*args[:insert_at], flag, *args[insert_at:]]


def _codex_config_insert_index(args: list[str]) -> int:
    index = 1 if args and args[0] in {"exec", "e"} else 0
    while index < len(args):
        arg = args[index]
        if arg in {"-c", "--config"} and index + 1 < len(args):
            index += 2
            continue
        if arg.startswith("--config="):
            index += 1
            continue
        break
    return index


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _normalize_codex_settings(settings: CodexConnectionSettings) -> CodexConnectionSettings:
    base_url = settings.base_url
    auth_mode = settings.auth_mode
    if settings.connection == "official" and not base_url:
        base_url = "https://api.openai.com/v1"
    if settings.connection == "proxy":
        base_url = _codex_proxy_base_url(base_url)
        if settings.api_key:
            auth_mode = "env_key"
        elif auth_mode in {"openai_auth", "none", ""}:
            auth_mode = "proxy_key_missing"
    if settings.connection == "official" and auth_mode in {"", "none"}:
        auth_mode = "env_key" if settings.api_key else "openai_auth"
    return CodexConnectionSettings(
        connection=settings.connection,
        base_url=base_url,
        api_key=settings.api_key,
        model=settings.model,
        auth_mode=auth_mode,
        wire_api=settings.wire_api,
        provider_name=settings.provider_name,
        provider_id=settings.provider_id,
        source=settings.source,
        api_key_source=settings.api_key_source,
        missing_env_key=settings.missing_env_key,
        has_chatgpt_auth=settings.has_chatgpt_auth,
    )


def _codex_proxy_key_error(settings: CodexConnectionSettings) -> str:
    if settings.missing_env_key:
        return (
            f"检测到本机 Codex 中转配置使用环境变量 {settings.missing_env_key}，"
            "但 AgentHub 启动环境和 CODEX_HOME/.env 中都未找到这个值。"
        )
    if settings.source == "codex_config":
        if settings.has_chatgpt_auth:
            return (
                "检测到本机 Codex 使用第三方中转 URL，但当前只有 ChatGPT 登录态，"
                "没有中转站 API Key。第三方中转不能使用本机 Codex 的 ChatGPT 登录态；"
                "请在 CODEX_HOME/.env 写入 OPENAI_API_KEY 或 CODEX_API_KEY，"
                "或在 config.toml 的该 provider 中设置 env_key 指向对应环境变量。"
            )
        return (
            "检测到本机 Codex 使用第三方中转 URL，但未在 CODEX_HOME/.env、auth.json "
            "或当前环境中找到可用于中转的 API Key。请在本机 Codex 配置中使用 env_key，"
            "或把对应 key 写入 CODEX_HOME/.env。"
        )
    return "Codex 中转模式需要中转 API Key，不能使用本机 ChatGPT 登录态。"


def _codex_proxy_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise ValueError("Codex 中转模式需要填写 Base URL，例如 https://example.com/v1。")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Codex Base URL 必须是完整的 http(s) URL。")
    if parsed.path.rstrip("/").endswith("/v1"):
        return value
    path = f"{parsed.path.rstrip('/')}/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def render_transcript_prompt(messages: list[dict]) -> str:
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "").strip()
        if not content or role == "system":
            continue
        label = {
            "user": "User",
            "assistant": "Assistant",
        }.get(role, role.title())
        lines.append(f"{label}:\n{content}")
    return "\n\n".join(lines).rstrip() + "\n" if lines else ""


def _opencode_has_message_or_command(args: list[str]) -> bool:
    index = 1 if args and args[0] == "run" else 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            return index + 1 < len(args)
        if not arg.startswith("-"):
            return True
        if arg == "--command":
            return index + 1 < len(args)
        if arg.startswith("--command="):
            return True
        if arg in {
            "--format",
            "-m",
            "--model",
            "--agent",
            "-f",
            "--file",
            "--title",
            "--attach",
            "-p",
            "--password",
            "-u",
            "--username",
            "--dir",
            "--port",
            "--variant",
            "-s",
            "--session",
        }:
            index += 2
            continue
        index += 1
    return False


def _opencode_acp_args(args: list[str], cwd: str) -> list[str]:
    if args and args[0] == "acp":
        result = list(args)
    else:
        result = ["acp"]
        if "--pure" in args:
            result.append("--pure")
        for option in ("--print-logs", "--log-level"):
            if option in args:
                index = args.index(option)
                result.append(option)
                if option == "--log-level" and index + 1 < len(args):
                    result.append(args[index + 1])
    if cwd and not _has_opencode_option(result, "--cwd"):
        result.extend(["--cwd", cwd])
    return result


def _has_opencode_option(args: list[str], option: str) -> bool:
    return any(arg == option or arg.startswith(f"{option}=") for arg in args)


def _opencode_with_session(args: list[str], engine_session_id: str) -> list[str]:
    clean = _without_opencode_session_args(args)
    insert_at = 1 if clean and clean[0] == "run" else 0
    return [
        *clean[:insert_at],
        "--session",
        engine_session_id,
        *clean[insert_at:],
    ]


def _without_opencode_session_args(args: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"-c", "--continue", "--fork"}:
            index += 1
            continue
        if arg in {"-s", "--session"}:
            index += 2 if index + 1 < len(args) else 1
            continue
        if arg.startswith("--session="):
            index += 1
            continue
        result.append(arg)
        index += 1
    return result


def _latest_user_message(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            return content
    return ""


def _acp_content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
        nested = content.get("content")
        if nested is not None:
            return _acp_content_text(nested)
        return ""
    if isinstance(content, list):
        return "".join(_acp_content_text(item) for item in content)
    return ""


def _codex_stderr_signal_lines(text: str) -> list[str]:
    signal: list[str] = []
    for line in str(text).replace("\r\n", "\n").splitlines():
        clean = line.strip()
        if not clean:
            continue
        if _is_codex_stderr_noise(clean):
            continue
        signal.append(clean)
    return signal


def _is_codex_stderr_noise(line: str) -> bool:
    return any(pattern.search(line) for pattern in CodexAdapter.STDERR_NOISE_PATTERNS)


def _looks_like_cli_error(text: str) -> bool:
    return bool(re.search(r"\b(ERROR|Error|error|failed|Failed|exception|traceback|unauthorized|forbidden)\b", text))


def _looks_like_json_fragment_noise(line: str) -> bool:
    clean = line.strip()
    if len(clean) < 40:
        return False
    if re.search(r'"object"\s*:\s*"list"|owned_by|display_name|gpt-image|model"', clean):
        return True
    return clean.startswith(("{", "[", '"')) and clean.endswith(("}", "]", '"'))
