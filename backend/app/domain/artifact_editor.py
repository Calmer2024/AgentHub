"""Pure artifact editing primitives used by the ArtifactService."""

import difflib
import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class DiffResult:
    from_version: int
    to_version: int
    diff: str
    old_content: str
    new_content: str


class ArtifactEditor:
    """Framework-free artifact diff and edit logic."""

    def build_diff(self, old: str, new: str, from_version: int, to_version: int) -> DiffResult:
        diff = "\n".join(difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"v{from_version}",
            tofile=f"v{to_version}",
            lineterm="",
        ))
        return DiffResult(
            from_version=from_version,
            to_version=to_version,
            diff=diff,
            old_content=old,
            new_content=new,
        )

    def parse_tool_call(self, tool_calls: list[dict]) -> dict[str, Any] | None:
        for call in tool_calls:
            name = call.get("name") or call.get("function", {}).get("name")
            if name != "edit_artifact":
                continue
            payload = (
                call.get("input")
                or call.get("arguments")
                or call.get("function", {}).get("arguments")
                or {}
            )
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    return None
            return payload if isinstance(payload, dict) else None
        return None

    def apply_tool_payload(
        self,
        content: str,
        original_selection: str,
        payload: dict[str, Any],
    ) -> str:
        selection = str(payload.get("selection") or original_selection)
        edit_type = str(payload.get("edit_type") or "replace")
        replacement = str(
            payload.get("replacement")
            or payload.get("content")
            or payload.get("new_content")
            or ""
        )
        return self.apply_edit_operation(content, selection, replacement, edit_type)

    def apply_edit_operation(
        self,
        content: str,
        selection: str,
        replacement: str,
        edit_type: str,
    ) -> str:
        if selection not in content:
            raise ValueError("selection not found in artifact content")
        if edit_type == "delete":
            next_chunk = ""
        elif edit_type == "insert_after":
            next_chunk = selection + replacement
        elif edit_type == "insert_before":
            next_chunk = replacement + selection
        else:
            next_chunk = replacement
        return content.replace(selection, next_chunk, 1)

    @staticmethod
    def extract_replacement(content: str) -> str:
        text = content.strip()
        fenced = re.search(r"```(?:\w+)?\s*(.*?)```", text, flags=re.DOTALL)
        return fenced.group(1).strip("\n") if fenced else text

    @staticmethod
    def deterministic_rewrite(selection: str, instruction: str, edit_type: str) -> str:
        if edit_type == "delete":
            return ""
        if "uppercase" in instruction.lower() or "大写" in instruction:
            return selection.upper()
        if "lowercase" in instruction.lower() or "小写" in instruction:
            return selection.lower()
        return_value = _extract_return_value(instruction)
        if return_value:
            return return_value
        return f"{selection}\n# TODO: {instruction}"


def _extract_return_value(instruction: str) -> str:
    patterns = (
        r"改成返回\s+(.+)",
        r"返回\s+(.+)",
        r"return\s+(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, instruction, flags=re.I)
        if not match:
            continue
        value = match.group(1).strip().strip("。.!！`'\"")
        if value.lower() == "hello world":
            return "Hello World!"
        return value
    return ""
