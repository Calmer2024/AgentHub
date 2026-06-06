"""CLI stdout/stderr 分层解析器。"""

import json
from typing import Protocol

from .cli_events import ParsedOutput


class OutputAdapter(Protocol):
    expects_json_lines: bool

    def classify(self, chunk: str) -> str: ...

    def parse_json_event(self, data: object, seen_text: bool) -> list[ParsedOutput]: ...

    def parse_stderr_output(self, text: str) -> list[ParsedOutput]: ...

    def parse_raw_line(self, line: str) -> list[ParsedOutput]: ...


class CliOutputParser:
    """每次 CLI 执行独享的输出 parser，避免 adapter 单例共享状态。"""

    def __init__(self, adapter: OutputAdapter):
        self.adapter = adapter
        self._line_buffer = ""
        self._seen_text = False
        self._suppressing_html_stderr = False
        self._reported_html_stderr = False
        self._suppressing_noisy_stderr_line = False

    def feed_stdout(self, text: str) -> list[ParsedOutput]:
        if not self.adapter.expects_json_lines:
            return self._mark([ParsedOutput(text, self.adapter.classify(text))])
        self._line_buffer += text
        outputs: list[ParsedOutput] = []
        while "\n" in self._line_buffer:
            line, self._line_buffer = self._line_buffer.split("\n", 1)
            outputs.extend(self._parse_json_line(line))
        return self._mark(outputs)

    def feed_stderr(self, text: str) -> list[ParsedOutput]:
        text = self._suppress_noisy_stderr_line(text)
        if not text:
            return []
        html_output = self._html_stderr_summary(text)
        if html_output is not None:
            return html_output
        return self.adapter.parse_stderr_output(text)

    def flush(self) -> list[ParsedOutput]:
        if not self._line_buffer.strip():
            self._line_buffer = ""
            return []
        line = self._line_buffer
        self._line_buffer = ""
        return self._mark(self._parse_json_line(line))

    def _parse_json_line(self, line: str) -> list[ParsedOutput]:
        stripped = line.strip()
        if not stripped:
            return []
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            raw_parser = getattr(self.adapter, "parse_raw_line", None)
            if callable(raw_parser):
                return raw_parser(stripped)
            return [ParsedOutput(stripped + "\n", self.adapter.classify(stripped))]
        return self.adapter.parse_json_event(data, self._seen_text)

    def _mark(self, outputs: list[ParsedOutput]) -> list[ParsedOutput]:
        for output in outputs:
            if output.chunk_type == "text" and output.text.strip():
                self._seen_text = True
        return outputs

    def _html_stderr_summary(self, text: str) -> list[ParsedOutput] | None:
        lower = text.lower()
        starts_html = "<!doctype html" in lower or "<html" in lower
        if starts_html:
            self._suppressing_html_stderr = "</html>" not in lower
            if self._reported_html_stderr:
                return []
            self._reported_html_stderr = True
            return [ParsedOutput(
                "Codex 收到了 HTML 网页响应；请确认 Codex Base URL 指向 OpenAI 兼容 API 端点，"
                "通常需要以 /v1 结尾，而不是中转站首页。",
                "error",
            )]

        if self._suppressing_html_stderr:
            self._suppressing_html_stderr = "</html>" not in lower
            return []
        return None

    def _suppress_noisy_stderr_line(self, text: str) -> str:
        lower = text.lower()
        if self._suppressing_noisy_stderr_line:
            if "\n" not in text:
                return ""
            self._suppressing_noisy_stderr_line = False
            return text.split("\n", 1)[1]
        if (
            "codex_models_manager::manager: failed to refresh available models" in lower
            and "body:" in lower
        ):
            if "\n" not in text:
                self._suppressing_noisy_stderr_line = True
                return ""
            return text.split("\n", 1)[1]
        return text


def json_to_readable_text(data: object) -> str:
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return ""
    return first_string(data, ("text", "content", "message", "result"))


def looks_like_message_event(data: dict) -> bool:
    event_type = str(data.get("type") or data.get("event") or "").lower()
    role = str(data.get("role") or "").lower()
    if role == "user":
        return False
    return any(marker in event_type for marker in ("message", "delta", "output", "response"))


def extract_content(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    chunks.append(text)
        return "".join(chunks)
    return ""


def first_string(data: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
    return ""
