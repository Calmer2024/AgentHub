from typing import AsyncIterator, Callable, Optional
from openai import AsyncOpenAI

from .base import BaseAgentAdapter, AgentCapability, AgentResponse
from ..config import settings


class GeminiAdapter(BaseAgentAdapter):
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
        return self._client

    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(
            name="Gemini 2.0 Flash",
            supports_streaming=True,
            max_context_tokens=1_000_000,
            tags=["code", "writing", "general", "multimodal"],
        )

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> AgentResponse:
        full_content = ""
        transformed_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        transformed_messages.insert(0, {"role": "system", "content": system_prompt})

        stream = await self.client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=transformed_messages,
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
    ) -> AsyncIterator[str]:
        transformed_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        transformed_messages.insert(0, {"role": "system", "content": system_prompt})

        stream = await self.client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=transformed_messages,
            stream=True,
            max_tokens=4096,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
