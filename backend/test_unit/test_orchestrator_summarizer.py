import pytest

from app.models import AgentConfig
from app.domain.execution_planner import AgentCall
from app.services import orchestrator_summarizer as summarizer_module
from app.services.orchestrator_summarizer import OrchestratorSummarizer


class RecordingAdapter:
    def __init__(self):
        self.calls = []

    async def chat_stream(self, messages, system_prompt, model=None, tools=None):
        self.calls.append({
            "messages": messages,
            "system_prompt": system_prompt,
            "model": model,
        })
        yield "central"
        yield " summary"


@pytest.mark.asyncio
async def test_summarizer_uses_independent_orchestrator_model(monkeypatch):
    adapter = RecordingAdapter()
    requested_providers = []

    def get_adapter(provider):
        requested_providers.append(provider)
        return adapter if provider == "openai" else None

    monkeypatch.setattr(summarizer_module.settings, "orchestrator_provider", "openai")
    monkeypatch.setattr(summarizer_module.settings, "orchestrator_model", "gpt-4o-mini")
    monkeypatch.setattr(summarizer_module.agent_registry, "get_adapter", get_adapter)

    agent = AgentConfig(
        id="agent-1",
        name="Worker",
        description="",
        system_prompt="",
        provider="deepseek",
        model="agent-owned-model",
    )
    calls = {
        "agent-1:0:primary": AgentCall(
            agent=agent,
            task="primary",
            role="executor",
        ),
    }

    tokens = [
        token async for token in OrchestratorSummarizer().stream_summary(
            "用户目标", "编排说明", {"agent-1:0:primary": "Agent output"}, calls,
        )
    ]

    assert "".join(tokens) == "central summary"
    assert requested_providers == ["openai"]
    assert adapter.calls[0]["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_summarizer_falls_back_without_agent_model(monkeypatch):
    monkeypatch.setattr(summarizer_module.settings, "orchestrator_provider", "missing")
    monkeypatch.setattr(summarizer_module.settings, "orchestrator_model", "missing-model")
    monkeypatch.setattr(summarizer_module.agent_registry, "get_adapter", lambda provider: None)

    agent = AgentConfig(
        id="agent-1",
        name="Worker",
        description="",
        system_prompt="",
        provider="deepseek",
        model="agent-owned-model",
    )
    calls = {
        "agent-1:0:primary": AgentCall(
            agent=agent,
            task="primary",
            role="executor",
        ),
    }

    tokens = [
        token async for token in OrchestratorSummarizer().stream_summary(
            "用户目标", "编排说明", {"agent-1:0:primary": "Agent output"}, calls,
        )
    ]

    assert "综合总结" in "".join(tokens)
