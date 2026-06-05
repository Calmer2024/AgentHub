"""Seed built-in CLI agents."""

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.cli_defaults import DEFAULT_CLI_AGENTS
from ..core.agent_env import allowed_sensitive_env_keys_for_cli, encode_cli_agent_env
from ..models import AgentConfig
from .cli_agent_registry import decode_json_dict


LEGACY_CLI_DEFAULT_ARGS = {
    "claude_code": [
        "-p",
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        "--dangerously-skip-permissions",
    ],
    "codex": [
        "exec",
        "--ask-for-approval",
        "never",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--color",
        "never",
        "--json",
        "-",
    ],
    "codex_misordered_approval": [
        "--ask-for-approval",
        "never",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--color",
        "never",
        "--json",
    ],
    "codex_user_config": [
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--dangerously-bypass-approvals-and-sandbox",
        "--color",
        "never",
        "--json",
        "-",
    ],
    "codex_ignore_user_config": [
        "exec",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--dangerously-bypass-approvals-and-sandbox",
        "--color",
        "never",
        "--json",
        "-",
    ],
    "opencode": ["--no-color", "--plain"],
    "opencode_run_json_without_permissions": ["run", "--format", "json"],
    "opencode_run_json": [
        "run",
        "--format",
        "json",
        "--dangerously-skip-permissions",
    ],
}


async def seed_default_cli_agents(db: AsyncSession) -> None:
    await archive_non_cli_agents(db)
    defaults_by_tool: dict[str, AgentConfig] = {}
    for cli_tool, defaults in DEFAULT_CLI_AGENTS.items():
        result = await db.execute(
            select(AgentConfig).where(AgentConfig.cli_tool == cli_tool).limit(1)
        )
        existing = result.scalars().first()
        if existing:
            _upgrade_legacy_defaults(existing, cli_tool, defaults)
            existing.agent_type = "cli_wrapper"
            existing.env_vars = _clean_env_vars(existing.env_vars, cli_tool)
            _ensure_skill_profile(existing)
            defaults_by_tool[cli_tool] = existing
            continue
        agent = AgentConfig(
            id=str(uuid.uuid4()),
            name=defaults["name"],
            description=defaults["description"],
            system_prompt="",
            agent_type="cli_wrapper",
            cli_tool=cli_tool,
            executable=defaults["executable"],
            init_args=json.dumps(defaults["init_args"], ensure_ascii=False),
            env_vars=encode_cli_agent_env(
                defaults["env_vars"],
                allowed_sensitive_keys=allowed_sensitive_env_keys_for_cli(cli_tool),
            ),
            primary_skill="general_coding",
            auxiliary_skills=json.dumps(["workspace_editing"], ensure_ascii=False),
            context_policy="workspace_coding",
        )
        db.add(agent)
        defaults_by_tool[cli_tool] = agent
    await _ensure_orchestrator_agent(db, defaults_by_tool)
    await db.commit()


async def archive_non_cli_agents(db: AsyncSession) -> None:
    """Hide non-CLI records from the CLI friends list."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.is_active == True))
    default_tools = set(DEFAULT_CLI_AGENTS)
    default_names = {item["name"] for item in DEFAULT_CLI_AGENTS.values()}
    for agent in result.scalars().all():
        agent.env_vars = _clean_env_vars(agent.env_vars, agent.cli_tool)
        _ensure_skill_profile(agent)
        if (agent.agent_type or "cli_wrapper") != "cli_wrapper":
            agent.is_active = False
            continue
        if agent.cli_tool in default_tools:
            continue
        if agent.executable:
            continue
        if agent.name not in default_names:
            agent.is_active = False


def _upgrade_legacy_defaults(agent: AgentConfig, cli_tool: str, defaults: dict) -> None:
    legacy_args = LEGACY_CLI_DEFAULT_ARGS.get(cli_tool)
    current_args = _json_list(agent.init_args)
    legacy_candidates = [legacy_args] if legacy_args is not None else []
    if cli_tool == "opencode":
        legacy_candidates.append(LEGACY_CLI_DEFAULT_ARGS["opencode_run_json_without_permissions"])
        legacy_candidates.append(LEGACY_CLI_DEFAULT_ARGS["opencode_run_json"])
    if current_args in legacy_candidates:
        agent.init_args = json.dumps(defaults["init_args"], ensure_ascii=False)
    if cli_tool == "codex" and _json_list(agent.init_args) in (
        LEGACY_CLI_DEFAULT_ARGS["codex_user_config"],
        LEGACY_CLI_DEFAULT_ARGS["codex_misordered_approval"],
        LEGACY_CLI_DEFAULT_ARGS["codex_ignore_user_config"],
    ):
        agent.init_args = json.dumps(defaults["init_args"], ensure_ascii=False)
    if not agent.executable:
        agent.executable = defaults["executable"]
    if decode_json_dict(agent.env_vars, cli_tool=cli_tool) == {} and defaults["env_vars"]:
        agent.env_vars = json.dumps(defaults["env_vars"], ensure_ascii=False)


def _clean_env_vars(raw: str | None, cli_tool: str | None) -> str:
    return encode_cli_agent_env(
        decode_json_dict(raw, cli_tool=cli_tool),
        allowed_sensitive_keys=allowed_sensitive_env_keys_for_cli(cli_tool),
    )


def _ensure_skill_profile(agent: AgentConfig) -> None:
    if not getattr(agent, "primary_skill", None):
        agent.primary_skill = "general_coding"
    if not getattr(agent, "auxiliary_skills", None):
        agent.auxiliary_skills = json.dumps(["workspace_editing"], ensure_ascii=False)
    if not getattr(agent, "context_policy", None):
        agent.context_policy = "workspace_coding"


async def _ensure_orchestrator_agent(
    db: AsyncSession,
    defaults_by_tool: dict[str, AgentConfig],
) -> None:
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.primary_skill == "orchestrator_planner",
            AgentConfig.is_active == True,
        ).limit(1)
    )
    existing = result.scalars().first()
    if existing:
        existing.name = existing.name or "Orchestrator 调度器"
        existing.description = existing.description or "负责需求拆解、DAG 计划和 Agent 分配建议。"
        existing.context_policy = "planning_only"
        return

    base = (
        defaults_by_tool.get("claude_code")
        or defaults_by_tool.get("codex")
        or defaults_by_tool.get("opencode")
    )
    defaults = DEFAULT_CLI_AGENTS.get(base.cli_tool if base else "claude_code", DEFAULT_CLI_AGENTS["claude_code"])
    db.add(AgentConfig(
        id=str(uuid.uuid4()),
        name="Orchestrator 调度器",
        description="负责需求拆解、DAG 计划和 Agent 分配建议；只输出计划，不直接执行子任务。",
        system_prompt="",
        agent_type="cli_wrapper",
        cli_tool=base.cli_tool if base else "claude_code",
        executable=base.executable if base else defaults["executable"],
        init_args=base.init_args if base else json.dumps(defaults["init_args"], ensure_ascii=False),
        env_vars=base.env_vars if base else encode_cli_agent_env(
            defaults["env_vars"],
            allowed_sensitive_keys=allowed_sensitive_env_keys_for_cli("claude_code"),
        ),
        primary_skill="orchestrator_planner",
        auxiliary_skills=json.dumps(["architect"], ensure_ascii=False),
        context_policy="planning_only",
    ))


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
