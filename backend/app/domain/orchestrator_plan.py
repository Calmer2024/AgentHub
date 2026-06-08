"""Plan-first Orchestrator helpers.

The Orchestrator Agent is an Agent Profile that returns a draft plan. This
module keeps parsing, normalization, validation, and UI projection independent
from CLI execution.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict, deque
from typing import Any


PLAN_SCHEMA: dict[str, Any] = {
    "plan_id": "plan_xxx",
    "status": "draft",
    "execution_policy": {
        "mode": "plan_only",
        "requires_approval_before_execution": True,
    },
    "tasks": [{
        "task_id": "T1",
        "title": "任务标题",
        "goal": "任务目标",
        "required_skills": ["frontend", "react"],
        "assigned_agent_id": "agent_id",
        "assigned_agent_name": "Agent 显示名称",
        "assignment_reason": "为什么分配给它",
        "depends_on": [],
        "expected_outputs": ["交付物类型或建议位置，不要强制精确文件名"],
        "acceptance_criteria": ["可验证的完成标准"],
        "needs_approval": False,
        "is_blocking": True,
    }],
    "execution_strategy": {
        "parallelizable_groups": [["T2", "T3"]],
        "critical_path": ["T1", "T4"],
    },
}


def build_plan_prompt(content: str, candidate_agents: list[dict[str, Any]]) -> str:
    agent_lines = []
    for agent in candidate_agents:
        agent_lines.append(
            "- "
            f"id={agent.get('id')}; "
            f"name={agent.get('name')}; "
            f"engine={agent.get('engine')}; "
            f"primary_skill={agent.get('primary_skill')}; "
            f"auxiliary_skills={agent.get('auxiliary_skills')}"
        )
    return (
        "请作为 AgentHub Orchestrator Agent，把用户需求拆成 plan-only DAG。\n"
        "只输出一个 JSON 对象，不要输出 Markdown 说明，不要执行任务，不要修改文件。\n\n"
        "候选 Agent Profiles:\n"
        f"{chr(10).join(agent_lines) if agent_lines else '- 无候选 Agent'}\n\n"
        "输出必须符合这个最小结构，字段可扩展但不要缺少关键字段：\n"
        f"{json.dumps(PLAN_SCHEMA, ensure_ascii=False, indent=2)}\n\n"
        "要求：\n"
        "1. 每个任务必须有 task_id/title/goal/required_skills/depends_on。\n"
        "2. 优先按 required_skills 解释任务需要什么能力。\n"
        "3. 可以填写 assigned_agent_id 和 assigned_agent_name，但必须写 assignment_reason。\n"
        "4. depends_on 必须引用已有 task_id，整体必须是 DAG。\n"
        "5. status 固定为 draft，execution_policy.mode 固定为 plan_only。\n"
        "6. expected_outputs 只描述交付物类型、目录层级或建议位置；除非用户明确指定，"
        "不要精确到固定文件名，避免限制执行 Agent 的实现选择。"
        "如果用户要求 PRD、架构设计、接口说明、测试清单等正式项目文档，"
        "expected_outputs 应明确建议写入项目 `docs/`，不要只写“document”。\n"
        "7. acceptance_criteria 写成可验收的行为/质量标准，不要把语言要求重复塞进每个任务。\n"
        "8. 输出语言遵循用户输入语言；用户用中文时，计划标题、目标、交接说明和后续执行要求都用中文。\n\n"
        f"用户需求：\n{content.strip()}\n"
    )


def build_plan_followup_prompt(
    content: str,
    candidate_agents: list[dict[str, Any]],
    latest_plan: dict[str, Any],
) -> str:
    return (
        "请作为 AgentHub Orchestrator Agent，处理用户对上一版 draft plan 的跟进消息。\n"
        "你必须只输出一个 JSON 对象，不要输出 Markdown 说明，不要执行任务，不要修改文件。\n\n"
        "如果用户明确批准、确认、开始执行上一版计划，请输出控制 JSON：\n"
        "{\n"
        '  "action": "approve_plan",\n'
        '  "target_plan_id": "上一版 plan_id",\n'
        '  "reason": "为什么判断用户是在批准执行"\n'
        "}\n\n"
        "如果用户明确表示先不执行、放弃、取消、不再跟进或把这版计划挂起作废，请输出控制 JSON：\n"
        "{\n"
        '  "action": "discard_plan",\n'
        '  "target_plan_id": "上一版 plan_id",\n'
        '  "reason": "为什么判断用户是在放弃这版计划"\n'
        "}\n\n"
        "如果用户提出修改、补充、删除、合并、重新分配等意见，请输出一份新的 draft plan JSON，"
        "结构仍必须符合 Plan JSON / DAG schema，不要输出 approve_plan。\n\n"
        "如果用户只是开启了一个和上一版计划无关的新话题，也应输出 discard_plan，"
        "让本轮对话退出上一版计划的待处理状态。\n\n"
        "计划约束：expected_outputs 只描述交付物类型、目录层级或建议位置；除非用户明确指定，"
        "不要精确到固定文件名。如果用户要求正式项目文档，expected_outputs 应明确建议写入项目 `docs/`，"
        "不要只写“document”。输出语言遵循用户输入语言；用户用中文时，计划内容也用中文。\n\n"
        "候选 Agent Profiles:\n"
        f"{_agent_lines(candidate_agents)}\n\n"
        "上一版 draft plan：\n"
        f"{json.dumps(latest_plan, ensure_ascii=False, indent=2)}\n\n"
        f"用户跟进消息：\n{content.strip()}\n"
    )


def _agent_lines(candidate_agents: list[dict[str, Any]]) -> str:
    agent_lines = []
    for agent in candidate_agents:
        agent_lines.append(
            "- "
            f"id={agent.get('id')}; "
            f"name={agent.get('name')}; "
            f"engine={agent.get('engine')}; "
            f"primary_skill={agent.get('primary_skill')}; "
            f"auxiliary_skills={agent.get('auxiliary_skills')}"
        )
    return chr(10).join(agent_lines) if agent_lines else "- 无候选 Agent"


def extract_json_object(raw: str) -> dict[str, Any]:
    text = _strip_code_fence(raw)
    decoder = json.JSONDecoder()
    candidates = [text]
    first_brace = text.find("{")
    if first_brace >= 0:
        candidates.append(text[first_brace:])
    for candidate in candidates:
        try:
            data, _ = decoder.raw_decode(candidate.strip())
        except json.JSONDecodeError:
            data = _repair_approve_action_json(candidate)
        if isinstance(data, dict):
            return data
    raise ValueError("调度器输出中未找到合法 JSON 对象")


def _repair_approve_action_json(text: str) -> dict[str, Any] | None:
    """Repair the narrow common case where only approve reason has raw quotes."""
    if '"action"' not in text or "approve_plan" not in text:
        return None
    action = _extract_json_string_field(text, "action")
    target_plan_id = _extract_json_string_field(text, "target_plan_id")
    reason = _extract_json_string_field(text, "reason", last=True)
    if action != "approve_plan" or not target_plan_id:
        return None
    return {
        "action": action,
        "target_plan_id": target_plan_id,
        "reason": reason or "",
    }


def _extract_json_string_field(text: str, field: str, *, last: bool = False) -> str | None:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"', text)
    if not match:
        return None
    start = match.end()
    if last:
        end = text.rfind('"')
        return text[start:end] if end >= start else None
    match_end = re.search(r'"\s*(?:,|\})', text[start:], flags=re.S)
    if not match_end:
        return None
    return text[start:start + match_end.start()]


def normalize_plan(raw_plan: dict[str, Any]) -> dict[str, Any]:
    plan = dict(raw_plan)
    plan["plan_id"] = str(plan.get("plan_id") or f"plan_{uuid.uuid4().hex[:8]}")
    plan["status"] = str(plan.get("status") or "draft")
    policy = plan.get("execution_policy")
    if not isinstance(policy, dict):
        policy = {}
    policy.setdefault("mode", "plan_only")
    policy.setdefault("requires_approval_before_execution", True)
    plan["execution_policy"] = policy

    tasks = plan.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    normalized_tasks = []
    for index, item in enumerate(tasks, start=1):
        task = item if isinstance(item, dict) else {}
        task_id = str(task.get("task_id") or task.get("id") or f"T{index}")
        title = str(task.get("title") or task.get("name") or f"任务 {index}")
        required = _string_list(task.get("required_skills") or task.get("required_skill"))
        depends_on = _string_list(task.get("depends_on") or task.get("dependencies"))
        normalized_tasks.append({
            **task,
            "task_id": task_id,
            "title": title,
            "goal": str(task.get("goal") or task.get("description") or title),
            "required_skills": required,
            "assigned_agent_id": _optional_str(task.get("assigned_agent_id")),
            "assigned_agent_name": _optional_str(task.get("assigned_agent_name") or task.get("agent_name")),
            "assignment_reason": str(task.get("assignment_reason") or ""),
            "depends_on": depends_on,
            "expected_outputs": _string_list(task.get("expected_outputs")),
            "acceptance_criteria": _string_list(task.get("acceptance_criteria")),
            "needs_approval": bool(task.get("needs_approval") or task.get("requires_human_approval") or False),
            "is_blocking": bool(task.get("is_blocking") if "is_blocking" in task else True),
        })
    plan["tasks"] = normalized_tasks

    strategy = plan.get("execution_strategy")
    if not isinstance(strategy, dict):
        strategy = {}
    strategy.setdefault("parallelizable_groups", [])
    strategy.setdefault("critical_path", _critical_path(normalized_tasks))
    plan["execution_strategy"] = strategy
    return plan


def validate_plan(plan: dict[str, Any], candidate_agent_ids: set[str] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    tasks = plan.get("tasks") if isinstance(plan.get("tasks"), list) else []
    ids = [str(task.get("task_id")) for task in tasks if isinstance(task, dict)]
    duplicate_ids = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
    if duplicate_ids:
        errors.append(f"task_id 重复: {', '.join(duplicate_ids)}")
    id_set = set(ids)
    if not tasks:
        errors.append("tasks 不能为空")

    for task in tasks:
        if not isinstance(task, dict):
            errors.append("tasks 中存在非对象任务")
            continue
        task_id = str(task.get("task_id"))
        for dep in _string_list(task.get("depends_on")):
            if dep not in id_set:
                errors.append(f"{task_id}.depends_on 引用了不存在的任务: {dep}")
        if not _string_list(task.get("required_skills")):
            warnings.append(f"{task_id} 未填写 required_skills")
        assigned = task.get("assigned_agent_id")
        if assigned and candidate_agent_ids is not None and str(assigned) not in candidate_agent_ids:
            warnings.append(f"{task_id}.assigned_agent_id 不在候选 Agent 中: {assigned}")

    if tasks and not any(not _string_list(task.get("depends_on")) for task in tasks if isinstance(task, dict)):
        errors.append("DAG 至少需要一个起点任务")
    cycle = _find_cycle(tasks)
    if cycle:
        errors.append(f"DAG 存在循环依赖: {' -> '.join(cycle)}")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def plan_to_collab_payload(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tasks = plan.get("tasks") if isinstance(plan.get("tasks"), list) else []
    task_payloads = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_payloads.append({
            "name": str(task.get("title") or task.get("task_id")),
            "role": _role_from_skills(_string_list(task.get("required_skills"))),
            "agent": str(task.get("assigned_agent_name") or task.get("assigned_agent_id") or "待分配"),
            "agentId": task.get("assigned_agent_id"),
            "status": "pending",
            "depends_on": _string_list(task.get("depends_on")),
            "phase": _phase_for_task(task, tasks),
            "summary": str(task.get("goal") or ""),
        })
    phases = []
    for phase, phase_tasks in sorted(_group_by_phase(task_payloads).items()):
        phases.append({
            "phase": phase,
            "mode": "parallel" if len(phase_tasks) > 1 else "serial",
            "tasks": phase_tasks,
        })
    return task_payloads, {"phases": phases}


def visualize_mermaid(plan: dict[str, Any]) -> str:
    lines = ["graph TD"]
    tasks = plan.get("tasks") if isinstance(plan.get("tasks"), list) else []
    for task in tasks:
        task_id = str(task.get("task_id"))
        title = str(task.get("title") or task_id).replace('"', "'")
        lines.append(f'  {task_id}["{task_id}: {title}"]')
    for task in tasks:
        task_id = str(task.get("task_id"))
        for dep in _string_list(task.get("depends_on")):
            lines.append(f"  {dep} --> {task_id}")
    return "\n".join(lines)


def _strip_code_fence(raw: str) -> str:
    text = raw.strip().lstrip("\ufeff")
    match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
    return match.group(1).strip() if match else text


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _critical_path(tasks: list[dict[str, Any]]) -> list[str]:
    return [str(task.get("task_id")) for task in tasks]


def _find_cycle(tasks: list[Any]) -> list[str]:
    graph = {
        str(task.get("task_id")): _string_list(task.get("depends_on"))
        for task in tasks
        if isinstance(task, dict)
    }
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        if node in visiting:
            start = stack.index(node) if node in stack else 0
            return stack[start:] + [node]
        if node in visited:
            return []
        visiting.add(node)
        stack.append(node)
        for dep in graph.get(node, []):
            cycle = visit(dep)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in graph:
        cycle = visit(node)
        if cycle:
            return cycle
    return []


def _phase_for_task(task: dict[str, Any], all_tasks: list[Any]) -> int:
    task_id = str(task.get("task_id"))
    graph = {
        str(item.get("task_id")): _string_list(item.get("depends_on"))
        for item in all_tasks
        if isinstance(item, dict)
    }
    cache: dict[str, int] = {}

    def depth(node: str) -> int:
        if node in cache:
            return cache[node]
        deps = graph.get(node, [])
        cache[node] = 0 if not deps else 1 + max(depth(dep) for dep in deps if dep in graph)
        return cache[node]

    return depth(task_id)


def _group_by_phase(tasks: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        grouped[int(task.get("phase") or 0)].append(task)
    return grouped


def _role_from_skills(skills: list[str]) -> str:
    joined = " ".join(skills).lower()
    if any(word in joined for word in ("review", "test", "security", "审查", "测试")):
        return "reviewer"
    if any(word in joined for word in ("architect", "plan", "schema", "requirements", "架构", "需求")):
        return "planner"
    return "executor"
