"""执行计划器 —— 决定执行模式 + 构建 AgentCall 列表。

Domain 层纯逻辑，零框架依赖。

模式决策优先级链:
  1. chain_config 存在 → mode="chain"
  2. is_chain(content) AND agents >= 2 → mode="chain" (自动链式)
  3. is_complex(content) AND agents >= 2 → mode="parallel" + decompose
  4. len(agents) == 1 → mode="single"
  5. len(agents) >= 2 → mode="parallel" (all primary)
"""

from dataclasses import dataclass, field

from ..models import AgentConfig
from .task_decomposer import TaskDecomposer, SubTask


@dataclass
class AgentCall:
    """单个 Agent 调用单元。"""
    agent: AgentConfig
    task: str = "primary"           # 任务名称
    role: str = "executor"          # 协作角色
    input_messages: list[dict] = field(default_factory=list)
    role_prompt_override: str | None = None  # 角色 Prompt 注入


@dataclass
class ChainConfig:
    """链式协作配置 (运行时参数)。"""
    chain_name: str | None = None           # 模板名 (Phase 3)
    agent_order: list[str] | None = None    # Agent ID 顺序


@dataclass
class ExecutionPlan:
    """执行计划。"""
    mode: str                            # "single" | "parallel" | "chain"
    calls: list[AgentCall]
    decomposer_used: bool = False
    chain_auto_triggered: bool = False   # 是否为自动触发的链式


class ExecutionPlanner:
    """执行计划器 —— 决定编排模式并构建 AgentCall 列表。

    用法:
        planner = ExecutionPlanner(decomposer)
        plan = planner.plan(scored_agents, content, messages, chain_config=None)
    """

    def __init__(self, decomposer: TaskDecomposer | None = None):
        self.decomposer = decomposer or TaskDecomposer()

    def plan(
        self,
        agents: list[AgentConfig],
        content: str,
        messages: list[dict],
        chain_config: ChainConfig | None = None,
    ) -> ExecutionPlan:
        """根据优先级链决定执行模式并构建调用列表。"""
        if not agents:
            return ExecutionPlan(mode="empty", calls=[])

        # 优先级 1: 显式 chain_config
        if chain_config and len(agents) >= 2:
            return self._build_chain_plan(agents, messages, chain_config,
                                          auto_triggered=False)

        # 优先级 2: 自动链式触发 (多阶段关键词)
        if self.decomposer.is_chain(content) and len(agents) >= 2:
            return self._build_auto_chain_plan(agents, content, messages)

        # 优先级 3: 复杂请求拆解
        if self.decomposer.is_complex(content) and len(agents) >= 2:
            return self._build_parallel_decompose_plan(agents, content, messages)

        # 优先级 4: 单 Agent
        if len(agents) == 1:
            return ExecutionPlan(
                mode="single",
                calls=[AgentCall(
                    agent=agents[0], task="primary", role="executor",
                    input_messages=list(messages),
                )],
            )

        # 优先级 5: 多 Agent 并行 (无拆解)
        return ExecutionPlan(
            mode="parallel",
            calls=[
                AgentCall(agent=a, task="primary", role="executor",
                          input_messages=list(messages))
                for a in agents[:5]
            ],
        )

    # ---- 内部构建方法 ----

    def _build_chain_plan(
        self, agents: list[AgentConfig], messages: list[dict],
        chain_config: ChainConfig, auto_triggered: bool,
    ) -> ExecutionPlan:
        """构建链式执行计划。"""
        if chain_config.agent_order:
            # 按指定顺序排列 Agent
            ordered = []
            for aid in chain_config.agent_order:
                for a in agents:
                    if a.id == aid:
                        ordered.append(a)
                        break
            agents = ordered if ordered else agents

        calls: list[AgentCall] = []
        for i, agent in enumerate(agents[:5]):
            role = self._assign_chain_role(i, len(agents[:5]))
            calls.append(AgentCall(
                agent=agent,
                task=role,
                role=role,
                input_messages=list(messages),
                role_prompt_override=self.decomposer.get_role_prompt(role),
            ))

        return ExecutionPlan(
            mode="chain", calls=calls,
            chain_auto_triggered=auto_triggered,
        )

    def _build_auto_chain_plan(
        self, agents: list[AgentConfig], content: str, messages: list[dict],
    ) -> ExecutionPlan:
        """自动触发链式: 按意图模板拆解后，按角色顺序串行。"""
        # 先用朴素意图检测决定 intent
        intent = self._detect_intent_simple(content)

        # 拆解获得角色分配
        subtask_pairs = self.decomposer.decompose(intent, agents)

        calls: list[AgentCall] = []
        for subtask, agent in subtask_pairs:
            if agent is None:
                continue
            calls.append(AgentCall(
                agent=agent,
                task=subtask.name,
                role=subtask.role,
                input_messages=list(messages),
                role_prompt_override=self.decomposer.get_role_prompt(subtask.role),
            ))

        if len(calls) <= 1:
            # 拆解后只有一个有效 Agent → 降级为 single
            return ExecutionPlan(
                mode="single",
                calls=calls if calls else [AgentCall(
                    agent=agents[0], task="primary", role="executor",
                    input_messages=list(messages),
                )],
            )

        return ExecutionPlan(
            mode="chain", calls=calls,
            chain_auto_triggered=True,
            decomposer_used=True,
        )

    def _build_parallel_decompose_plan(
        self, agents: list[AgentConfig], content: str, messages: list[dict],
    ) -> ExecutionPlan:
        """复杂请求并行拆解。"""
        intent = self._detect_intent_simple(content)
        subtask_pairs = self.decomposer.decompose(intent, agents)

        calls: list[AgentCall] = []
        for subtask, agent in subtask_pairs:
            if agent is None:
                continue
            calls.append(AgentCall(
                agent=agent,
                task=subtask.name,
                role=subtask.role,
                input_messages=list(messages),
                role_prompt_override=self.decomposer.get_role_prompt(subtask.role),
            ))

        if not calls:
            return ExecutionPlan(
                mode="parallel",
                calls=[AgentCall(agent=a, task="primary", role="executor",
                                 input_messages=list(messages))
                       for a in agents[:5]],
            )

        return ExecutionPlan(
            mode="parallel", calls=calls,
            decomposer_used=True,
        )

    def _assign_chain_role(self, step: int, total: int) -> str:
        """为链式步骤分配角色。"""
        if total >= 3:
            roles = ["planner", "executor", "reviewer"]
            return roles[step] if step < len(roles) else "executor"
        else:
            return "executor" if step == 0 else "reviewer"

    @staticmethod
    def _detect_intent_simple(content: str) -> str:
        """轻量意图检测 (供 planner 内部使用，不依赖 IntentAnalyzer)。"""
        from .intent_analyzer import INTENT_RULES
        content_lower = content.lower()
        for intent_name, rules in INTENT_RULES.items():
            if intent_name == "general_qa":
                continue
            for kw in rules["keywords"]:
                if kw.lower() in content_lower:
                    return intent_name
        return "general_qa"
