"""Semantic trace extraction for CLI adapters."""

from __future__ import annotations

import json
import re
from pathlib import PurePath
from typing import Any


TRACE_KINDS = {"process", "progress", "tool", "command", "file", "artifact", "prompt", "error", "info"}


def process_start_trace(agent_name: str, command: list[str] | None, cwd: str | None, pid: int | None) -> dict:
    argv = list(command or [])
    command_text = _shell_join(argv)
    detail_parts = []
    if command_text:
        detail_parts.append(command_text)
    if cwd:
        detail_parts.append(f"cwd: {cwd}")
    if pid:
        detail_parts.append(f"pid: {pid}")
    return {
        "kind": "process",
        "title": f"启动 {agent_name}",
        "detail": "\n".join(detail_parts),
        "command": command_text or None,
        "target": cwd,
        "action": "start",
        "provider": "AgentHub",
        "level": "info",
        "pid": pid,
    }


def process_completed_trace(agent_name: str, exit_code: int | None) -> dict:
    ok = exit_code in (0, None)
    return {
        "kind": "process",
        "title": f"{agent_name} 执行结束",
        "detail": "exit code: 0" if exit_code is None else f"exit code: {exit_code}",
        "action": "complete",
        "level": "success" if ok else "error",
    }


def prompt_trace(text: str) -> dict:
    return {
        "kind": "prompt",
        "title": "等待确认",
        "detail": _one_line(text),
        "action": "confirm",
        "level": "warning",
        "raw": text,
    }


def error_trace(text: str) -> dict:
    return {
        "kind": "error",
        "title": _error_title(text),
        "detail": _trim_log_prefix(text),
        "action": "error",
        "level": "error",
        "raw": text,
    }


def artifact_trace(text: str) -> dict:
    target = _first_path(text)
    return {
        "kind": "artifact",
        "title": f"检测到产物输出{f': {target}' if target else ''}",
        "detail": _summarize_text(text, 500),
        "target": target,
        "action": "artifact",
        "level": "info",
        "raw": text,
    }


def generic_progress_trace(text: str, *, provider: str = "CLI") -> dict:
    command = _extract_command(text)
    target = _first_path(text)
    kind = "command" if command else "progress"
    return {
        "kind": kind,
        "title": _progress_title(text),
        "detail": _trim_log_prefix(text),
        "command": command,
        "target": target,
        "provider": provider,
        "action": _guess_action(text, command=command),
        "level": "info",
        "raw": text if "\n" in text else None,
    }


def claude_tool_trace(item: dict[str, Any]) -> dict:
    name = str(item.get("name") or "tool")
    payload = item.get("input")
    action = _normalize_action(name)
    command = _command_from_payload(name, payload)
    target = _target_from_payload(payload)
    detail = _payload_detail(payload)
    title = _tool_title("Claude Code", name, action, target)
    return {
        "kind": "command" if command else "tool",
        "title": title,
        "detail": detail,
        "command": command,
        "target": target,
        "toolName": name,
        "provider": "Claude Code",
        "action": action,
        "level": "info",
        "raw": _json_preview(payload),
    }


def claude_thinking_trace(text: str) -> dict:
    return {
        "kind": "progress",
        "title": "Claude Code 正在思考",
        "detail": _summarize_text(text, 1200),
        "provider": "Claude Code",
        "action": "think",
        "level": "info",
    }


def claude_tool_result_trace(data: dict[str, Any]) -> dict | None:
    result = data.get("tool_use_result")
    message = data.get("message")
    content = _tool_result_content(message)
    if not isinstance(result, dict) and not content:
        return None

    payload = result if isinstance(result, dict) else {}
    file_info = payload.get("file")
    target = _target_from_payload(file_info) if isinstance(file_info, dict) else None
    target = target or _target_from_payload(payload)
    stdout = _string_value(payload.get("stdout"))
    stderr = _string_value(payload.get("stderr"))
    is_error = payload.get("is_error") is True or payload.get("interrupted") is True
    detail = _tool_result_detail(payload, content)
    title = "Claude Code 工具结果"
    if stdout or stderr:
        title = "Claude Code 命令输出"
    elif target:
        title = f"Claude Code 读取结果: {target}"

    return {
        "kind": "error" if is_error else ("file" if target and not stdout else "tool"),
        "title": title,
        "detail": detail,
        "target": target,
        "provider": "Claude Code",
        "action": "result",
        "level": "error" if is_error else "success",
        "output": _summarize_text(stdout or content or _json_preview(payload), 1200),
        "stderr": _summarize_text(stderr, 1200) if stderr else None,
        "raw": _json_preview(data),
    }


def claude_event_trace(event_type: str, data: dict[str, Any]) -> dict | None:
    subtype = str(data.get("subtype") or "")
    if subtype:
        return {
            "kind": "progress",
            "title": _humanize_event(subtype),
            "detail": _json_preview(data),
            "provider": "Claude Code",
            "action": _guess_action(subtype),
            "level": "info",
        }
    if event_type.endswith("_started") or event_type.endswith("_completed"):
        return {
            "kind": "progress",
            "title": _humanize_event(event_type),
            "detail": _json_preview(data),
            "provider": "Claude Code",
            "action": _guess_action(event_type),
            "level": "info",
        }
    return None


def codex_event_trace(event_type: str, data: dict[str, Any]) -> dict | None:
    item = data.get("item")
    if isinstance(item, dict):
        item_trace = codex_item_trace(event_type, item)
        if item_trace:
            return item_trace
    if "command" in data and isinstance(data["command"], str):
        return codex_item_trace(event_type, data)
    if event_type and any(marker in event_type for marker in ("tool", "exec", "command")):
        return {
            "kind": "tool" if "tool" in event_type else "command",
            "title": _humanize_event(event_type),
            "detail": _json_preview(data),
            "provider": "Codex",
            "action": _guess_action(event_type),
            "level": "info",
        }
    return None


def codex_item_trace(event_type: str, item: dict[str, Any]) -> dict | None:
    item_type = str(item.get("type") or item.get("kind") or event_type)
    command = _codex_command(item)
    tool_name = _codex_tool_name(item_type, item)
    target = _target_from_payload(item)
    if command:
        status = _string_value(item.get("status"))
        exit_code = item.get("exit_code")
        output = _codex_output(item)
        return {
            "kind": "command",
            "title": _codex_command_title(status, exit_code),
            "detail": _codex_item_detail(item),
            "command": command,
            "target": target,
            "toolName": tool_name,
            "provider": "Codex",
            "action": "run",
            "level": _command_level(status, exit_code),
            "status": status or None,
            "exitCode": exit_code if isinstance(exit_code, int) else None,
            "output": _summarize_text(output, 1200) if output else None,
            "raw": _json_preview(item),
        }
    if "tool" in item_type or tool_name:
        return {
            "kind": "tool",
            "title": _tool_title("Codex", tool_name or item_type, _guess_action(item_type), target),
            "detail": _codex_item_detail(item),
            "target": target,
            "toolName": tool_name or item_type,
            "provider": "Codex",
            "action": _guess_action(item_type),
            "level": "info",
            "raw": _json_preview(item),
        }
    if item_type in {"reasoning", "plan", "status"}:
        detail = _codex_item_detail(item)
        return {
            "kind": "progress",
            "title": _humanize_event(item_type),
            "detail": detail,
            "provider": "Codex",
            "action": item_type,
            "level": "info",
            "raw": _json_preview(item),
        }
    return None


def codex_stderr_trace(text: str) -> dict:
    clean = _trim_log_prefix(text)
    reconnect = re.search(r"Reconnecting\.\.\.\s*(\d+/\d+).*?\((.*)\)", clean, re.I | re.S)
    if reconnect:
        detail = reconnect.group(2).strip()
        return {
            "kind": "error" if "unauthorized" in detail.lower() else "progress",
            "title": f"Codex 正在重试连接 {reconnect.group(1)}",
            "detail": detail,
            "provider": "Codex",
            "action": "retry",
            "level": "error" if "unauthorized" in detail.lower() else "warning",
            "raw": text,
        }
    if "responses_retry" in text and "retrying sampling request" in text:
        return {
            "kind": "progress",
            "title": "Codex 请求中断，准备重试",
            "detail": clean,
            "provider": "Codex",
            "action": "retry",
            "level": "warning",
            "raw": text,
        }
    return error_trace(text) if _looks_like_error(text) else generic_progress_trace(text, provider="Codex")


def opencode_part_trace(part: dict[str, Any]) -> dict | None:
    part_type = str(part.get("type") or "")
    if part_type == "text":
        return None
    if part_type == "tool" or part_type.startswith("tool-"):
        name = str(part.get("tool") or part.get("name") or part_type)
        payload = part.get("input") if "input" in part else part
        action = _normalize_action(name or part_type)
        command = _command_from_payload(name, payload)
        target = _target_from_payload(payload)
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        return {
            "kind": "command" if command else "tool",
            "title": _tool_title("OpenCode", name, action, target),
            "detail": _payload_detail(payload),
            "command": command,
            "target": target,
            "toolName": name,
            "provider": "OpenCode",
            "action": action,
            "level": _command_level(_string_value(state.get("status")), state.get("exitCode")),
            "status": _string_value(state.get("status")) or None,
            "output": _summarize_text(_string_value(state.get("output")), 1200)
            if isinstance(state, dict) else None,
            "raw": _json_preview(part),
        }
    if part_type in {"step-start", "step-finish"}:
        return {
            "kind": "progress",
            "title": "OpenCode 开始执行步骤" if part_type == "step-start" else "OpenCode 完成步骤",
            "detail": _json_preview(part),
            "provider": "OpenCode",
            "action": "step",
            "level": "info",
        }
    return None


def trace_text(trace: dict[str, Any], fallback: str = "") -> str:
    for key in ("title", "detail", "command", "text"):
        value = trace.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback.strip()


def _tool_title(provider: str, name: str, action: str, target: str | None) -> str:
    action_label = {
        "read": "读取",
        "write": "写入",
        "edit": "编辑",
        "run": "执行",
        "search": "搜索",
        "list": "列出",
        "delete": "删除",
        "confirm": "确认",
    }.get(action, "调用")
    title = f"{provider} {action_label} {name}"
    return f"{title}: {target}" if target else title


def _payload_detail(payload: Any) -> str:
    if not isinstance(payload, dict):
        return _json_preview(payload)
    state = payload.get("state")
    if isinstance(state, dict):
        return _tool_state_detail(state) or _json_preview(payload)
    lines = []
    for key in (
        "status", "command", "cmd", "path", "file_path", "filepath", "filePath",
        "pattern", "query", "description", "content", "old_string", "oldString",
        "new_string", "newString", "stdout", "stderr", "output", "aggregated_output",
    ):
        value = payload.get(key)
        if value is None:
            continue
        text = _summarize_text(str(value), 600)
        if text:
            lines.append(f"{key}: {text}")
    return "\n".join(lines) or _json_preview(payload)


def _command_from_payload(name: str, payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("command", "cmd", "shell_command"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    state = payload.get("state")
    if isinstance(state, dict):
        command = _command_from_payload(name, state)
        if command:
            return command
        nested = state.get("input")
        if isinstance(nested, dict):
            command = _command_from_payload(name, nested)
            if command:
                return command
    if _normalize_action(name) == "run":
        value = payload.get("input") or payload.get("args")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _target_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in (
        "path", "file_path", "filepath", "filePath", "file", "cwd", "workdir",
        "directory",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested_input = payload.get("input")
    target = _target_from_payload(nested_input)
    if target:
        return target
    state = payload.get("state")
    if isinstance(state, dict):
        target = _target_from_payload(state)
        if target:
            return target
        nested = state.get("input")
        target = _target_from_payload(nested)
        if target:
            return target
    file_info = payload.get("file")
    target = _target_from_payload(file_info)
    if target:
        return target
    for key in ("files", "paths"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return ", ".join(str(item) for item in value[:3])
    title = payload.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def _codex_command(item: dict[str, Any]) -> str | None:
    for key in ("command", "cmd"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            return _shell_join([str(part) for part in value])
    args = item.get("args")
    if isinstance(args, list) and args:
        return _shell_join([str(part) for part in args])
    return None


def _codex_tool_name(item_type: str, item: dict[str, Any]) -> str | None:
    for key in ("tool", "tool_name", "name", "call_id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if item_type and "tool" in item_type:
        return item_type
    return None


def _codex_item_detail(item: dict[str, Any]) -> str:
    lines = []
    status = _string_value(item.get("status"))
    if status:
        lines.append(f"status: {status}")
    exit_code = item.get("exit_code")
    if isinstance(exit_code, int):
        lines.append(f"exit_code: {exit_code}")
    output = _codex_output(item)
    if output:
        lines.append(f"output:\n{_summarize_text(output, 900)}")
    for key in ("text", "message", "content"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(_summarize_text(value, 900))
            break
    return "\n".join(lines) or _payload_detail(item)


def _codex_output(item: dict[str, Any]) -> str:
    for key in ("aggregated_output", "output", "stdout", "stderr"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _codex_command_title(status: str, exit_code: object) -> str:
    if status == "completed":
        return "Codex 完成命令"
    if status in {"failed", "error"} or (isinstance(exit_code, int) and exit_code != 0):
        return "Codex 命令失败"
    if status in {"in_progress", "running"}:
        return "Codex 正在执行命令"
    return "Codex 执行命令"


def _normalize_action(value: str) -> str:
    lower = value.lower()
    if any(part in lower for part in ("bash", "shell", "exec", "command", "run")):
        return "run"
    if any(part in lower for part in ("write", "create", "save")):
        return "write"
    if any(part in lower for part in ("edit", "patch", "update", "replace")):
        return "edit"
    if any(part in lower for part in ("read", "open", "view", "cat")):
        return "read"
    if any(part in lower for part in ("grep", "search", "find")):
        return "search"
    if any(part in lower for part in ("list", "ls", "glob")):
        return "list"
    if any(part in lower for part in ("delete", "remove", "rm")):
        return "delete"
    return "tool"


def _guess_action(text: str, *, command: str | None = None) -> str:
    if command:
        return "run"
    return _normalize_action(text)


def _extract_command(text: str) -> str | None:
    match = re.search(r"(?:执行命令|command|cmd)\s*[:：]\s*(.+)", text, re.I)
    if match:
        return match.group(1).strip()
    return None


def _first_path(text: str) -> str | None:
    match = re.search(
        r"(?:(?:[A-Za-z]:\\|\.{0,2}[/\\])?[\w .@()~+-]+(?:[/\\][\w .@()~+-]+)+)",
        text,
    )
    if not match:
        return None
    value = match.group(0).strip(" .,:;()[]{}\"'")
    try:
        name = PurePath(value).as_posix()
    except Exception:
        name = value
    return name


def _progress_title(text: str) -> str:
    clean = _trim_log_prefix(text)
    line = _one_line(clean)
    line = re.sub(r"^(?:⏺|⎿|\*|-)\s*", "", line)
    return _summarize_text(line, 120) or "CLI 执行中"


def _error_title(text: str) -> str:
    clean = _trim_log_prefix(text)
    lower = clean.lower()
    if "unauthorized" in lower or "invalid api key" in lower:
        return "认证失败"
    if "not found" in lower:
        return "资源未找到"
    if "timeout" in lower:
        return "执行超时"
    return _summarize_text(_one_line(clean), 120) or "执行错误"


def _trim_log_prefix(text: str) -> str:
    clean = str(text).strip()
    clean = re.sub(r"^\d{4}-\d\d-\d\dT\S+\s+(?:ERROR|WARN|INFO|DEBUG)\s+[\w:.-]+:\s*", "", clean)
    clean = re.sub(r"^\d{4}-\d\d-\d\dT\S+\s+", "", clean)
    return clean.strip()


def _humanize_event(value: str) -> str:
    text = value.replace("_", " ").replace("-", " ").replace(".", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1].upper() + text[1:] if text else "Progress"


def _shell_join(parts: list[str]) -> str:
    if not parts:
        return ""
    rendered = []
    for part in parts:
        if re.search(r"\s|[\"']", part):
            rendered.append(json.dumps(part, ensure_ascii=False))
        else:
            rendered.append(part)
    return " ".join(rendered)


def _json_preview(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _summarize_text(value, 1200)
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)[:1200]
    except TypeError:
        return _summarize_text(str(value), 1200)


def _summarize_text(text: str, limit: int) -> str:
    clean = str(text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "..."


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip())


def _looks_like_error(text: str) -> bool:
    return bool(re.search(r"\b(error|failed|exception|traceback|unauthorized|forbidden|invalid api key)\b", text, re.I))


def _tool_result_content(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, list):
        chunks = []
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_result":
                continue
            value = item.get("content")
            if isinstance(value, str):
                chunks.append(value)
        return "\n".join(chunks).strip()
    return ""


def _tool_result_detail(payload: dict[str, Any], content: str) -> str:
    lines = []
    file_info = payload.get("file")
    if isinstance(file_info, dict):
        target = _target_from_payload(file_info)
        if target:
            lines.append(f"file: {target}")
        file_content = _string_value(file_info.get("content"))
        if file_content:
            lines.append(f"content:\n{_summarize_text(file_content, 900)}")
    for key in ("stdout", "stderr", "content"):
        value = _string_value(payload.get(key))
        if value:
            lines.append(f"{key}:\n{_summarize_text(value, 900)}")
    if content:
        lines.append(f"content:\n{_summarize_text(content, 900)}")
    return "\n".join(lines) or _json_preview(payload)


def _tool_state_detail(state: dict[str, Any]) -> str:
    lines = []
    status = _string_value(state.get("status"))
    if status:
        lines.append(f"status: {status}")
    input_payload = state.get("input")
    target = _target_from_payload(input_payload)
    if target:
        lines.append(f"target: {target}")
    output = _string_value(state.get("output"))
    if output:
        lines.append(f"output:\n{_summarize_text(output, 900)}")
    metadata = state.get("metadata")
    if isinstance(metadata, dict):
        preview = _string_value(metadata.get("preview"))
        if preview:
            lines.append(f"preview: {_summarize_text(preview, 300)}")
    return "\n".join(lines)


def _command_level(status: str, exit_code: object) -> str:
    if isinstance(exit_code, int):
        return "success" if exit_code == 0 else "error"
    if status in {"completed", "success"}:
        return "success"
    if status in {"failed", "error"}:
        return "error"
    return "info"


def _string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
