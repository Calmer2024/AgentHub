import asyncio
from typing import AsyncIterator, Callable, Optional
from zhipuai import ZhipuAI

from .base import BaseAgentAdapter, AgentCapability, AgentResponse
from ..config import settings


class GLMAdapter(BaseAgentAdapter):
    MODELS = ["glm-5.1", "glm-5v-turbo", "glm-5", "glm-4.7"]
    DEFAULT_MODEL = "glm-5.1"

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = ZhipuAI(api_key=settings.glm_api_key)
        return self._client

    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(
            name="GLM-5.1",
            supports_streaming=True,
            max_context_tokens=128_000,
            tags=["code", "writing", "general"],
        )

    def _build_messages(self, messages: list[dict], system_prompt: str) -> list[dict]:
        return [{"role": "system", "content": system_prompt}] + [
            {"role": m["role"], "content": m["content"]} for m in messages
        ]

    def _sync_stream(self, model: str, messages: list[dict]):
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=4096,
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
        built = self._build_messages(messages, system_prompt)
        response = await asyncio.to_thread(self._sync_stream, model or self.DEFAULT_MODEL, built)

        for chunk in response:
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
        built = self._build_messages(messages, system_prompt)
        response = await asyncio.to_thread(self._sync_stream, model or self.DEFAULT_MODEL, built)

        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
