from ..agents import (
    ClaudeAdapter, DeepSeekAdapter, GeminiAdapter, OpenAIAdapter,
    MiniMaxAdapter, GLMAdapter, BaseAgentAdapter,
)
from ..config import settings


class AgentRegistry:
    def __init__(self):
        self._adapters: dict[str, BaseAgentAdapter] = {
            "openai": OpenAIAdapter(),
            "claude": ClaudeAdapter(),
            "deepseek": DeepSeekAdapter(),
            "gemini": GeminiAdapter(),
            "minimax": MiniMaxAdapter(),
            "glm": GLMAdapter(),
        }

    def get_agent_names(self) -> list[str]:
        return list(self._adapters.keys())

    def get_adapter(self, name: str) -> BaseAgentAdapter | None:
        return self._adapters.get(name)

    def get_models(self, name: str) -> list[str]:
        adapter = self._adapters.get(name)
        return getattr(adapter, "MODELS", []) if adapter else []

    def get_default_model(self, name: str) -> str:
        adapter = self._adapters.get(name)
        return getattr(adapter, "DEFAULT_MODEL", "") if adapter else ""

    def is_available(self, name: str) -> bool:
        key = {
            "openai": settings.openai_api_key,
            "claude": settings.anthropic_api_key,
            "deepseek": settings.deepseek_api_key,
            "gemini": settings.gemini_api_key,
            "minimax": settings.minimax_api_key,
            "glm": settings.glm_api_key,
        }.get(name, "")

        if not key:
            return False

        format_rules = {
            "openai": key.startswith("sk-"),
            "claude": key.startswith("sk-ant-"),
            "deepseek": key.startswith("sk-"),
            "gemini": key.startswith("AIza") or len(key) >= 20,
            "minimax": len(key) >= 20,
            "glm": len(key) >= 20,
        }
        return format_rules.get(name, False)

    def get_agents_info(self) -> list[dict]:
        result = []
        for name, adapter in self._adapters.items():
            cap = adapter.capability
            available = self.is_available(name)
            info = {
                "name": name,
                "display_name": cap.name,
                "provider": self.get_provider(name),
                "is_available": available,
                "models": self.get_models(name),
                "default_model": self.get_default_model(name),
                "capability": {
                    "supports_streaming": cap.supports_streaming,
                    "supports_file_input": cap.supports_file_input,
                    "supports_tool_call": cap.supports_tool_call,
                    "max_context_tokens": cap.max_context_tokens,
                    "tags": cap.tags,
                },
            }
            if not available:
                info["unavailable_reason"] = self._unavailable_reason(name)
            result.append(info)
        return result

    def _unavailable_reason(self, name: str) -> str:
        key = {
            "openai": settings.openai_api_key,
            "claude": settings.anthropic_api_key,
            "deepseek": settings.deepseek_api_key,
            "gemini": settings.gemini_api_key,
            "minimax": settings.minimax_api_key,
            "glm": settings.glm_api_key,
        }.get(name, "")
        if not key:
            return "API Key 未配置"
        return "API Key 格式无效"

    @staticmethod
    def get_provider(name: str) -> str:
        return {
            "openai": "openai",
            "claude": "anthropic",
            "deepseek": "deepseek",
            "gemini": "google",
            "minimax": "minimax",
            "glm": "zhipu",
        }.get(name, "unknown")


agent_registry = AgentRegistry()
