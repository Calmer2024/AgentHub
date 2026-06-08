"""Manual Orchestrator bridge helpers.

This module keeps the debug console focused on plan-first orchestration:
build a copyable prompt, parse pasted JSON, normalize and validate the draft
plan, then render Mermaid.
"""

from __future__ import annotations

import json
from typing import Any

from ..models import AgentConfig
from ..services.cli_agent_registry import decode_json_list
from .orchestrator_plan import (
    PLAN_SCHEMA,
    build_plan_prompt,
    extract_json_object,
    normalize_plan,
    validate_plan,
    visualize_mermaid,
)


class OrchestratorPlanBridge:
    def build_input(self, content: str, agents: list[AgentConfig]) -> dict[str, Any]:
        candidates = [agent_payload(agent) for agent in agents]
        return {
            "input": {
                "content": content,
                "agentCount": len(candidates),
            },
            "orchestratorAgent": {
                "id": "manual-orchestrator",
                "name": "手动调度器",
                "engine": "manual_bridge",
                "toolset": [],
                "primarySkill": "orchestrator_planner",
                "auxiliarySkills": [],
            },
            "candidateAgents": candidates,
            "prompt": build_plan_prompt(content, candidates),
            "outputSchema": PLAN_SCHEMA,
        }

    def parse_output(self, raw_output: str, candidate_agents: list[dict[str, Any]]) -> dict[str, Any]:
        parse_errors: list[str] = []
        try:
            parsed = extract_json_object(raw_output)
        except ValueError as exc:
            parsed = {}
            parse_errors.append(str(exc))

        normalized = normalize_plan(parsed)
        validation = validate_plan(
            normalized,
            {str(agent.get("id")) for agent in candidate_agents if agent.get("id")},
        )
        validation["errors"] = parse_errors + validation["errors"]
        validation["ok"] = validation["ok"] and not parse_errors
        return {
            "rawOutput": raw_output,
            "normalizedPlan": normalized,
            "validation": validation,
            "visualization": {
                "mermaid": visualize_mermaid(normalized),
            },
        }


def agent_payload(agent: AgentConfig) -> dict[str, Any]:
    auxiliary = decode_json_list(agent.auxiliary_skills)
    toolset = decode_json_list(getattr(agent, "toolset", "[]"))
    engine = agent.cli_tool or "custom"
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description or "",
        "engine": engine,
        "provider": engine,
        "model": agent.executable or engine,
        "toolset": toolset,
        "primarySkill": agent.primary_skill or "general_coding",
        "primary_skill": agent.primary_skill or "general_coding",
        "auxiliarySkills": auxiliary,
        "auxiliary_skills": auxiliary,
        "contextPolicy": agent.context_policy or "workspace_coding",
    }


def mock_agent(
    agent_id: str,
    name: str,
    description: str,
    primary_skill: str,
    auxiliary_skills: list[str],
) -> AgentConfig:
    return AgentConfig(
        id=agent_id,
        name=name,
        description=description,
        system_prompt="",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable="debug-mock-agent",
        init_args="[]",
        env_vars="{}",
        primary_skill=primary_skill,
        auxiliary_skills=json.dumps(auxiliary_skills, ensure_ascii=False),
        toolset=json.dumps(auxiliary_skills, ensure_ascii=False),
        context_policy="planning_only",
        avatar="",
    )
