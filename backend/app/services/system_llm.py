"""System-only LLM facade.

User-visible Agent execution is CLI-only. This service keeps DeepSeek as a
background capability for orchestration summaries, title generation, and small
editing assists without becoming a user-visible chat Agent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ..config import settings
from ..system_models import (
    DeepSeekSystemAdapter,
    SystemModelCapability,
    SystemModelResponse,
)


class SystemLLMUnavailableError(RuntimeError):
    """Raised when the system DeepSeek key is not configured or unusable."""


class SystemLLMService:
    """DeepSeek-backed system model for internal backend capabilities."""

    def __init__(self, adapter: DeepSeekSystemAdapter | None = None):
        self._adapter = adapter or DeepSeekSystemAdapter()

    @property
    def model(self) -> str:
        return settings.deepseek_model or self._adapter.DEFAULT_MODEL

    @property
    def capability(self) -> SystemModelCapability:
        return self._adapter.capability

    def is_configured(self) -> bool:
        return bool(settings.deepseek_api_key.strip())

    async def chat(
        self,
        *,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict] | None = None,
    ) -> SystemModelResponse:
        self._ensure_configured()
        return await self._adapter.chat(
            messages=messages,
            system_prompt=system_prompt,
            model=self.model,
            tools=tools,
        )

    async def chat_stream(
        self,
        *,
        messages: list[dict],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        self._ensure_configured()
        async for token in self._adapter.chat_stream(
            messages=messages,
            system_prompt=system_prompt,
            model=self.model,
        ):
            yield token

    def _ensure_configured(self) -> None:
        if not self.is_configured():
            raise SystemLLMUnavailableError("DeepSeek API Key 未配置")


system_llm = SystemLLMService()


def system_model_status() -> dict[str, Any]:
    """Small API-friendly health snapshot without exposing raw secrets."""
    configured = bool(settings.deepseek_api_key.strip())
    return {
        "systemModelProvider": "deepseek",
        "systemModel": settings.deepseek_model or DeepSeekSystemAdapter.DEFAULT_MODEL,
        "isConfigured": configured,
        "capability": {
            "supportsStreaming": True,
            "supportsToolCall": True,
            "maxContextTokens": 128_000,
        },
    }
