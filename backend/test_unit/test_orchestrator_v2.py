"""OrchestratorV2 Pipeline 单元测试 —— 覆盖组件独立测试 + Pipeline 集成。

组件: IntentAnalyzer, AgentSelector, TaskDecomposer, ExecutionPlanner, OrchestratorV2
"""
import uuid
import pytest
from app.domain.intent_analyzer import IntentAnalyzer, IntentAnalysis
from app.domain.agent_selector import AgentSelector, ScoredAgent
from app.domain.task_decomposer import TaskDecomposer, SubTask
from app.domain.execution_planner import (
    ExecutionPlanner, AgentCall, ChainConfig, ExecutionPlan,
)
from app.domain.orchestrator_v2 import (
    OrchestratorV2, PipelineRequest, PipelineResult,
)
from app.domain.context_manager import ContextManager
from app.models import AgentConfig


# ===== 测试辅助 =====

def make_agent(name="默认助手", provider="deepseek", agent_id=None,
               description="通用助手", system_prompt="你是一个有帮助的AI助手") -> AgentConfig:
    """创建测试 Agent。使用元数据（name/description/system_prompt）而非 provider 来描述能力。"""
    return AgentConfig(
        id=agent_id or str(uuid.uuid4()),
        name=name,
        description=description,
        provider=provider,
        model="test-model",
        system_prompt=system_prompt,
    )


def make_request(content="hello", mentions=None, agents=None) -> PipelineRequest:
    return PipelineRequest(
        session_id="s1",
        content=content,
        mentions=mentions,
        messages=[{"role": "user", "content": content, "id": "m1"}],
        member_agents=agents if agents is not None else [make_agent()],
    )


# ===== IntentAnalyzer 测试 =====

class TestIntentAnalyzer:
    def test_detect_code_gen(self):
        analyzer = IntentAnalyzer()
        result = analyzer.analyze("帮我写一个React登录组件")
        assert result.intent == "code_gen"
        assert result.confidence == 1.0

    def test_detect_research(self):
        analyzer = IntentAnalyzer()
        result = analyzer.analyze("对比React和Vue的优缺点")
        assert result.intent == "research"

    def test_detect_design_ui(self):
        analyzer = IntentAnalyzer()
        result = analyzer.analyze("帮我设计一个好看的按钮样式")
        assert result.intent == "design_ui"

    def test_fallback_general_qa(self):
        analyzer = IntentAnalyzer()
        result = analyzer.analyze("今天天气怎么样")
        assert result.intent == "general_qa"
        assert result.confidence == 0.3

    def test_empty_content(self):
        analyzer = IntentAnalyzer()
        result = analyzer.analyze("")
        assert result.intent == "general_qa"
        assert result.confidence == 0.0

    def test_extract_tags_code_gen(self):
        analyzer = IntentAnalyzer()
        result = analyzer.analyze("帮我写一个React前端登录页面，需要数据库和后端API")
        tags = result.required_tags
        assert "开发" in tags
        assert "React" in tags
        assert "认证" in tags
        assert "数据库" in tags


# ===== AgentSelector 测试 =====

class TestAgentSelector:
    def test_mention_exact_match_by_id(self):
        """@mention 按 Agent ID 精确匹配。"""
        selector = AgentSelector()
        agents = [
            make_agent(agent_id="a1", name="前端专家"),
            make_agent(agent_id="a2", name="后端架构师"),
        ]
        scored = selector.select(["React"], agents, mentions=["a1"])
        assert len(scored) == 1
        assert scored[0].agent.id == "a1"
        assert scored[0].reason == "exact_mention"

    def test_tag_match_in_description(self):
        """标签在 Agent.description 中命中 → 高得分。"""
        selector = AgentSelector()
        agents = [
            make_agent(name="前端专家", description="擅长React前端开发"),
            make_agent(name="数据分析师", description="擅长数据分析和调研"),
        ]
        scored = selector.select(["React", "前端"], agents)
        assert len(scored) == 2
        assert scored[0].agent.name == "前端专家"
        assert scored[0].reason == "tag_match"

    def test_tag_match_in_system_prompt(self):
        """标签在 system_prompt 中命中。"""
        selector = AgentSelector()
        agents = [
            make_agent(name="后端助手", system_prompt="擅长Python后端API开发"),
            make_agent(name="通用助手", system_prompt="你是一个有帮助的AI助手"),
        ]
        scored = selector.select(["Python", "后端"], agents)
        assert scored[0].agent.name == "后端助手"

    def test_fallback_when_no_match(self):
        """无标签匹配时 fallback，所有 Agent 得分相同。"""
        selector = AgentSelector()
        agents = [
            make_agent(name="A", description="general assistant"),
            make_agent(name="B", description="generic helper"),
        ]
        scored = selector.select(["Rust"], agents)
        assert len(scored) == 2
        assert all(s.reason == "fallback" for s in scored)

    def test_name_match_higher_priority(self):
        """标签命中 Agent.name 得分最高 (权重 3)。"""
        selector = AgentSelector()
        agents = [
            make_agent(name="React开发者", description="", system_prompt=""),
            make_agent(name="助手", description="擅长React开发", system_prompt=""),
        ]
        scored = selector.select(["React"], agents)
        assert scored[0].agent.name == "React开发者"

    def test_empty_candidates(self):
        selector = AgentSelector()
        assert selector.select(["React"], []) == []


# ===== TaskDecomposer 测试 =====

class TestTaskDecomposer:
    def test_complex_detection(self):
        d = TaskDecomposer()
        assert d.is_complex("前后端都要做")
        assert d.is_complex("登录和注册一起实现")
        assert d.is_complex("先设计再实现")

    def test_simple_not_complex(self):
        d = TaskDecomposer()
        assert not d.is_complex("写一个函数")
        assert not d.is_complex("hello")

    def test_chain_detection(self):
        d = TaskDecomposer()
        assert d.is_chain("先分析需求再实现代码")
        assert d.is_chain("从设计到实现都要做")
        assert not d.is_chain("写一个函数")

    def test_code_gen_decompose_with_roles(self):
        """code_gen 拆解为 planning → frontend/backend → review。"""
        d = TaskDecomposer()
        agents = [
            make_agent(name="架构师", system_prompt="擅长架构设计和技术方案"),
            make_agent(name="前端专家", system_prompt="擅长React前端开发"),
            make_agent(name="代码审查员", system_prompt="擅长代码审查和安全测试"),
        ]
        pairs = d.decompose("code_gen", agents)
        assert len(pairs) == 4
        subtasks = [p[0] for p in pairs]
        roles = [s.role for s in subtasks]
        assert roles == ["planner", "executor", "executor", "reviewer"]
        assert subtasks[1].depends_on == ["planning"]
        assert subtasks[2].depends_on == ["planning"]
        assert subtasks[3].depends_on == ["frontend", "backend"]

    def test_research_decompose_with_roles(self):
        """research 拆解为 researcher → synthesizer → critic。"""
        d = TaskDecomposer()
        agents = [
            make_agent(name="研究员", system_prompt="擅长搜索和分析"),
            make_agent(name="总结助手", system_prompt="擅长写作和综合信息"),
            make_agent(name="批判思考者", system_prompt="擅长批判性分析"),
        ]
        pairs = d.decompose("research", agents)
        roles = [p[0].role for p in pairs]
        assert roles == ["researcher", "synthesizer", "critic"]

    def test_less_agents_than_tasks(self):
        """Agent 少于模板数时，只分配可用 Agent。"""
        d = TaskDecomposer()
        agents = [make_agent(name="全栈", system_prompt="全栈开发")]
        pairs = d.decompose("code_gen", agents)
        # 只有 1 个 Agent，降级为 single primary
        assert pairs[0][0].role == "executor"

    def test_empty_templates_returns_primary(self):
        d = TaskDecomposer()
        agents = [make_agent(name="助手")]
        pairs = d.decompose("unknown_intent", agents)
        assert pairs[0][0].name == "primary"

    def test_get_role_prompt(self):
        d = TaskDecomposer()
        prompt = d.get_role_prompt("planner")
        assert "planner" in prompt
        assert "技术方案" in prompt


# ===== ExecutionPlanner 测试 =====

class TestExecutionPlanner:
    def test_single_agent_yields_single_mode(self):
        planner = ExecutionPlanner()
        plan = planner.plan(
            [make_agent(name="助手")], "写一个函数",
            [{"role": "user", "content": "写一个函数"}],
        )
        assert plan.mode == "single"
        assert len(plan.calls) == 1

    def test_complex_request_yields_dag_decompose(self):
        """复杂标记触发 DAG 拆解。"""
        planner = ExecutionPlanner()
        agents = [
            make_agent(name="前端", system_prompt="React前端开发"),
            make_agent(name="后端", system_prompt="Python后端开发"),
        ]
        plan = planner.plan(agents, "前后端都要做登录系统",
                            [{"role": "user", "content": "前后端都要"}])
        assert plan.mode == "dag"
        assert plan.decomposer_used
        assert [p.phase for p in plan.dag_phases] == [0, 1, 2]
        assert plan.dag_phases[1].mode == "parallel"

    def test_chain_keyword_triggers_auto_dag(self):
        """多阶段关键词触发自动 DAG。"""
        planner = ExecutionPlanner()
        agents = [
            make_agent(name="架构师", system_prompt="擅长架构设计"),
            make_agent(name="前端", system_prompt="React前端开发"),
            make_agent(name="审查员", system_prompt="代码审查和测试"),
        ]
        plan = planner.plan(agents, "先设计系统架构再实现代码然后审查",
                            [{"role": "user", "content": "先设计再实现再审查"}])
        assert plan.mode == "dag"
        assert plan.chain_auto_triggered
        assert plan.dag_phases

    def test_explicit_chain_config_priority(self):
        """显式 chain_config 最高优先级。"""
        planner = ExecutionPlanner()
        agents = [
            make_agent(agent_id="a1", name="产出者"),
            make_agent(agent_id="a2", name="审查者"),
        ]
        plan = planner.plan(
            agents, "写代码",
            [{"role": "user", "content": "写代码"}],
            chain_config=ChainConfig(agent_order=["a1", "a2"]),
        )
        assert plan.mode == "chain"
        assert not plan.chain_auto_triggered  # 显式配置，非自动

    def test_empty_agents_returns_empty(self):
        planner = ExecutionPlanner()
        plan = planner.plan([], "hello", [])
        assert plan.mode == "empty"
        assert len(plan.calls) == 0

    def test_multi_agent_no_complex_parallel(self):
        """多 Agent，无复杂标记 → parallel (all primary)。"""
        planner = ExecutionPlanner()
        agents = [
            make_agent(name="A"),
            make_agent(name="B"),
        ]
        plan = planner.plan(agents, "写一个函数", [{"role": "user", "content": "写一个函数"}])
        assert plan.mode == "parallel"
        assert all(c.task == "primary" for c in plan.calls)

    def test_supplemental_does_not_rebuild_dag(self):
        """补充轮次只追加调用，不重新拆完整项目小队。"""
        planner = ExecutionPlanner()
        agents = [
            make_agent(name="前端", system_prompt="React前端开发"),
            make_agent(name="后端", system_prompt="Python后端API数据库"),
            make_agent(name="审查员", system_prompt="代码审查和安全测试"),
        ]
        plan = planner.plan(
            agents,
            "补充后端缺失内容，先设计再实现最后审查",
            [{"role": "user", "content": "补充后端缺失内容"}],
            supplemental=True,
        )
        assert plan.mode == "parallel"
        assert not plan.decomposer_used
        assert plan.dag_phases == []
        assert all(c.task == "primary" for c in plan.calls)

    def test_dag_calls_include_phase_and_dependencies(self):
        """DAG 调用单元携带 phase 和 depends_on，供执行器定向注入。"""
        planner = ExecutionPlanner()
        agents = [
            make_agent(name="架构师", system_prompt="擅长架构设计"),
            make_agent(name="前端", system_prompt="React前端开发"),
            make_agent(name="后端", system_prompt="Python后端API数据库"),
            make_agent(name="审查员", system_prompt="代码审查和安全测试"),
        ]
        plan = planner.plan(
            agents,
            "先设计登录系统再前后端实现最后审查",
            [{"role": "user", "content": "登录系统"}],
        )
        by_task = {c.task: c for c in plan.calls}
        assert by_task["planning"].phase == 0
        assert by_task["frontend"].phase == 1
        assert by_task["backend"].phase == 1
        assert by_task["review"].phase == 2
        assert by_task["review"].depends_on == ["frontend", "backend"]


# ===== OrchestratorV2 Pipeline 集成测试 =====

class TestPipelineIntegration:
    @pytest.mark.asyncio
    async def test_pipeline_run_returns_result(self):
        """Pipeline.run() 完整四阶段流程。"""
        pl = OrchestratorV2()
        req = PipelineRequest(
            session_id="s1",
            content="写一个React组件",
            mentions=None,
            messages=[{"role": "user", "content": "写一个React组件", "id": "m1"}],
            member_agents=[
                make_agent(name="前端专家", description="React前端开发", system_prompt="擅长React和TypeScript"),
            ],
        )
        result = await pl.run(req)
        assert result.execution_mode == "single"
        assert len(result.agent_calls) == 1
        assert result.intent == "code_gen"

    @pytest.mark.asyncio
    async def test_mention_priority_in_pipeline(self):
        """Pipeline 中 @mention 优先于意图匹配。"""
        pl = OrchestratorV2()
        agents = [
            make_agent(agent_id="a1", name="前端", system_prompt="React开发"),
            make_agent(agent_id="a2", name="研究员", system_prompt="擅长调研分析"),
        ]
        req = make_request("帮我分析React和Vue", mentions=["a1"], agents=agents)
        result = await pl.run(req)
        # @mention a1 优先，即使 content 是 research 意图
        assert result.agent_calls[0].agent.id == "a1"

    @pytest.mark.asyncio
    async def test_supplemental_mention_only_calls_named_agent(self):
        """补充轮次若 @ 指定 Agent，只调用被点名 Agent。"""
        pl = OrchestratorV2()
        agents = [
            make_agent(agent_id="frontend", name="前端", system_prompt="React前端开发"),
            make_agent(agent_id="backend", name="后端", system_prompt="Python后端API数据库"),
            make_agent(agent_id="reviewer", name="审查员", system_prompt="代码审查"),
        ]
        req = PipelineRequest(
            session_id="s1",
            content="@后端 补充缺失的后端实现，先设计再实现最后审查",
            mentions=["backend"],
            messages=[{"role": "user", "content": "补充缺失的后端实现", "id": "m1"}],
            member_agents=agents,
            supplemental=True,
        )
        result = await pl.run(req)
        assert result.execution_mode == "single"
        assert [c.agent.id for c in result.agent_calls] == ["backend"]
        assert result.dag_phases == []

    @pytest.mark.asyncio
    async def test_auto_chain_via_pipeline(self):
        """Pipeline 中多阶段关键词自动触发链式。"""
        pl = OrchestratorV2()
        agents = [
            make_agent(name="架构师", system_prompt="擅长架构设计"),
            make_agent(name="开发者", system_prompt="擅长代码开发"),
            make_agent(name="审查员", system_prompt="擅长代码审查"),
        ]
        req = make_request("先设计架构再实现代码然后审查", agents=agents)
        result = await pl.run(req)
        assert result.execution_mode == "chain" or result.chain_auto_triggered

    @pytest.mark.asyncio
    async def test_empty_agents_in_pipeline(self):
        pl = OrchestratorV2()
        req = make_request("hi", agents=[])
        result = await pl.run(req)
        assert len(result.agent_calls) == 0


# ===== ContextManager 集成测试 (保持不变) =====

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
            member_agents=[make_agent()],
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
            member_agents=[make_agent()],
            context_budget=100,
            reserve_tokens=0,
        )
        result = await pl.run(req)
        assert result.truncated
