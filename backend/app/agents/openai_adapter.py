from typing import AsyncIterator, Callable, Optional
from openai import AsyncOpenAI

from .base import BaseAgentAdapter, AgentCapability, AgentResponse
from ..config import settings


class OpenAIAdapter(BaseAgentAdapter):
    MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
    DEFAULT_MODEL = "gpt-4o"

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(
            name="GPT-4o",
            supports_streaming=True,
            supports_file_input=True,
            supports_tool_call=True,
            max_context_tokens=128_000,
            tags=["code", "writing", "general", "multimodal"],
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
        transformed.insert(0, {"role": "system", "content": system_prompt})

        stream = await self.client.chat.completions.create(
            model=model or self.DEFAULT_MODEL,
            messages=transformed,
            stream=True,
            max_tokens=4096,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_content += token
                if on_token:
                    on_token(token)

        return AgentResponse(content=full_content)

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        transformed = [{"role": m["role"], "content": m["content"]} for m in messages]
        transformed.insert(0, {"role": "system", "content": system_prompt})

        stream = await self.client.chat.completions.create(
            model=model or self.DEFAULT_MODEL,
            messages=transformed,
            stream=True,
            max_tokens=4096,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
