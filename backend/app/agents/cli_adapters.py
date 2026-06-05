"""Per-CLI adapters：把真实 CLI stdout/stderr 解析成 AgentHub 事件。"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import AsyncIterator
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


class CliAgentAdapter:
    cli_tool = "custom"
    display_name = "CLI Agent"
    progress_patterns: tuple[re.Pattern, ...] = ()
    close_stdin_after_prompt = False
    expects_json_lines = False
    stdin_mode = "pipe"

    async def stream(
        self,
        *,
        agent: AgentConfig,
        session_id: str,
        cwd: str,
        user_prompt: str,
        system_prompt: str = "",
        event_bus=None,
    ) -> AsyncIterator[CliEvent]:
        interceptor = PromptInterceptor()
        executable = agent.executable or DEFAULT_CLI_AGENTS.get(
            self.cli_tool, {},
        ).get("executable", "")
        args = _json_list(agent.init_args)
        env_vars = _json_dict(agent.env_vars)
        prompt = self.build_prompt(system_prompt, user_prompt)
        args, stdin_prompt, close_stdin = self.prepare_invocation(args, prompt)

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
                        ),
                    )
                    continue
                if chunk.event_type == "completed":
                    for parsed in parser.flush():
                        yield CliEvent(
                            "agent.output",
                            chunk.process_id,
                            chunk=parsed.text,
                            chunk_type=parsed.chunk_type,
                            trace=parsed.trace,
                        )
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
                        yield CliEvent(
                            "agent.output",
                            chunk.process_id,
                            chunk=parsed.text,
                            chunk_type=parsed.chunk_type,
                            trace=parsed.trace,
                        )
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
                    yield CliEvent(
                        "agent.output",
                        chunk.process_id,
                        chunk=parsed.text,
                        chunk_type=parsed.chunk_type,
                        trace=parsed.trace,
                    )
        except CliExecutableNotFound:
            yield CliEvent(
                "error",
                "",
                error=f"未找到 '{executable}' 命令。请安装 CLI 后重试。",
            )

        except CliSubprocessNotSupported as exc:
            yield CliEvent("error", "", error=str(exc))

    def build_prompt(self, system_prompt: str, user_prompt: str) -> str:
        return f"{user_prompt.rstrip()}\n"

    def render_prompt_messages(self, messages: list[dict]) -> str:
        return render_transcript_prompt(messages)

    def prepare_invocation(self, args: list[str], prompt: str) -> tuple[list[str], str, bool]:
        return args, prompt, self.close_stdin_after_prompt

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
    progress_patterns = (
        re.compile(r"^(?:⏺|⎿)\s+", re.M),
        re.compile(r"调用工具|正在读取|正在写入"),
    )

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
            if data.get("is_error") is True:
                text = first_string(data, ("result", "message", "error"))
                return [ParsedOutput(text, "error", error_trace(text))] if text else []
            if not seen_text and isinstance(data.get("result"), str):
                text = data["result"]
                return [self.parsed(text)]
            return []
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


class CodexAdapter(CliAgentAdapter):
    cli_tool = "codex"
    display_name = "Codex"
    close_stdin_after_prompt = True
    expects_json_lines = True
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
            event_bus=event_bus,
        ):
            yield event

    def build_prompt(self, system_prompt: str, user_prompt: str) -> str:
        if system_prompt.strip():
            return f"{system_prompt.strip()}\n\n{user_prompt.rstrip()}\n"
        return super().build_prompt(system_prompt, user_prompt)

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

    def prepare_invocation(self, args: list[str], prompt: str) -> tuple[list[str], str, bool]:
        run_args = self._normalize_run_args(args)
        if not _opencode_has_message_or_command(run_args):
            run_args = [*run_args, prompt]
        return run_args, "", True

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
        }:
            index += 2
            continue
        index += 1
    return False


def _latest_user_message(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            return content
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
