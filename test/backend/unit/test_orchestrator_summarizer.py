import pytest

from app.models import AgentConfig
from app.domain.execution_planner import AgentCall
from app.services import orchestrator_summarizer as summarizer_module
from app.services.orchestrator_summarizer import OrchestratorSummarizer


class RecordingSystemLLM:
    def __init__(self):
        self.calls = []
        self.model = "deepseek-v4-flash"

    async def chat_stream(self, *, messages, system_prompt):
        self.calls.append({
            "messages": messages,
            "system_prompt": system_prompt,
        })
        yield "central"
        yield " summary"


@pytest.mark.asyncio
async def test_summarizer_uses_system_llm_not_agent_model(monkeypatch):
    system_llm = RecordingSystemLLM()
    monkeypatch.setattr(summarizer_module, "system_llm", system_llm)
    agent = AgentConfig(
        id="agent-1",
        name="Worker",
        description="",
        system_prompt="",
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
    assert system_llm.calls[0]["messages"][0]["content"].count("Agent output") == 1


def test_summarizer_metadata_uses_system_model_names():
    config = OrchestratorSummarizer().current_model_config()
    assert config == {
        "system_model_provider": "deepseek",
        "system_model": "deepseek-v4-flash",
    }


@pytest.mark.asyncio
async def test_summarizer_falls_back_when_system_llm_unavailable(monkeypatch):
    class MissingSystemLLM:
        async def chat_stream(self, *, messages, system_prompt):
            raise summarizer_module.SystemLLMUnavailableError("missing")

    monkeypatch.setattr(summarizer_module, "system_llm", MissingSystemLLM())

    agent = AgentConfig(
        id="agent-1",
        name="Worker",
        description="",
        system_prompt="",
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
