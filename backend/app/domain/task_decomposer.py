"""任务拆解器 —— 复杂请求拆解 + 6 种动态角色分配。

Domain 层纯逻辑，零框架依赖。

Phase 3: 模板驱动的角色分配。
Phase 4: 升级为 LLM 动态角色识别。
"""

from dataclasses import dataclass, field

from .agent_profile import AgentProfileSnapshot


# ===== 6 种协作角色 =====

ROLE_DEFINITIONS: dict[str, str] = {
    "planner": "制定详细的技术方案和架构设计，不写具体实现代码",
    "executor": "按照上一步的方案，产出具体实现代码",
    "reviewer": "审查以上产出，指出代码质量问题、安全隐患和改进建议",
    "researcher": "搜索和收集相关信息与数据，整理为结构化分析材料",
    "synthesizer": "综合多方信息和分析结果，形成最终结论和建议",
    "critic": "以批判性视角审视方案，找出逻辑漏洞、遗漏点和潜在风险",
}

# ===== 复杂请求检测关键词 =====

COMPLEX_MARKERS: list[str] = [
    "前后端", "API+", "全栈", "前端和后端", "都要",
    "同时", "一起", "以及", "还有", "并且",
    "先", "再", "然后", "最后", "之后",
    "设计并实现", "从设计到",
]

# 多阶段链式触发关键词
CHAIN_MARKERS: list[str] = [
    "先", "再", "然后", "最后", "之后",
    "设计并实现", "从设计到",
    "调研并总结", "分析并优化",
]


# ===== 拆解模板 (意图 → 子任务 + 角色 + DAG 依赖) =====

@dataclass
class SubTask:
    """子任务定义。"""
    name: str                   # 任务名: "planning" | "frontend" | "search"
    role: str                   # 角色: "planner" | "executor" | "reviewer" | ...
    description: str            # 注入 Prompt 的任务描述
    tags: list[str] = field(default_factory=list)  # 匹配 Agent 的能力标签
    depends_on: list[str] = field(default_factory=list)  # 依赖的上游任务名
    phase: int = 0              # ExecutionPlanner 拓扑排序后写入


TASK_TEMPLATES: dict[str, list[SubTask]] = {
    "code_gen": [
        SubTask("planning", "planner",
                "分析需求，制定技术方案和架构设计，不写具体代码",
                ["架构", "设计", "方案"]),
        SubTask("frontend", "executor",
                "按照技术方案实现前端界面和交互逻辑",
                ["前端", "React", "UI", "组件"],
                depends_on=["planning"]),
        SubTask("backend", "executor",
                "按照技术方案实现后端 API 和数据库",
                ["后端", "API", "数据库", "Python"],
                depends_on=["planning"]),
        SubTask("review", "reviewer",
                "审查前端和后端代码的质量、安全性和一致性",
                ["审查", "测试", "安全"],
                depends_on=["frontend", "backend"]),
    ],
    "research": [
        SubTask("search", "researcher",
                "搜索和收集相关资料与数据",
                ["搜索", "分析", "调查"]),
        SubTask("synthesize", "synthesizer",
                "综合多方信息形成结构化结论",
                ["写作", "总结", "综合"],
                depends_on=["search"]),
        SubTask("critique", "critic",
                "审视结论的漏洞和局限性",
                ["批判", "检查", "验证"],
                depends_on=["synthesize"]),
    ],
    "design_ui": [
        SubTask("concept", "planner",
                "分析用户需求，制定设计策略",
                ["设计", "UI", "UX"]),
        SubTask("execution", "executor",
                "产出具体的 UI 设计和样式代码",
                ["前端", "CSS", "组件"],
                depends_on=["concept"]),
        SubTask("review", "reviewer",
                "审查设计的可用性和一致性",
                ["审查", "测试", "UI"],
                depends_on=["execution"]),
    ],
}


class TaskDecomposer:
    """任务拆解器 —— 复杂请求判断 + 角色模板拆解。

    用法:
        decomposer = TaskDecomposer()
        if decomposer.is_complex("前后端都要做"):
            tasks = decomposer.decompose("code_gen", scored_agents)
    """

    def is_complex(self, content: str) -> bool:
        """判断请求是否需要拆解。"""
        return any(m in content for m in COMPLEX_MARKERS)

    def is_chain(self, content: str) -> bool:
        """判断是否需要链式 (多阶段) 协作。"""
        return any(m in content for m in CHAIN_MARKERS)

    def decompose(
        self,
        intent: str,
        agents: list[AgentProfileSnapshot],
    ) -> list[tuple[SubTask, AgentProfileSnapshot | None]]:
        """按模板拆解任务，匹配最合适的 Agent。

        Returns:
            list[tuple[SubTask, AgentProfileSnapshot | None]]: 子任务与 Agent 的配对列表
        """
        templates = TASK_TEMPLATES.get(intent, [])
        if not templates or len(agents) < 2:
            return self._single_agent_fallback(agents)

        result: list[tuple[SubTask, AgentProfileSnapshot | None]] = []
        available = list(agents)
        all_agents = list(agents)

        for template in templates:
            subtask = self._clone_subtask(template)
            matched = self._match_agent_for_subtask(subtask, available)
            if matched:
                available.remove(matched)
            else:
                matched = available.pop(0) if available else self._match_agent_for_subtask(
                    subtask, all_agents,
                )
                matched = matched or (all_agents[0] if all_agents else None)
            result.append((subtask, matched))

        return result

    def _match_agent_for_subtask(
        self, subtask: SubTask, agents: list[AgentProfileSnapshot],
    ) -> AgentProfileSnapshot | None:
        """为子任务匹配最合适的 Agent —— 基于标签命中。"""
        best: AgentProfileSnapshot | None = None
        best_score = 0

        for agent in agents:
            search = (agent.description + " " + agent.system_prompt + " " + agent.name).lower()
            score = sum(1 for tag in subtask.tags if tag.lower() in search)
            if score > best_score:
                best_score = score
                best = agent

        return best if best_score > 0 else None

    def _single_agent_fallback(
        self, agents: list[AgentProfileSnapshot],
    ) -> list[tuple[SubTask, AgentProfileSnapshot | None]]:
        """只有一个 Agent 或无模板时的降级。"""
        primary = SubTask("primary", "executor", "完成用户的任务", [])
        return [(primary, agents[0] if agents else None)]

    @staticmethod
    def _clone_subtask(subtask: SubTask) -> SubTask:
        """复制模板任务，避免 phase 写入污染全局模板。"""
        return SubTask(
            name=subtask.name,
            role=subtask.role,
            description=subtask.description,
            tags=list(subtask.tags),
            depends_on=list(subtask.depends_on),
            phase=subtask.phase,
        )

    def get_role_prompt(self, role: str) -> str:
        """获取角色对应的 Prompt 注入文本。"""
        desc = ROLE_DEFINITIONS.get(role, "完成用户的任务")
        return f"[角色: {role}]\n{desc}"
