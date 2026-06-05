"""Plan-first Orchestrator debug helpers.

This module powers the manual Orchestrator bridge. It does not call a model or
execute worker agents; it only builds the prompt, parses pasted output, validates
the draft plan, and produces a visualization.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..models import AgentConfig


PLAN_SCHEMA: dict[str, Any] = {
    "plan_id": "plan_001",
    "status": "draft",
    "execution_policy": "manual_approval_required",
    "tasks": [
        {
            "task_id": "T1",
            "title": "架构设计与接口契约",
            "goal": "明确系统模块、API 契约和数据模型",
            "required_skills": ["architecture", "api_design"],
            "assigned_agent_id": "mock_architect",
            "assigned_agent_name": "架构专家",
            "assignment_reason": "匹配 architecture 主 skill",
            "depends_on": [],
            "expected_outputs": ["document"],
            "acceptance_criteria": ["产出 API 契约", "产出数据模型"],
            "needs_approval": True,
            "is_blocking": True,
        }
    ],
    "execution_strategy": {
        "summary": "先需求和契约，再并行实现，最后验收。",
        "phases": [
            {
                "phase": 1,
                "mode": "serial",
                "tasks": ["T1"],
                "reason": "需求和架构是后续任务的阻塞前置",
            }
        ],
    },
}


@dataclass
class OrchestratorBridgeRequest:
    """Input for building the manual bridge prompt."""

    content: str
    agents: list[AgentConfig]


class OrchestratorInputBuilder:
    """Builds the copyable prompt for an external Orchestrator model."""

    def build(self, req: OrchestratorBridgeRequest) -> dict[str, Any]:
        candidates = [agent_payload(a) for a in req.agents]
        orchestrator_agent = {
            "id": "manual-orchestrator",
            "name": "手动调度器",
            "engine": "manual_bridge",
            "primarySkill": "orchestrator_planner",
            "auxiliarySkills": ["task_decomposition", "agent_assignment", "dag_planning"],
        }
        return {
            "input": {
                "content": req.content,
                "agentCount": len(candidates),
            },
            "orchestratorAgent": orchestrator_agent,
            "candidateAgents": candidates,
            "prompt": self._prompt(req.content, candidates),
            "outputSchema": PLAN_SCHEMA,
        }

    def _prompt(self, content: str, candidates: list[dict[str, Any]]) -> str:
        agent_json = json.dumps(candidates, ensure_ascii=False, indent=2)
        schema_json = json.dumps(PLAN_SCHEMA, ensure_ascii=False, indent=2)
        return (
            "你是 AgentHub 的 Orchestrator 调度器。你的任务是只输出一个 draft plan JSON，"
            "不要写解释，不要执行任务，不要调用工具。\n\n"
            "调度原则：\n"
            "1. 任务拆到模块/交付物级，不拆到创建文件、安装依赖、写函数这类代码步骤级。\n"
            "2. 每个任务同时保留 required_skills 与 assigned_agent_id，"
            "执行按 Agent，解释和兜底按能力。\n"
            "3. depends_on 必须组成有向无环图。\n"
            "4. 关键阻塞节点设置 is_blocking=true，通常也 needs_approval=true。\n"
            "5. 如果没有合适 Agent，可将 assigned_agent_id 设为 null，并在 assignment_reason 说明。\n\n"
            "用户需求：\n"
            f"{content.strip()}\n\n"
            "候选 Agent 快照：\n"
            f"{agent_json}\n\n"
            "必须输出符合这个最小 Schema 的 JSON，字段名保持一致：\n"
            f"{schema_json}\n\n"
            "只输出 JSON。"
        )


class PlanParser:
    """Extracts a JSON object from pasted model output."""

    def parse(self, raw_output: str) -> tuple[dict[str, Any] | None, list[str]]:
        text = raw_output.strip()
        if not text:
            return None, ["rawOutput 不能为空"]

        candidates = self._json_candidates(text)
        decode_errors: list[str] = []
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as exc:
                decode_errors.append(self._decode_error(candidate, exc))
                continue
            if isinstance(parsed, dict):
                return parsed, []
            return None, ["调度器输出必须是 JSON object"]

        errors = [
            "无法从 rawOutput 中解析 JSON，请粘贴纯 JSON、```json 代码块，或使用调试台导入 JSON 文件。"
        ]
        if decode_errors:
            errors.append(decode_errors[0])
        if self._looks_encoding_damaged(text):
            errors.append("检测到疑似编码损坏字符，建议直接用调试台导入 UTF-8 JSON 文件。")
        return None, errors

    def _json_candidates(self, text: str) -> list[str]:
        blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        candidates = [b.strip() for b in blocks if b.strip()]
        if text.startswith("{") and text.endswith("}"):
            candidates.append(text)
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last > first:
            candidates.append(text[first:last + 1])
        return unique_strs(candidates)

    def _decode_error(self, candidate: str, exc: json.JSONDecodeError) -> str:
        lines = candidate.splitlines()
        line = lines[exc.lineno - 1] if 0 <= exc.lineno - 1 < len(lines) else ""
        start = max(exc.colno - 40, 0)
        end = exc.colno + 80
        snippet = line[start:end].strip()
        return f"JSON 语法错误：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}。附近：{snippet}"

    def _looks_encoding_damaged(self, text: str) -> bool:
        return "\ufffd" in text or any(marker in text for marker in ["鏋", "鐨", "鍚", "绯", "€"])


class PlanNormalizer:
    """Normalizes partially valid model output into the minimum plan shape."""

    def normalize(self, plan: dict[str, Any] | None) -> dict[str, Any]:
        source = plan if isinstance(plan, dict) else {}
        tasks = source.get("tasks")
        normalized_tasks = [
            self._task(t, i) for i, t in enumerate(tasks if isinstance(tasks, list) else [])
            if isinstance(t, dict)
        ]
        strategy = source.get("execution_strategy")
        return {
            "plan_id": str(source.get("plan_id") or "plan_001"),
            "status": str(source.get("status") or "draft"),
            "execution_policy": str(source.get("execution_policy") or "manual_approval_required"),
            "tasks": normalized_tasks,
            "execution_strategy": self._strategy(strategy, normalized_tasks),
        }

    def _task(self, task: dict[str, Any], index: int) -> dict[str, Any]:
        task_id = str(task.get("task_id") or f"T{index + 1}")
        return {
            "task_id": task_id,
            "title": str(task.get("title") or task_id),
            "goal": str(task.get("goal") or ""),
            "required_skills": as_str_list(task.get("required_skills")),
            "assigned_agent_id": none_or_str(task.get("assigned_agent_id")),
            "assigned_agent_name": none_or_str(task.get("assigned_agent_name")),
            "assignment_reason": str(task.get("assignment_reason") or ""),
            "depends_on": as_str_list(task.get("depends_on")),
            "expected_outputs": as_str_list(task.get("expected_outputs")),
            "acceptance_criteria": as_str_list(task.get("acceptance_criteria")),
            "needs_approval": bool(task.get("needs_approval", False)),
            "is_blocking": bool(task.get("is_blocking", False)),
        }

    def _strategy(self, strategy: Any, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(strategy, dict):
            return {
                "summary": "按 DAG 依赖顺序执行。",
                "phases": self._default_phases(tasks),
            }
        phases = strategy.get("phases")
        return {
            "summary": str(strategy.get("summary") or "按 DAG 依赖顺序执行。"),
            "phases": [self._phase(p) for p in phases if isinstance(p, dict)]
            if isinstance(phases, list) else self._default_phases(tasks),
        }

    def _phase(self, phase: dict[str, Any]) -> dict[str, Any]:
        mode = phase.get("mode")
        return {
            "phase": int(phase.get("phase") or 1),
            "mode": mode if mode in {"serial", "parallel"} else "serial",
            "tasks": as_str_list(phase.get("tasks")),
            "reason": str(phase.get("reason") or ""),
        }

    def _default_phases(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not tasks:
            return []
        return [{
            "phase": 1,
            "mode": "serial",
            "tasks": [t["task_id"] for t in tasks],
            "reason": "调度器未提供 execution_strategy，按任务列表顺序展示。",
        }]


class PlanValidator:
    """Validates DAG structure and returns content warnings."""

    def validate(self, plan: dict[str, Any], candidate_agents: list[dict[str, Any]]) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        tasks = plan.get("tasks") if isinstance(plan.get("tasks"), list) else []
        ids = [str(t.get("task_id")) for t in tasks if isinstance(t, dict)]

        if not tasks:
            errors.append("tasks 不能为空")

        duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
        for task_id in duplicates:
            errors.append(f"task_id 重复: {task_id}")

        id_set = set(ids)
        for task in tasks:
            task_id = str(task.get("task_id"))
            for dep in as_str_list(task.get("depends_on")):
                if dep not in id_set:
                    errors.append(f"{task_id}.depends_on 引用了不存在的任务: {dep}")

        if tasks and not any(not as_str_list(t.get("depends_on")) for t in tasks):
            errors.append("DAG 至少需要一个无依赖的起点任务")

        cycle = self._find_cycle(tasks)
        if cycle:
            errors.append(f"DAG 存在循环依赖: {' -> '.join(cycle)}")

        agent_ids = {a.get("id") for a in candidate_agents}
        for task in tasks:
            task_id = str(task.get("task_id"))
            assigned = task.get("assigned_agent_id")
            if assigned and assigned not in agent_ids:
                warnings.append(f"{task_id}.assigned_agent_id 不在候选 Agent 中: {assigned}")
            if not task.get("required_skills"):
                warnings.append(f"{task_id}.required_skills 为空")
            if not task.get("acceptance_criteria"):
                warnings.append(f"{task_id}.acceptance_criteria 为空")

        return {"ok": not errors, "errors": errors, "warnings": warnings}

    def _find_cycle(self, tasks: list[dict[str, Any]]) -> list[str]:
        graph = {str(t.get("task_id")): as_str_list(t.get("depends_on")) for t in tasks}
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


class PlanVisualizer:
    """Produces a Mermaid diagram from a normalized plan."""

    def mermaid(self, plan: dict[str, Any]) -> str:
        tasks = plan.get("tasks") if isinstance(plan.get("tasks"), list) else []
        if not tasks:
            return "flowchart LR\n  empty[No tasks]"

        lines = ["flowchart LR"]
        by_id = {t["task_id"]: t for t in tasks}
        for task in tasks:
            node_id = node(task["task_id"])
            label = f"{task['task_id']} · {task['title']}\\n@{task.get('assigned_agent_name') or '未分配'}"
            lines.append(f"  {node_id}[\"{label}\"]")
        for task in tasks:
            for dep in task.get("depends_on", []):
                if dep in by_id:
                    lines.append(f"  {node(dep)} --> {node(task['task_id'])}")

        for phase in plan.get("execution_strategy", {}).get("phases", []):
            ids = [task_id for task_id in phase.get("tasks", []) if task_id in by_id]
            if not ids:
                continue
            lines.append(f"  subgraph phase_{phase.get('phase')}[Phase {phase.get('phase')} · {phase.get('mode')}]")
            for task_id in ids:
                lines.append(f"    {node(task_id)}")
            lines.append("  end")
        return "\n".join(lines)


class OrchestratorPlanBridge:
    """Facade for manual Orchestrator bridge operations."""

    def __init__(self):
        self.input_builder = OrchestratorInputBuilder()
        self.parser = PlanParser()
        self.normalizer = PlanNormalizer()
        self.validator = PlanValidator()
        self.visualizer = PlanVisualizer()

    def build_input(self, content: str, agents: list[AgentConfig]) -> dict[str, Any]:
        return self.input_builder.build(OrchestratorBridgeRequest(content=content, agents=agents))

    def parse_output(self, raw_output: str, candidate_agents: list[dict[str, Any]]) -> dict[str, Any]:
        parsed, parse_errors = self.parser.parse(raw_output)
        normalized = self.normalizer.normalize(parsed)
        validation = self.validator.validate(normalized, candidate_agents)
        validation["errors"] = parse_errors + validation["errors"]
        validation["ok"] = validation["ok"] and not parse_errors
        return {
            "rawOutput": raw_output,
            "normalizedPlan": normalized,
            "validation": validation,
            "visualization": {
                "mermaid": self.visualizer.mermaid(normalized),
            },
        }


def agent_payload(agent: AgentConfig) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "provider": agent.provider,
        "model": agent.model,
        "primarySkill": infer_primary_skill(agent),
        "auxiliarySkills": infer_auxiliary_skills(agent),
    }


def infer_primary_skill(agent: AgentConfig) -> str:
    text = f"{agent.name} {agent.description} {agent.system_prompt}".lower()
    if any(k in text for k in ["前端", "react", "ui", "组件"]):
        return "frontend_engineer"
    if any(k in text for k in ["后端", "api", "fastapi", "数据库"]):
        return "backend_engineer"
    if any(k in text for k in ["审查", "测试", "安全"]):
        return "reviewer"
    if any(k in text for k in ["调研", "研究", "分析"]):
        return "researcher"
    return "architecture"


def infer_auxiliary_skills(agent: AgentConfig) -> list[str]:
    text = f"{agent.name} {agent.description} {agent.system_prompt}".lower()
    skills = []
    keyword_map = [
        ("react", "react"),
        ("typescript", "typescript"),
        ("fastapi", "fastapi"),
        ("数据库", "database"),
        ("api", "api_design"),
        ("安全", "security_review"),
        ("测试", "testing"),
        ("架构", "architecture"),
    ]
    for keyword, skill in keyword_map:
        if keyword in text and skill not in skills:
            skills.append(skill)
    return skills


def as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def unique_strs(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def none_or_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def node(task_id: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in task_id)
    return f"task_{safe}"
