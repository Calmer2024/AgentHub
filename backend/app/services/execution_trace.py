"""Structured execution trace metadata for CLI-backed messages."""

from __future__ import annotations

import uuid
from typing import Any

from ..core.timezone import china_now_iso

MAX_TRACE_ITEMS = 300
MAX_TRACE_TEXT_CHARS = 1200
MAX_TRACE_RAW_CHARS = 4000


def utc_iso() -> str:
    return china_now_iso()


class ExecutionTraceBuilder:
    """Collect concise, readable CLI execution events for message metadata."""

    def __init__(self, *, agent_name: str, cli_tool: str, workspace_path: str):
        self._trace = {
            "status": "running",
            "agentName": agent_name,
            "cliTool": cli_tool,
            "workspacePath": workspace_path,
            "startedAt": utc_iso(),
            "completedAt": None,
            "processId": None,
            "exitCode": None,
            "items": [],
        }

    @property
    def process_id(self) -> str | None:
        value = self._trace.get("processId")
        return str(value) if value else None

    def set_process(self, process_id: str) -> None:
        if process_id:
            self._trace["processId"] = process_id

    def add(
        self,
        *,
        kind: str,
        text: str,
        source: str = "system",
        chunk_type: str | None = None,
        process_id: str | None = None,
        trace: dict[str, Any] | None = None,
    ) -> dict | None:
        text = _normalize_text(text)
        trace = dict(trace or {})
        if not text:
            text = _normalize_text(str(trace.get("detail") or trace.get("title") or ""))
        if not text:
            return None
        if process_id:
            self.set_process(process_id)
        detail = _normalize_text(str(trace.get("detail") or ""))
        raw = _normalize_text(str(trace.get("raw") or ""))
        item = {
            "id": f"trace_{uuid.uuid4().hex[:12]}",
            "kind": str(trace.get("kind") or kind),
            "text": text[:MAX_TRACE_TEXT_CHARS],
            "title": _optional_str(trace.get("title"), MAX_TRACE_TEXT_CHARS),
            "detail": detail[:MAX_TRACE_TEXT_CHARS] if detail else None,
            "summary": _optional_str(trace.get("summary"), MAX_TRACE_TEXT_CHARS),
            "action": _optional_str(trace.get("action"), 80),
            "target": _optional_str(trace.get("target"), 500),
            "command": _optional_str(trace.get("command"), MAX_TRACE_TEXT_CHARS),
            "toolName": _optional_str(trace.get("toolName"), 120),
            "provider": _optional_str(trace.get("provider"), 80),
            "level": _optional_str(trace.get("level"), 40),
            "raw": raw[:MAX_TRACE_RAW_CHARS] if raw and raw != text else None,
            "source": source,
            "chunkType": chunk_type,
            "processId": process_id or self.process_id,
            "timestamp": utc_iso(),
        }
        for key, value in trace.items():
            if key in item or value is None:
                continue
            if isinstance(value, (str, int, float, bool, list, dict)):
                item[key] = value
        items = list(self._trace.get("items") or [])
        items.append(item)
        self._trace["items"] = items[-MAX_TRACE_ITEMS:]
        return item

    def complete(self, *, status: str = "completed", exit_code: int | None = None) -> None:
        self._trace["status"] = status
        self._trace["completedAt"] = utc_iso()
        self._trace["exitCode"] = exit_code

    def metadata(self) -> dict:
        return {"executionTrace": self._trace}


def merge_trace_metadata(metadata: dict, trace: ExecutionTraceBuilder) -> dict:
    merged = dict(metadata)
    merged.update(trace.metadata())
    return merged


def _normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in str(text).replace("\r\n", "\n").splitlines()]
    return "\n".join(line for line in lines if line.strip()).strip()


def _optional_str(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = _normalize_text(str(value))
    return text[:limit] if text else None
