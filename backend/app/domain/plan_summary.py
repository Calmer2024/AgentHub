"""执行计划的轻量用户解释。"""

from .execution_planner import AgentCall, DAGPhase

ROLE_ACTIONS = {
    "planner": "规划",
    "executor": "执行",
    "reviewer": "审查",
    "researcher": "调研",
    "synthesizer": "综合",
    "critic": "质疑补充",
}


def build_plan_summary(
    mode: str, calls: list[AgentCall], dag_phases: list[DAGPhase] | None = None,
) -> str:
    """生成给用户看的轻量分工解释。"""
    if not calls:
        return "暂无可执行安排。"
    if mode == "dag" and dag_phases:
        return f"已安排: {'，'.join(_phase_part(p, i, len(dag_phases)) for i, p in enumerate(dag_phases))}。"
    if mode == "chain":
        return f"已安排: 按 {_names(calls, sep=' → ')} 顺序协作。"
    if mode == "serial" and len(calls) > 1:
        return f"已安排: 按 {_names(calls, sep=' → ')} 顺序处理。"
    if mode == "parallel" and len(calls) > 1:
        return f"已安排: 由{_names(calls)}并行处理。"
    return f"已安排: 由@{calls[0].agent.name}直接处理。"


def _phase_part(phase: DAGPhase, index: int, total: int) -> str:
    prefix = "先" if index == 0 else "最后" if index == total - 1 else "再"
    if len(phase.calls) > 1:
        roles = {c.role for c in phase.calls}
        action = ROLE_ACTIONS.get(next(iter(roles)), "协作") if len(roles) == 1 else "协作"
        if phase.mode == "serial":
            return f"{prefix}按{_names(phase.calls, sep=' → ')}顺序{action}"
        return f"{prefix}由{_names(phase.calls)}并行{action}"
    call = phase.calls[0]
    action = ROLE_ACTIONS.get(call.role, "处理")
    return f"{prefix}由@{call.agent.name}{action}"


def _names(calls: list[AgentCall], sep: str = "、") -> str:
    return sep.join(f"@{c.agent.name}" for c in calls)
