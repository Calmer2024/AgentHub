"""Orchestrator 单元测试 —— 覆盖意图识别 + Agent 评分 + 任务拆解 + 路由。"""
import pytest
from app.domain.orchestrator import Orchestrator
from app.models import AgentConfig


@pytest.fixture
def orch():
    return Orchestrator()


def make_agent(provider: str, system_prompt: str = "", agent_id: str = None, agent_name: str = None) -> AgentConfig:
    return AgentConfig(
        id=agent_id or provider,
        name=agent_name or provider.title(),
        provider=provider,
        model="test-model",
        system_prompt=system_prompt,
    )


class TestIntentDetection:
    def test_code_gen_intent(self, orch: Orchestrator):
        assert orch.detect_intent("帮我写一个登录页面前端代码") == "code_gen"
        assert orch.detect_intent("修复这个bug") == "code_gen"
        assert orch.detect_intent("实现API接口") == "code_gen"

    def test_research_intent(self, orch: Orchestrator):
        assert orch.detect_intent("调研一下React和Vue的区别") == "research"
        assert orch.detect_intent("分析这个技术选型") == "research"

    def test_design_ui_intent(self, orch: Orchestrator):
        assert orch.detect_intent("帮我设计一个好看的按钮样式") == "design_ui"
        assert orch.detect_intent("改善页面布局") == "design_ui"

    def test_general_qa_fallback(self, orch: Orchestrator):
        assert orch.detect_intent("今天天气怎么样") == "general_qa"
        assert orch.detect_intent("hello") == "general_qa"


class TestAgentScoring:
    def test_code_gen_prefers_claude(self, orch: Orchestrator):
        agents = [
            make_agent("claude"), make_agent("gemini"),
            make_agent("deepseek"), make_agent("minimax"),
        ]
        scored = orch.score_agents("code_gen", agents)
        assert scored[0].provider == "claude"

    def test_research_prefers_gemini(self, orch: Orchestrator):
        agents = [make_agent("claude"), make_agent("gemini"), make_agent("minimax")]
        scored = orch.score_agents("research", agents)
        assert scored[0].provider == "gemini"

    def test_empty_agents(self, orch: Orchestrator):
        assert orch.score_agents("code_gen", []) == []


class TestComplexityDetection:
    def test_detects_complex(self, orch: Orchestrator):
        assert orch.is_complex("帮我做一个登录页面，前后端都要")
        assert orch.is_complex("API和前端一起开发")

    def test_not_complex(self, orch: Orchestrator):
        assert not orch.is_complex("帮我写一个函数")
        assert not orch.is_complex("hello world")


class TestTaskDecomposition:
    def test_code_gen_decompose(self, orch: Orchestrator):
        agents = [make_agent("claude", "frontend React"), make_agent("deepseek", "backend Python")]
        tasks = orch.decompose("code_gen", agents)
        assert len(tasks) == 2
        assert tasks[0][0] == "frontend"
        assert tasks[1][0] == "backend"

    def test_single_agent_no_decompose(self, orch: Orchestrator):
        agents = [make_agent("claude")]
        tasks = orch.decompose("code_gen", agents)
        assert len(tasks) == 1
        assert tasks[0][0] == "primary"


class TestRouting:
    @pytest.mark.asyncio
    async def test_mentions_take_priority(self, orch: Orchestrator):
        agents = [make_agent("claude", agent_id="a1"), make_agent("gemini", agent_id="a2")]
        result = await orch.route(mentions=["a1"], member_agents=agents, content="写代码")
        assert len(result) == 1
        assert result[0].id == "a1"

    @pytest.mark.asyncio
    async def test_no_mentions_returns_scored(self, orch: Orchestrator):
        agents = [make_agent("claude"), make_agent("gemini")]
        result = await orch.route(mentions=None, member_agents=agents, content="写代码")
        assert result[0].provider == "claude"

    @pytest.mark.asyncio
    async def test_route_without_content(self, orch: Orchestrator):
        agents = [make_agent("claude"), make_agent("gemini")]
        result = await orch.route(mentions=None, member_agents=agents)
        assert len(result) == 2


class TestChainCollaboration:
    def test_code_review_chain(self, orch: Orchestrator):
        agents = [
            make_agent("claude", agent_id="c1"),
            make_agent("deepseek", agent_id="d1"),
        ]
        chain = orch.get_chain("code_review", agents)
        assert len(chain) == 2
        assert chain[0].provider == "claude"
        assert chain[1].provider == "deepseek"

    def test_unknown_chain_returns_empty(self, orch: Orchestrator):
        agents = [make_agent("claude")]
        chain = orch.get_chain("unknown", agents)
        assert len(chain) == 0
