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
            rules="",
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
    await _ensure_lifecycle_agents(db, defaults_by_tool)
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
        existing.system_prompt = _orchestrator_system_prompt()
        existing.rules = _orchestrator_rules()
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
        system_prompt=_orchestrator_system_prompt(),
        rules=_orchestrator_rules(),
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


LIFECYCLE_AGENT_SPECS = [
    {
        "name": "产品经理",
        "description": "负责业务目标、角色权限、需求范围、优先级和验收标准。",
        "primary_skill": "product_manager",
        "auxiliary_skills": ["requirements_analyst", "technical_writer"],
        "context_policy": "planning_only",
        "preferred_tool": "claude_code",
    },
    {
        "name": "需求分析师",
        "description": "负责需求澄清、业务规则、异常流程、权限矩阵和用例。",
        "primary_skill": "requirements_analyst",
        "auxiliary_skills": ["product_manager", "technical_writer"],
        "context_policy": "planning_only",
        "preferred_tool": "claude_code",
    },
    {
        "name": "架构师",
        "description": "负责系统边界、技术方案、模块划分、数据模型和接口契约。",
        "primary_skill": "architect",
        "auxiliary_skills": ["api_designer", "database_designer", "technical_writer"],
        "context_policy": "workspace_coding",
        "preferred_tool": "claude_code",
    },
    {
        "name": "后端专家",
        "description": "负责服务端 API、数据库访问、业务逻辑、权限和后端测试。",
        "primary_skill": "backend_engineer",
        "auxiliary_skills": ["api_designer", "database_designer", "workspace_editing"],
        "context_policy": "workspace_coding",
        "preferred_tool": "codex",
    },
    {
        "name": "前端专家",
        "description": "负责前端页面、组件、交互、状态管理和 Web 预览。",
        "primary_skill": "frontend_engineer",
        "auxiliary_skills": ["ux_designer", "web_preview", "workspace_editing"],
        "context_policy": "workspace_coding",
        "preferred_tool": "claude_code",
    },
    {
        "name": "测试专家",
        "description": "负责测试策略、测试用例、集成测试、回归风险和验收报告。",
        "primary_skill": "test_engineer",
        "auxiliary_skills": ["code_reviewer", "technical_writer"],
        "context_policy": "review_only",
        "preferred_tool": "codex",
    },
    {
        "name": "文档专家",
        "description": "负责 PRD、架构说明、接口文档、用户指南和交接文档。",
        "primary_skill": "technical_writer",
        "auxiliary_skills": ["product_manager", "architect"],
        "context_policy": "planning_only",
        "preferred_tool": "claude_code",
    },
]

BUILTIN_ROLE_AGENT_NAMES = [
    "Orchestrator 调度器",
    *[str(spec["name"]) for spec in LIFECYCLE_AGENT_SPECS],
]


async def _ensure_lifecycle_agents(
    db: AsyncSession,
    defaults_by_tool: dict[str, AgentConfig],
) -> None:
    for spec in LIFECYCLE_AGENT_SPECS:
        result = await db.execute(
            select(AgentConfig).where(
                AgentConfig.primary_skill == spec["primary_skill"],
                AgentConfig.name == spec["name"],
                AgentConfig.is_active == True,
            ).limit(1)
        )
        existing = result.scalars().first()
        if existing:
            existing.description = spec["description"]
            existing.system_prompt = _lifecycle_system_prompt(spec["name"])
            existing.rules = _lifecycle_rules()
            existing.auxiliary_skills = json.dumps(spec["auxiliary_skills"], ensure_ascii=False)
            existing.context_policy = spec["context_policy"]
            _ensure_engine_defaults(existing, defaults_by_tool, spec["preferred_tool"])
            continue

        base = _preferred_engine(defaults_by_tool, spec["preferred_tool"])
        db.add(AgentConfig(
            id=str(uuid.uuid4()),
            name=spec["name"],
            description=spec["description"],
            system_prompt=_lifecycle_system_prompt(spec["name"]),
            rules=_lifecycle_rules(),
            agent_type="cli_wrapper",
            cli_tool=base.cli_tool,
            executable=base.executable,
            init_args=base.init_args,
            env_vars=base.env_vars,
            primary_skill=spec["primary_skill"],
            auxiliary_skills=json.dumps(spec["auxiliary_skills"], ensure_ascii=False),
            context_policy=spec["context_policy"],
        ))


async def configure_builtin_role_agents_as_codex(db: AsyncSession) -> int:
    """把内置角色 Agent 统一切到 Codex 引擎，保留角色技能配置。"""
    await seed_default_cli_agents(db)
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.name.in_(BUILTIN_ROLE_AGENT_NAMES),
            AgentConfig.is_active == True,
        )
    )
    codex_defaults = DEFAULT_CLI_AGENTS["codex"]
    updated = 0
    for agent in result.scalars().all():
        agent.agent_type = "cli_wrapper"
        agent.cli_tool = "codex"
        agent.executable = codex_defaults["executable"]
        agent.init_args = json.dumps(codex_defaults["init_args"], ensure_ascii=False)
        agent.env_vars = encode_cli_agent_env(
            codex_defaults["env_vars"],
            allowed_sensitive_keys=allowed_sensitive_env_keys_for_cli("codex"),
        )
        _ensure_skill_profile(agent)
        updated += 1
    await db.commit()
    return updated


def _preferred_engine(
    defaults_by_tool: dict[str, AgentConfig],
    preferred_tool: str,
) -> AgentConfig:
    return (
        defaults_by_tool.get(preferred_tool)
        or defaults_by_tool.get("claude_code")
        or defaults_by_tool.get("codex")
        or defaults_by_tool.get("opencode")
        or _fallback_engine()
    )


def _ensure_engine_defaults(
    agent: AgentConfig,
    defaults_by_tool: dict[str, AgentConfig],
    preferred_tool: str,
) -> None:
    base = _preferred_engine(defaults_by_tool, preferred_tool)
    if not agent.cli_tool or agent.cli_tool == "custom":
        agent.cli_tool = base.cli_tool
    if not agent.executable:
        agent.executable = base.executable
    if not agent.init_args:
        agent.init_args = base.init_args
    if not agent.env_vars:
        agent.env_vars = base.env_vars
    if not agent.system_prompt:
        agent.system_prompt = _lifecycle_system_prompt(agent.name)
    if getattr(agent, "rules", None) is None:
        agent.rules = ""


def _fallback_engine() -> AgentConfig:
    defaults = DEFAULT_CLI_AGENTS["claude_code"]
    return AgentConfig(
        id="fallback-engine",
        name=defaults["name"],
        description=defaults["description"],
        system_prompt="",
        rules="",
        agent_type="cli_wrapper",
        cli_tool="claude_code",
        executable=defaults["executable"],
        init_args=json.dumps(defaults["init_args"], ensure_ascii=False),
        env_vars=encode_cli_agent_env(
            defaults["env_vars"],
            allowed_sensitive_keys=allowed_sensitive_env_keys_for_cli("claude_code"),
        ),
        primary_skill="general_coding",
        auxiliary_skills="[]",
        context_policy="workspace_coding",
    )


def _lifecycle_system_prompt(agent_name: str) -> str:
    return (
        f"你是 AgentHub 默认产品生命周期小队中的「{agent_name}」。"
        "不要宣称自己只是底层 CLI Engine；当用户询问身份时，回答这个 Agent 身份。"
    )


def _lifecycle_rules() -> str:
    return (
        "请严格按当前 Agent Profile 的主 Skill 与辅助 Skills 工作。"
        "输出语言默认跟随用户需求与上游交接语言；中文需求下，文档、交接说明、UI 文案和必要注释都使用中文。"
        "用户要的正式项目文档、代码、配置和测试应沉淀到项目 workspace；"
        "任务工作包只保存草稿、过程笔记和下游交接副本。"
    )


def _orchestrator_system_prompt() -> str:
    return (
        "你是 AgentHub 群聊中的 Orchestrator 调度器。用户没有 @ 任何成员时，"
        "这条消息默认先交给你判断。你负责计划、分流和调度建议，不直接执行子任务。"
    )


def _orchestrator_rules() -> str:
    return (
        "你只输出调用方要求的 JSON，不直接修改文件、不执行子任务。"
        "当调用方要求 steward routing 时，输出 route_type/reply/selected_agent_ids 等决策 JSON；"
        "当用户明确 @ 你生成计划或跟进计划时，输出符合 orchestrator_planner skill 契约的 draft plan JSON。"
        "任务交付物只描述类型、目录层级或建议位置，除非用户明确指定，不要强制精确文件名。"
        "当用户要求正式项目文档时，计划应建议写入项目 docs/，不要把任务工作包当成最终交付目录。"
        "输出语言默认跟随用户需求；中文需求下，计划标题、目标、验收标准和交接要求都用中文。"
    )


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
