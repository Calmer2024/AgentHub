from collections.abc import AsyncIterator, Callable

from openai import AsyncOpenAI

from ..config import settings
from .types import SystemModelCapability, SystemModelResponse


class DeepSeekSystemAdapter:
    """DeepSeek adapter for internal system capabilities only."""

    MODELS = ["deepseek-v4-flash", "deepseek-v4-pro"]
    DEFAULT_MODEL = "deepseek-v4-flash"

    def __init__(self):
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url="https://api.deepseek.com",
            )
        return self._client

    @property
    def capability(self) -> SystemModelCapability:
        return SystemModelCapability(
            name="DeepSeek System Model",
            supports_streaming=True,
            supports_tool_call=True,
            max_context_tokens=128_000,
            tags=["code", "writing", "general"],
        )

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_token: Callable[[str], None] | None = None,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> SystemModelResponse:
        full_content = ""
        transformed_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        transformed_messages.insert(0, {"role": "system", "content": system_prompt})

        if tools:
            response = await self.client.chat.completions.create(
                model=model or self.DEFAULT_MODEL,
                messages=transformed_messages,
                tools=[{"type": "function", "function": tool} for tool in tools],
                tool_choice="auto",
                max_tokens=4096,
            )
            message = response.choices[0].message
            tool_calls = [
                {
                    "id": call.id,
                    "type": call.type,
                    "name": call.function.name,
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in message.tool_calls or []
            ]
            return SystemModelResponse(
                content=message.content or "",
                tool_calls=tool_calls,
                finish_reason=response.choices[0].finish_reason or "stop",
            )

        stream = await self.client.chat.completions.create(
            model=model or self.DEFAULT_MODEL,
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

        return SystemModelResponse(content=full_content)

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        transformed_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        transformed_messages.insert(0, {"role": "system", "content": system_prompt})

        stream = await self.client.chat.completions.create(
            model=model or self.DEFAULT_MODEL,
            messages=transformed_messages,
            stream=True,
            max_tokens=4096,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
