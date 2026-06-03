from typing import AsyncIterator, Callable, Optional
from google import genai

from .base import BaseAgentAdapter, AgentCapability, AgentResponse
from ..config import settings


class GeminiAdapter(BaseAgentAdapter):
    MODELS = ["gemini-3.5-flash", "gemini-3.1-pro-preview"]
    DEFAULT_MODEL = "gemini-3.5-flash"

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(
            name="Gemini 3.5 Flash",
            supports_streaming=True,
            supports_tool_call=False,
            max_context_tokens=1_000_000,
            tags=["code", "writing", "general", "multimodal"],
        )

    def _merge_tokens_to_messages(
        self, messages: list[dict], system_prompt: str
    ) -> list[dict]:
        converted = []
        if system_prompt:
            converted.append({"role": "user", "parts": [{"text": f"System: {system_prompt}"}]})
            converted.append({"role": "model", "parts": [{"text": "Understood."}]})
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            converted.append({"role": role, "parts": [{"text": m["content"]}]})
        return converted

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> AgentResponse:
        converted = self._merge_tokens_to_messages(messages, system_prompt)
        full_content = ""

        stream = await self.client.aio.models.generate_content_stream(
            model=model or self.DEFAULT_MODEL,
            contents=converted,
        )
        async for response in stream:
            if response.text:
                full_content += response.text
                if on_token:
                    on_token(response.text)

        return AgentResponse(content=full_content)

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        converted = self._merge_tokens_to_messages(messages, system_prompt)

        stream = await self.client.aio.models.generate_content_stream(
            model=model or self.DEFAULT_MODEL,
            contents=converted,
        )
        async for response in stream:
            if response.text:
                yield response.text
