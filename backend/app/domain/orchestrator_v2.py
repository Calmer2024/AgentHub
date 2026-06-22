"""Orchestrator V2 —— Pipeline 模式智能路由 (thin coordinator)。

Domain 层纯逻辑，零 FastAPI/SQLAlchemy 依赖。

Pipeline 四阶段:
  1. ContextAssembly  — ContextManager token 预算 + Pin 优先级
  2. AgentSelection    — @mention 精确 → 意图识别 → Agent 元数据标签匹配
  3. ExecutionPlanning — 判定执行模式 + 优先级链决策 + 自动链式触发
  4. Lifecycle         — 通过 EventBus 发布任务开始/结束事件

组件:
  - IntentAnalyzer: 意图类型 + 能力标签提取
  - AgentSelector: 基于 Agent.description + system_prompt 标签匹配
  - TaskDecomposer: 复杂请求拆解 + 6 种角色模板
  - ExecutionPlanner: 模式决策 + 自动链式触发
"""

import logging
from dataclasses import dataclass, field

from .agent_profile import AgentProfileSnapshot
from .events import (
    ORCHESTRATOR_TASK_COMPLETED,
    ORCHESTRATOR_TASK_STARTED,
    DomainEventPublisher,
)
from .intent_analyzer import IntentAnalyzer
from .agent_selector import AgentSelector
from .task_decomposer import TaskDecomposer
from .execution_planner import ExecutionPlanner, AgentCall, ChainConfig, DAGPhase
from .plan_summary import build_plan_summary

logger = logging.getLogger(__name__)


# ===== Pipeline 数据类型 =====

@dataclass
class PipelineRequest:
    """Pipeline 输入。"""
    session_id: str
    content: str
    mentions: list[str] | None
    messages: list[dict]
    member_agents: list[AgentProfileSnapshot]
    system_prompt: str = ""
    pinned_message_ids: list[str] = field(default_factory=list)
    context_budget: int = 100_000
    reserve_tokens: int = 4096
    chain_config: ChainConfig | None = None  # Phase 3: 链式配置 (运行时)
    supplemental: bool = False  # 追问补充: 只调用被点名/缺失 Agent，不重跑完整小队


@dataclass
class PipelineResult:
    """Pipeline 输出。"""
    agent_calls: list[AgentCall]
    execution_mode: str  # "single" | "parallel" | "chain" | "dag" | "empty"
    assembled_messages: list[dict]
    total_tokens: int
    truncated: bool
    intent: str = "general_qa"
    chain_auto_triggered: bool = False
    decomposer_used: bool = False
    dag_phases: list[DAGPhase] = field(default_factory=list)
    plan_summary: str = ""


# ===== Pipeline (thin coordinator) =====

class OrchestratorV2:
    """Pipeline 模式智能编排器 (thin coordinator)。

    负责组装 4 个组件并协调执行流程。
    所有编排逻辑委托给独立组件，自身只做流程串联。

    用法:
        pipeline = OrchestratorV2(context_manager, event_bus)
        result = await pipeline.run(PipelineRequest(...))
    """

    def __init__(self, context_manager=None, event_bus: DomainEventPublisher | None = None):
        self._ctx = context_manager
        self._events = event_bus

        # 组装 4 个组件
        self.intent_analyzer = IntentAnalyzer()
        self.agent_selector = AgentSelector()
        self.task_decomposer = TaskDecomposer()
        self.execution_planner = ExecutionPlanner(self.task_decomposer)

    # ---- Public API ----

    async def run(self, req: PipelineRequest) -> PipelineResult:
        """执行 Pipeline 四阶段，返回执行计划。"""
        # Stage 1: 意图分析
        intent_analysis = self.intent_analyzer.analyze(req.content)

        # Stage 2: Context Assembly
        assembled, truncated = self._assemble_context(req)

        # Stage 3: Agent Selection
        agents = self._select_agents(req, intent_analysis.required_tags)

        # Stage 4: Execution Planning
        plan = self.execution_planner.plan(
            agents=agents,
            content=req.content,
            messages=assembled,
            chain_config=req.chain_config,
            supplemental=req.supplemental,
        )

        # Stage 5 (原 Stage 4): Lifecycle events
        await self._emit_task_started(req.session_id, intent_analysis.intent, plan.calls)

        return PipelineResult(
            agent_calls=plan.calls,
            execution_mode=plan.mode,
            assembled_messages=assembled,
            total_tokens=sum(len(m.get("content", "")) for m in assembled) // 3,
            truncated=truncated,
            intent=intent_analysis.intent,
            chain_auto_triggered=plan.chain_auto_triggered,
            decomposer_used=plan.decomposer_used,
            dag_phases=plan.dag_phases,
            plan_summary=build_plan_summary(plan.mode, plan.calls, plan.dag_phases),
        )

    # ---- Stage: Context Assembly ----

    def _assemble_context(self, req: PipelineRequest) -> tuple[list[dict], bool]:
        """Stage: ContextManager token 预算 + 截断。"""
        if not self._ctx:
            msgs = list(req.messages)
            if req.system_prompt:
                msgs.insert(0, {"role": "system", "content": req.system_prompt})
            return msgs, False

        from .context_manager import PromptAssemblyInput
        result = self._ctx.assemble(PromptAssemblyInput(
            session_id=req.session_id,
            system_prompt=req.system_prompt,
            messages=req.messages,
            pinned_message_ids=req.pinned_message_ids,
            max_tokens=req.context_budget,
            reserve_tokens=req.reserve_tokens,
        ))
        return result.assembled_messages, result.truncated

    # ---- Stage: Agent Selection ----

    def _select_agents(
        self,
        req: PipelineRequest,
        required_tags: list[str],
    ) -> list[AgentProfileSnapshot]:
        """Stage: @mention 精确匹配 → 标签匹配 → fallback。"""
        candidates = req.member_agents if req.mentions else [
            agent for agent in req.member_agents
            if (agent.primary_skill or "") != "orchestrator_planner"
        ]
        scored = self.agent_selector.select(
            required_tags=required_tags,
            candidates=candidates,
            mentions=req.mentions,
        )
        if req.supplemental and not req.mentions:
            matched = [s for s in scored if s.reason == "tag_match"]
            return [s.agent for s in matched[:2]]
        return [s.agent for s in scored]

    # ---- Lifecycle Events ----

    async def _emit_task_started(self, session_id: str, intent: str,
                                  calls: list[AgentCall]) -> None:
        """通过 EventBus 发布任务开始事件。"""
        if not self._events:
            return
        try:
            await self._events.publish(ORCHESTRATOR_TASK_STARTED, {
                "session_id": session_id,
                "intent": intent,
                "tasks": [
                    {"name": c.task, "role": c.role, "agent": c.agent.name,
                     "phase": c.phase, "depends_on": list(c.depends_on)}
                    for c in calls
                ],
                "agents": [c.agent.name for c in calls],
            })
        except Exception:
            logger.exception("EventBus publish failed")

    async def emit_completed(self, session_id: str, summary: str = "") -> None:
        """发布任务完成事件。"""
        if not self._events:
            return
        try:
            await self._events.publish(ORCHESTRATOR_TASK_COMPLETED, {
                "session_id": session_id,
                "summary": summary,
            })
        except Exception:
            logger.exception("EventBus publish failed")
