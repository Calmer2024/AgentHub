"""执行计划器 —— 决定执行模式 + 构建 AgentCall 列表。

Domain 层纯逻辑，零框架依赖。

模式决策优先级链:
  1. supplemental=True → mode="single|serial" (只补充被点名/缺失 Agent)
  2. chain_config 存在 → mode="chain"
  3. is_chain(content) AND agents >= 2 → mode="dag" (自动 DAG)
  4. is_complex(content) AND agents >= 2 → mode="dag" + decompose
  5. len(agents) == 1 → mode="single"
  6. len(agents) >= 2 → mode="serial" (all primary)
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
    depends_on: list[str] = field(default_factory=list)
    phase: int = 0


@dataclass
class DAGPhase:
    """DAG 执行阶段。Phase 间串行，Phase 内可并行。"""
    phase: int
    calls: list[AgentCall]
    mode: str = "serial"            # "serial" | "parallel"


@dataclass
class ChainConfig:
    """链式协作配置 (运行时参数)。"""
    chain_name: str | None = None           # 模板名 (Phase 3)
    agent_order: list[str] | None = None    # Agent ID 顺序


@dataclass
class ExecutionPlan:
    """执行计划。"""
    mode: str                            # "single" | "serial" | "chain" | "dag"
    calls: list[AgentCall]
    decomposer_used: bool = False
    chain_auto_triggered: bool = False   # 是否为自动触发的链式
    dag_phases: list[DAGPhase] = field(default_factory=list)


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
        supplemental: bool = False,
    ) -> ExecutionPlan:
        """根据优先级链决定执行模式并构建调用列表。"""
        if not agents:
            return ExecutionPlan(mode="empty", calls=[])

        # 优先级 1: 追问补充只调用被点名/缺失 Agent，不重新拆完整 DAG。
        if supplemental:
            return self._build_primary_plan(agents, messages)

        # 优先级 2: 显式 chain_config
        if chain_config and len(agents) >= 2:
            return self._build_chain_plan(agents, messages, chain_config,
                                          auto_triggered=False)

        # 优先级 2: 自动 DAG 触发 (多阶段关键词)
        if self.decomposer.is_chain(content) and len(agents) >= 2:
            return self._build_dag_plan(
                agents, content, messages, auto_triggered=True,
            )

        # 优先级 3: 复杂请求拆解为 DAG
        if self.decomposer.is_complex(content) and len(agents) >= 2:
            return self._build_dag_plan(
                agents, content, messages, auto_triggered=False,
            )

        # 优先级 5: 单 Agent
        if len(agents) == 1:
            return self._build_primary_plan(agents, messages)

        # 优先级 6: 多 Agent 并行 (无拆解)
        return self._build_primary_plan(agents, messages)

    # ---- 内部构建方法 ----

    @staticmethod
    def _build_primary_plan(
        agents: list[AgentConfig], messages: list[dict],
    ) -> ExecutionPlan:
        return ExecutionPlan(
            mode="single" if len(agents) == 1 else "serial",
            calls=[
                AgentCall(agent=a, task="primary", role="executor",
                          input_messages=list(messages))
                for a in agents[:5]
            ],
        )

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

    def _build_dag_plan(
        self, agents: list[AgentConfig], content: str, messages: list[dict],
        auto_triggered: bool,
    ) -> ExecutionPlan:
        """按模板拆解为 DAG 执行计划。"""
        intent = self._detect_intent_simple(content)
        subtask_pairs = self.decomposer.decompose(intent, agents)
        subtasks = [s for s, agent in subtask_pairs if agent is not None]
        self._assign_phases(subtasks)

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
                depends_on=list(subtask.depends_on),
                phase=subtask.phase,
            ))

        if len(calls) <= 1:
            return ExecutionPlan(
                mode="single",
                calls=calls if calls else [AgentCall(
                    agent=agents[0], task="primary", role="executor",
                    input_messages=list(messages),
                )],
            )

        phases = self._group_calls_by_phase(calls)
        return ExecutionPlan(
            mode="dag",
            calls=calls,
            decomposer_used=True,
            chain_auto_triggered=auto_triggered,
            dag_phases=phases,
        )

    def _assign_phases(self, subtasks: list[SubTask]) -> None:
        """拓扑排序并将 phase 写回 SubTask。"""
        remaining = {t.name: t for t in subtasks}
        assigned: dict[str, int] = {}
        phase = 0

        while remaining:
            ready = [
                t for t in remaining.values()
                if all(dep in assigned for dep in t.depends_on)
            ]
            if not ready:
                # 模板被误配置成环或缺依赖时，按原顺序降级为串行。
                for task in remaining.values():
                    task.phase = phase
                    phase += 1
                return

            for task in ready:
                task.phase = phase
                assigned[task.name] = phase
                remaining.pop(task.name)
            phase += 1

    @staticmethod
    def _group_calls_by_phase(calls: list[AgentCall]) -> list[DAGPhase]:
        """将调用按 phase 分组，Phase 内多调用则并行。"""
        phase_map: dict[int, list[AgentCall]] = {}
        for call in calls:
            phase_map.setdefault(call.phase, []).append(call)
        return [
            DAGPhase(
                phase=idx,
                calls=phase_map[idx],
                mode="serial",
            )
            for idx in sorted(phase_map)
        ]

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
