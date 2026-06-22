"""Map persistence agent records into pure domain agent profiles."""

from __future__ import annotations

from collections.abc import Iterable

from ..domain.agent_profile import AgentProfileSnapshot
from ..models import AgentConfig


def agent_profile_from_model(agent: AgentConfig) -> AgentProfileSnapshot:
    """Create a domain snapshot from an ORM AgentConfig record."""
    return AgentProfileSnapshot(
        id=str(agent.id),
        name=str(agent.name or ""),
        description=str(agent.description or ""),
        system_prompt=str(agent.system_prompt or ""),
        rules=str(getattr(agent, "rules", "") or ""),
        agent_type=str(agent.agent_type or "cli_wrapper"),
        cli_tool=str(agent.cli_tool or "custom"),
        executable=str(agent.executable or ""),
        init_args=str(agent.init_args or "[]"),
        env_vars=str(agent.env_vars or "{}"),
        primary_skill=str(agent.primary_skill or "general_coding"),
        auxiliary_skills=str(agent.auxiliary_skills or "[]"),
        toolset=str(agent.toolset or "[]"),
        context_policy=str(agent.context_policy or "workspace_coding"),
        avatar=str(getattr(agent, "avatar", "") or ""),
        is_active=bool(getattr(agent, "is_active", True)),
        prepared_invocation=bool(getattr(agent, "prepared_invocation", False)),
        close_stdin_after_prompt=bool(getattr(agent, "close_stdin_after_prompt", False)),
    )


def agent_profiles_from_models(
    agents: Iterable[AgentConfig],
) -> list[AgentProfileSnapshot]:
    return [agent_profile_from_model(agent) for agent in agents]
