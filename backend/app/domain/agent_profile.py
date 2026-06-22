"""Pure domain view of an agent profile used by orchestration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfileSnapshot:
    """Agent metadata required by domain planning and execution handoff.

    This object deliberately has no ORM or framework behavior. Application and
    infrastructure code convert persistence records into this snapshot before
    passing agents into the domain orchestration pipeline.
    """

    id: str
    name: str
    description: str = ""
    system_prompt: str = ""
    rules: str = ""
    agent_type: str = "cli_wrapper"
    cli_tool: str = "custom"
    executable: str = ""
    init_args: str = "[]"
    env_vars: str = "{}"
    primary_skill: str = "general_coding"
    auxiliary_skills: str = "[]"
    toolset: str = "[]"
    context_policy: str = "workspace_coding"
    avatar: str = ""
    is_active: bool = True
    prepared_invocation: bool = False
    close_stdin_after_prompt: bool = False
