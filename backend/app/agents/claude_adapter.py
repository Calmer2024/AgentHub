from typing import AsyncIterator, Callable, Optional

from anthropic import AsyncAnthropic

from .base import BaseAgentAdapter, AgentCapability, AgentResponse
from ..config import settings


class ClaudeAdapter(BaseAgentAdapter):
    MODELS = ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"]
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(
            name="Claude 3.5 Sonnet",
            supports_streaming=True,
            supports_tool_call=True,
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
