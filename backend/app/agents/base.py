from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Optional, List, Any


@dataclass
class AgentCapability:
    name: str
    supports_streaming: bool = True
    supports_file_input: bool = False
    supports_tool_call: bool = False
    max_context_tokens: int = 100_000
    tags: List[str] = field(default_factory=list)


@dataclass
class AgentResponse:
    content: str
    tool_calls: List[dict] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Optional[dict] = None


class BaseAgentAdapter(ABC):
    @property
    @abstractmethod
    def capability(self) -> AgentCapability:
        ...

    @abstractmethod
    async def chat(
        self,
        messages: List[dict],
        system_prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> AgentResponse:
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[dict],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        ...
