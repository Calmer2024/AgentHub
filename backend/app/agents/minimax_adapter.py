from typing import AsyncIterator, Callable, Optional
from anthropic import AsyncAnthropic

from .base import BaseAgentAdapter, AgentCapability, AgentResponse
from ..config import settings


class MiniMaxAdapter(BaseAgentAdapter):
    MODELS = ["MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.5-highspeed"]
    DEFAULT_MODEL = "MiniMax-M2.7"

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = AsyncAnthropic(
                api_key=settings.minimax_api_key,
                base_url="https://api.minimaxi.com/anthropic",
            )
        return self._client

    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(
            name="MiniMax M2.7",
            supports_streaming=True,
            max_context_tokens=200_000,
            tags=["code", "writing", "general"],
        )

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> AgentResponse:
        full_content = ""
        transformed = [{"role": m["role"], "content": m["content"]} for m in messages]

        async with self.client.messages.stream(
            model=model or self.DEFAULT_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=transformed,
        ) as stream:
            async for text in stream.text_stream:
                full_content += text
                if on_token:
                    on_token(text)

        return AgentResponse(content=full_content)

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        transformed = [{"role": m["role"], "content": m["content"]} for m in messages]

        async with self.client.messages.stream(
            model=model or self.DEFAULT_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=transformed,
        ) as stream:
            async for text in stream.text_stream:
                yield text
