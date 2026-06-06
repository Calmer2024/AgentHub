from dataclasses import dataclass, field
from typing import Any


@dataclass
class SystemModelCapability:
    name: str
    supports_streaming: bool = True
    supports_tool_call: bool = False
    max_context_tokens: int = 100_000
    tags: list[str] = field(default_factory=list)


@dataclass
class SystemModelResponse:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, Any] | None = None
