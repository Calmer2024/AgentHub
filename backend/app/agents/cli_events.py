"""CLI Adapter 的标准事件模型。"""

from dataclasses import dataclass
from typing import Any


@dataclass
class CliEvent:
    type: str
    process_id: str
    chunk: str = ""
    chunk_type: str = "text"
    exit_code: int | None = None
    error: str | None = None
    prompt_type: str = "confirm"
    trace: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class ParsedOutput:
    text: str
    chunk_type: str = "text"
    trace: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
