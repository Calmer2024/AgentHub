"""OrchestratorV2 Pipeline 单元测试 —— 覆盖 4 阶段 + 执行模式 + ContextManager 集成。"""
import uuid
import pytest
from app.domain.orchestrator_v2 import (
    OrchestratorV2, PipelineRequest, AgentCall, PipelineResult,
)
from app.domain.context_manager import ContextManager
from app.models import AgentConfig


def make_agent(provider="claude", agent_id=None, name=None, system_prompt="") -> AgentConfig:
    return AgentConfig(
        id=agent_id or provider,
        name=name or provider.title(),
        provider=provider,
        model="test",
        system_prompt=system_prompt,
    )


def make_request(content="hello", mentions=None, agents=None) -> PipelineRequest:
    return PipelineRequest(
        session_id="s1",
        content=content,
        mentions=mentions,
        messages=[{"role": "user", "content": content, "id": "m1"}],
        member_agents=agents if agents is not None else [make_agent("claude")],
    )


@pytest.fixture
def pipeline():
    return OrchestratorV2()


# ===== Stage 1: Context Assembly =====

class TestContextAssembly:
    @pytest.mark.asyncio
    async def test_no_context_manager_passthrough(self):
        pl = OrchestratorV2()
        req = make_request("hello")
        result = await pl.run(req)
        assert len(result.assembled_messages) > 0
        assert not result.truncated

    @pytest.mark.asyncio
    async def test_with_context_manager(self):
        cm = ContextManager()
        pl = OrchestratorV2(context_manager=cm)
        req = PipelineRequest(
            session_id="s1", content="hi", mentions=None,
            messages=[{"role": "user", "content": "hello", "id": "m1"}],
            member_agents=[make_agent("claude")],
            system_prompt="你是助手",
            context_budget=1000,
        )
        result = await pl.run(req)
        assert result.assembled_messages[0]["role"] == "system"
        assert result.assembled_messages[0]["content"] == "你是助手"

    @pytest.mark.asyncio
    async def test_truncation_detected_with_tight_budget(self):
        cm = ContextManager()
        pl = OrchestratorV2(context_manager=cm)
        req = PipelineRequest(
            session_id="s1", content="hi", mentions=None,
            messages=[{"role": "user", "content": "x" * 5000, "id": "m1"}],
            member_agents=[make_agent("claude")],
            context_budget=100,
            reserve_tokens=0,
        )
        result = await pl.run(req)
        assert result.truncated


# ===== Stage 2: Agent Selection =====

class TestAgentSelection:
    @pytest.mark.asyncio
    async def test_mentions_exact_match(self, pipeline):
        agents = [make_agent("claude", agent_id="c1"), make_agent("gemini", agent_id="g1")]
        req = make_request("写代码", mentions=["c1"], agents=agents)
        result = await pipeline.run(req)
        assert len(result.agent_calls) == 1
        assert result.agent_calls[0].agent.id == "c1"

    @pytest.mark.asyncio
    async def test_intent_based_scoring(self, pipeline):
        agents = [make_agent("gemini"), make_agent("claude"), make_agent("minimax")]
        req = make_request("帮我写一个函数", agents=agents)
        result = await pipeline.run(req)
        assert result.intent == "code_gen"
        assert result.agent_calls[0].agent.provider == "claude"

    @pytest.mark.asyncio
    async def test_research_prefers_gemini(self, pipeline):
        agents = [make_agent("claude"), make_agent("gemini"), make_agent("minimax")]
        req = make_request("对比React和Vue的优缺点", agents=agents)
        result = await pipeline.run(req)
        assert result.intent == "research"
        assert result.agent_calls[0].agent.provider == "gemini"

    @pytest.mark.asyncio
    async def test_empty_agents_returns_empty_calls(self, pipeline):
        req = make_request("hi", agents=[])
        result = await pipeline.run(req)
        assert len(result.agent_calls) == 0


# ===== Stage 3: Execution Planning =====

class TestExecutionPlanning:
    @pytest.mark.asyncio
    async def test_single_agent_yields_single_mode(self, pipeline):
        req = make_request("hi", agents=[make_agent("claude")])
        result = await pipeline.run(req)
        assert result.execution_mode == "single"
        assert len(result.agent_calls) == 1

    @pytest.mark.asyncio
    async def test_complex_request_decomposes(self, pipeline):
        agents = [
            make_agent("claude", system_prompt="React frontend developer"),
            make_agent("deepseek", system_prompt="Python backend developer"),
        ]
        req = make_request("做登录页面，前后端都要", agents=agents)
        result = await pipeline.run(req)
        assert result.execution_mode == "parallel"
        assert len(result.agent_calls) == 2
        tasks = {c.task for c in result.agent_calls}
        assert "frontend" in tasks
        assert "backend" in tasks

    @pytest.mark.asyncio
    async def test_simple_request_no_decompose(self, pipeline):
        agents = [make_agent("claude"), make_agent("deepseek")]
        req = make_request("帮我写一个函数", agents=agents)
        result = await pipeline.run(req)
        assert result.execution_mode == "parallel"
        assert all(c.task == "primary" for c in result.agent_calls)


# ===== Static Methods =====

class TestIntentDetection:
    def test_code_gen(self):
        assert OrchestratorV2.detect_intent("帮我写代码") == "code_gen"
        assert OrchestratorV2.detect_intent("修复一个bug") == "code_gen"

    def test_research(self):
        assert OrchestratorV2.detect_intent("分析React和Vue的优缺点") == "research"

    def test_design_ui(self):
        assert OrchestratorV2.detect_intent("帮我设计一个好看的按钮") == "design_ui"

    def test_fallback(self):
        assert OrchestratorV2.detect_intent("今天天气怎么样") == "general_qa"


class TestComplexityDetection:
    def test_complex(self):
        assert OrchestratorV2.is_complex("前后端都要做")
        assert OrchestratorV2.is_complex("登录和注册一起实现")

    def test_simple(self):
        assert not OrchestratorV2.is_complex("写一个函数")
        assert not OrchestratorV2.is_complex("hello")


class TestDecompose:
    def test_code_gen_decompose(self):
        agents = [
            make_agent("claude", system_prompt="React frontend"),
            make_agent("deepseek", system_prompt="Python backend API"),
        ]
        tasks = OrchestratorV2.decompose("code_gen", agents)
        assert len(tasks) == 2

    def test_no_template_returns_primary(self):
        agents = [make_agent("claude")]
        tasks = OrchestratorV2.decompose("unknown_intent", agents)
        assert tasks == [("primary", agents[0])]


class TestChainTemplate:
    def test_code_review_chain(self):
        agents = [make_agent("claude"), make_agent("deepseek")]
        chain = OrchestratorV2.get_chain("code_review", agents)
        assert chain[0].provider == "claude"
        assert chain[1].provider == "deepseek"

    def test_unknown_chain(self):
        assert OrchestratorV2.get_chain("nonexistent", [make_agent("claude")]) == []
