"""Orchestrator V2 —— Pipeline 模式智能路由。

Domain 层纯逻辑，零 FastAPI/SQLAlchemy 依赖。

Pipeline 四阶段:
  1. ContextAssembly  — ContextManager token 预算 + Pin 优先级
  2. AgentSelection    — @mention 精确 → 意图识别 → 评分排序
  3. ExecutionPlanning — 判定执行模式 + 构建 AgentCall 列表
  4. Lifecycle         — 通过 EventBus 发布任务开始/结束事件
"""

import logging
from dataclasses import dataclass, field

from ..models import AgentConfig
from ..event_bus import EventType

logger = logging.getLogger(__name__)


# ===== 意图规则表 =====

INTENT_KEYWORDS: dict[str, list[str]] = {
    "code_gen": ["写代码", "实现", "开发", "修复bug", "重构", "API", "前端", "后端",
                 "组件", "函数", "接口", "数据库", "写一个", "帮我写", "code", "bug",
                 "前后端", "登录页面", "注册", "CRUD"],
    "research": ["调研", "分析", "比较", "推荐", "优缺点", "最新", "技术选型",
                 "什么是最好的", "有什么区别", "research", "对比"],
    "design_ui": ["UI", "界面", "设计", "样式", "CSS", "布局", "颜色", "好看",
                  "美化", "页面", "组件样式", "UX", "交互", "视觉效果"],
    "general_qa": [],
}

AGENT_INTENT_SCORES: dict[str, dict[str, int]] = {
    "claude":   {"code_gen": 10, "research": 8, "design_ui": 7, "general_qa": 8},
    "deepseek": {"code_gen": 9, "research": 7, "design_ui": 5, "general_qa": 7},
    "openai":   {"code_gen": 9, "research": 7, "design_ui": 6, "general_qa": 8},
    "gemini":   {"code_gen": 7, "research": 10, "design_ui": 5, "general_qa": 7},
    "glm":      {"code_gen": 6, "research": 5, "design_ui": 4, "general_qa": 6},
    "minimax":  {"code_gen": 5, "research": 4, "design_ui": 4, "general_qa": 5},
}

COMPLEX_MARKERS = ["前后端", "API+", "全栈", "前端和后端", "都要",
                   "同时", "一起", "以及", "还有", "并且"]

TASK_TEMPLATES: dict[str, list[dict]] = {
    "code_gen": [
        {"task": "frontend", "tags": ["code", "UI", "frontend", "React"]},
        {"task": "backend", "tags": ["code", "API", "backend", "Python"]},
    ],
    "research": [
        {"task": "search", "tags": ["research", "search", "analysis"]},
        {"task": "summary", "tags": ["writing", "general", "summary"]},
    ],
}

CHAIN_TEMPLATES: dict[str, list[str]] = {
    "code_review": ["claude", "deepseek"],
    "design_to_code": ["gemini", "claude"],
}


# ===== Pipeline 数据类型 =====

@dataclass
class PipelineRequest:
    session_id: str
    content: str
    mentions: list[str] | None
    messages: list[dict]
    member_agents: list[AgentConfig]
    system_prompt: str = ""
    pinned_message_ids: list[str] = field(default_factory=list)
    context_budget: int = 100_000
    reserve_tokens: int = 4096


@dataclass
class AgentCall:
    agent: AgentConfig
    task: str = "primary"
    input_messages: list[dict] = field(default_factory=list)


@dataclass
class PipelineResult:
    agent_calls: list[AgentCall]
    execution_mode: str  # "single" | "parallel" | "chain"
    assembled_messages: list[dict]
    total_tokens: int
    truncated: bool
    intent: str = "general_qa"


# ===== Pipeline =====

class OrchestratorV2:
    """Pipeline 模式智能编排器。

    用法:
        pipeline = OrchestratorV2(context_manager, event_bus)
        result = await pipeline.run(PipelineRequest(...))
        # result.agent_calls 即确定要调用的 Agent 列表
    """

    def __init__(self, context_manager=None, event_bus=None):
        self._ctx = context_manager
        self._event_bus = event_bus

    # ---- Public API ----

    async def run(self, req: PipelineRequest) -> PipelineResult:
        intent = self.detect_intent(req.content)

        # Stage 1: Context Assembly (if ContextManager provided)
        assembled, truncated = self._assemble_context(req)

        # Stage 2: Agent Selection
        agents = self._select_agents(req, intent)

        # Stage 3: Execution Planning
        mode, calls = self._plan_execution(req, agents, intent, assembled)

        # Stage 4: Lifecycle events
        await self._emit_task_started(req.session_id, intent, calls)

        return PipelineResult(
            agent_calls=calls,
            execution_mode=mode,
            assembled_messages=assembled,
            total_tokens=sum(len(m.get("content", "")) for m in assembled) // 3,
            truncated=truncated,
            intent=intent,
        )

    # ---- Stage 1: Context ----

    def _assemble_context(self, req: PipelineRequest) -> tuple[list[dict], bool]:
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

    # ---- Stage 2: Selection ----

    def _select_agents(self, req: PipelineRequest, intent: str) -> list[AgentConfig]:
        if req.mentions:
            mention_set = set(req.mentions)
            return [a for a in req.member_agents if a.id in mention_set]

        if req.member_agents:
            return self.score_agents(intent, req.member_agents)

        return []

    # ---- Stage 3: Execution Planning ----

    def _plan_execution(
        self, req: PipelineRequest, agents: list[AgentConfig],
        intent: str, messages: list[dict],
    ) -> tuple[str, list[AgentCall]]:
        if not agents:
            return "single", []

        if len(agents) == 1:
            return "single", [
                AgentCall(agent=agents[0], task="primary", input_messages=list(messages))
            ]

        if self.is_complex(req.content):
            tasks = self.decompose(intent, agents)
            if len(tasks) > 1:
                calls = [
                    AgentCall(agent=a, task=t, input_messages=list(messages))
                    for t, a in tasks if a
                ]
                return "parallel", calls

        return "parallel", [
            AgentCall(agent=a, task="primary", input_messages=list(messages))
            for a in agents[:5]
        ]

    # ---- Stage 4: Lifecycle ----

    async def _emit_task_started(self, session_id, intent, calls):
        if not self._event_bus:
            return
        try:
            await self._event_bus.publish(EventType.ORCHESTRATOR_TASK_STARTED, {
                "session_id": session_id,
                "intent": intent,
                "tasks": [c.task for c in calls],
                "agents": [c.agent.name for c in calls],
            })
        except Exception:
            logger.exception("EventBus publish failed")

    # ---- L1: Intent Detection ----

    @staticmethod
    def detect_intent(content: str) -> str:
        for intent, keywords in INTENT_KEYWORDS.items():
            if intent == "general_qa":
                continue
            for kw in keywords:
                if kw.lower() in content.lower():
                    return intent
        return "general_qa"

    # ---- Agent Scoring ----

    @staticmethod
    def score_agents(intent: str, agents: list[AgentConfig]) -> list[AgentConfig]:
        scored = []
        for a in agents:
            provider = (a.provider or "").lower()
            score = AGENT_INTENT_SCORES.get(provider, {}).get(intent, 5)
            scored.append((score, a))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored]

    # ---- L2: Complexity ----

    @staticmethod
    def is_complex(content: str) -> bool:
        return any(m in content for m in COMPLEX_MARKERS)

    @staticmethod
    def decompose(intent: str, agents: list[AgentConfig]) -> list[tuple[str, AgentConfig | None]]:
        templates = TASK_TEMPLATES.get(intent, [])
        if not templates or len(agents) < 2:
            return [("primary", agents[0] if agents else None)]

        tasks: list[tuple[str, AgentConfig | None]] = []
        available = list(agents)
        for tmpl in templates:
            matched = None
            for a in available:
                a_tags = a.system_prompt or ""
                if any(t.lower() in a_tags.lower() for t in tmpl.get("tags", [])):
                    matched = a
                    break
            if matched:
                available.remove(matched)
            else:
                matched = available.pop(0) if available else None
            tasks.append((tmpl["task"], matched))
        return tasks

    # ---- L3: Chain ----

    @staticmethod
    def get_chain(chain_name: str, agents: list[AgentConfig]) -> list[AgentConfig]:
        provider_order = CHAIN_TEMPLATES.get(chain_name, [])
        ordered = []
        for provider in provider_order:
            for a in agents:
                if (a.provider or "").lower() == provider:
                    ordered.append(a)
                    break
        return ordered

    async def emit_completed(self, session_id: str, summary: str = "") -> None:
        if not self._event_bus:
            return
        try:
            await self._event_bus.publish(EventType.ORCHESTRATOR_TASK_COMPLETED, {
                "session_id": session_id,
                "summary": summary,
            })
        except Exception:
            logger.exception("EventBus publish failed")
