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
    await _seed_default_cli_agents(db, owner_user_id=None)


async def ensure_user_default_cli_agents(db: AsyncSession, owner_user_id: str) -> None:
    await _seed_default_cli_agents(db, owner_user_id=owner_user_id)


async def _seed_default_cli_agents(db: AsyncSession, owner_user_id: str | None) -> None:
    await archive_non_cli_agents(db, owner_user_id=owner_user_id)
    defaults_by_tool: dict[str, AgentConfig] = {}
    for cli_tool, defaults in DEFAULT_CLI_AGENTS.items():
        result = await db.execute(
            select(AgentConfig).where(
                _owner_filter(owner_user_id),
                AgentConfig.cli_tool == cli_tool,
                AgentConfig.name == defaults["name"],
            ).limit(1)
        )
        existing = result.scalars().first()
        if existing:
            _upgrade_legacy_defaults(existing, cli_tool, defaults)
            existing.agent_type = "cli_wrapper"
            existing.is_builtin = True
            existing.env_vars = _clean_env_vars(existing.env_vars, cli_tool)
            _ensure_skill_profile(existing)
            defaults_by_tool[cli_tool] = existing
            continue
        agent = AgentConfig(
            id=str(uuid.uuid4()),
            owner_user_id=owner_user_id,
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
            auxiliary_skills="[]",
            toolset="[]",
            context_policy="workspace_coding",
            avatar="",
            is_builtin=True,
        )
        db.add(agent)
        defaults_by_tool[cli_tool] = agent
    await _ensure_orchestrator_agent(db, defaults_by_tool, owner_user_id=owner_user_id)
    await _archive_template_agents(db, owner_user_id=owner_user_id)
    await db.commit()


async def archive_non_cli_agents(db: AsyncSession, owner_user_id: str | None = None) -> None:
    """Hide non-CLI records from the CLI friends list."""
    result = await db.execute(
        select(AgentConfig).where(AgentConfig.is_active == True, _owner_filter(owner_user_id))
    )
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
    if agent.name == defaults["name"] and (getattr(agent, "avatar", "") or "") in {"", "preset:blue"}:
        agent.avatar = ""


def _clean_env_vars(raw: str | None, cli_tool: str | None) -> str:
    return encode_cli_agent_env(
        decode_json_dict(raw, cli_tool=cli_tool),
        allowed_sensitive_keys=allowed_sensitive_env_keys_for_cli(cli_tool),
    )


def _ensure_skill_profile(agent: AgentConfig) -> None:
    if not getattr(agent, "primary_skill", None):
        agent.primary_skill = "general_coding"
    if not getattr(agent, "auxiliary_skills", None):
        agent.auxiliary_skills = "[]"
    if not getattr(agent, "toolset", None):
        agent.toolset = "[]"
    if not getattr(agent, "context_policy", None):
        agent.context_policy = "workspace_coding"
    if getattr(agent, "avatar", None) is None:
        agent.avatar = ""


async def _ensure_orchestrator_agent(
    db: AsyncSession,
    defaults_by_tool: dict[str, AgentConfig],
    *,
    owner_user_id: str | None = None,
) -> None:
    result = await db.execute(
        select(AgentConfig).where(
            _owner_filter(owner_user_id),
            AgentConfig.primary_skill == "orchestrator_planner",
            AgentConfig.is_active == True,
        ).limit(1)
    )
    existing = result.scalars().first()
    if existing:
        if not existing.name or existing.name == "Orchestrator 调度器":
            existing.name = "项目Leader"
        existing.description = existing.description or "负责需求拆解、DAG 计划和 Agent 分配建议。"
        existing.system_prompt = _orchestrator_system_prompt()
        existing.rules = _orchestrator_rules()
        existing.context_policy = "planning_only"
        existing.toolset = "[]"
        existing.avatar = "preset:violet"
        _ensure_engine_defaults(existing, defaults_by_tool, "codex")
        return

    base = (
        defaults_by_tool.get("codex")
        or defaults_by_tool.get("claude_code")
        or defaults_by_tool.get("opencode")
    )
    defaults = DEFAULT_CLI_AGENTS.get(base.cli_tool if base else "codex", DEFAULT_CLI_AGENTS["codex"])
    db.add(AgentConfig(
        id=str(uuid.uuid4()),
        owner_user_id=owner_user_id,
        name="项目Leader",
        description="负责需求拆解、DAG 计划和 Agent 分配建议；只输出计划，不直接执行子任务。",
        system_prompt=_orchestrator_system_prompt(),
        rules=_orchestrator_rules(),
        agent_type="cli_wrapper",
        cli_tool=base.cli_tool if base else "claude_code",
        executable=base.executable if base else defaults["executable"],
        init_args=base.init_args if base else json.dumps(defaults["init_args"], ensure_ascii=False),
        env_vars=base.env_vars if base else encode_cli_agent_env(
            defaults["env_vars"],
            allowed_sensitive_keys=allowed_sensitive_env_keys_for_cli("codex"),
        ),
        primary_skill="orchestrator_planner",
        auxiliary_skills="[]",
        toolset="[]",
        context_policy="planning_only",
        avatar="preset:violet",
    ))


LIFECYCLE_AGENT_SPECS = [
    {
        "name": "产品经理",
        "aliases": [],
        "description": "负责产品目标、用户场景、范围边界、优先级、验收标准和发布取舍。",
        "primary_skill": "product_manager",
        "toolset": ["product_strategy", "scope_control", "acceptance_criteria"],
        "context_policy": "planning_only",
        "avatar": "preset:rose",
        "system_prompt": (
            "你是 AgentHub 内置模板「产品经理」。你的职责是把模糊需求收敛为清晰、"
            "可验收、可分工的产品定义。你关注用户、场景、约束、优先级和非目标，"
            "不代替设计师画界面、不代替工程师写实现。"
        ),
        "rules": (
            "输出先说明目标和范围，再给用户故事、业务规则、验收标准和风险。"
            "遇到实现细节争议时只定义产品口径，把技术方案交给系统架构师或对应工程师。"
            "中文需求下使用中文，避免把未确认假设写成已确定结论。"
        ),
    },
    {
        "name": "UX/UI设计师",
        "aliases": [],
        "description": "负责信息架构、任务流、界面布局、交互反馈、视觉一致性和可用性验收。",
        "primary_skill": "ux_ui_designer",
        "toolset": ["interaction_flow", "visual_system", "ux_state_coverage"],
        "context_policy": "planning_only",
        "avatar": "preset:violet",
        "system_prompt": (
            "你是 AgentHub 内置模板「UX/UI设计师」。你的职责是把产品目标转化为"
            "清晰的信息架构、任务流、界面结构、交互状态和视觉规范。你关注用户是否"
            "知道当前系统在做什么、自己能做什么、下一步会发生什么。"
        ),
        "rules": (
            "输出必须覆盖空、加载、正常、完成、错误、边界六类体验状态。"
            "设计建议要能被前端工程师直接实现，避免只给抽象审美词。"
            "不代写业务 API 和数据库方案；需要实现时交给前端工程师。"
        ),
    },
    {
        "name": "测试工程师",
        "aliases": ["测试专家"],
        "description": "负责测试策略、风险建模、用例设计、自动化验证、回归检查和验收报告。",
        "primary_skill": "test_engineer",
        "toolset": ["risk_based_testing", "api_regression", "frontend_ux_testing"],
        "context_policy": "review_only",
        "avatar": "preset:green",
        "system_prompt": (
            "你是 AgentHub 内置模板「测试工程师」。你的职责是证明系统是否真的正确，"
            "并主动寻找同类问题、边界条件和回归风险。"
        ),
        "rules": (
            "输出优先给风险路径、测试矩阵、自动化命令和验收结论。"
            "发现问题时描述可复现步骤、预期、实际和影响面。"
            "不要把测试通过等同于人工体验通过；UI 相关任务必须覆盖 UX 状态。"
        ),
    },
    {
        "name": "前端工程师",
        "aliases": ["前端专家"],
        "description": "负责 React 组件、状态管理、界面实现、交互细节、响应式布局和浏览器验证。",
        "primary_skill": "frontend_engineer",
        "toolset": ["react_typescript", "state_management", "responsive_ui"],
        "context_policy": "workspace_coding",
        "avatar": "preset:blue",
        "system_prompt": (
            "你是 AgentHub 内置模板「前端工程师」。你的职责是把产品与设计方案落实为"
            "可维护的 React/TypeScript 前端实现，保持交互、状态、样式和可访问性一致。"
        ),
        "rules": (
            "优先遵循现有组件、状态管理和样式系统。所有用户操作必须有反馈，"
            "所有固定格式控件必须有稳定尺寸，移动端和桌面端都不能出现文字溢出或重叠。"
            "不擅自改后端契约；需要接口变更时先说明字段和状态。"
        ),
    },
    {
        "name": "后端工程师",
        "aliases": ["后端专家"],
        "description": "负责 API 路由、业务服务、权限边界、数据校验、异步流程和后端集成测试。",
        "primary_skill": "backend_engineer",
        "toolset": ["fastapi_service", "domain_logic", "integration_testing"],
        "context_policy": "workspace_coding",
        "avatar": "preset:amber",
        "system_prompt": (
            "你是 AgentHub 内置模板「后端工程师」。你的职责是实现稳定、可测试、"
            "符合分层边界的服务端能力，保证 API 契约、错误状态和持久化行为可靠。"
        ),
        "rules": (
            "先明确请求/响应和异常状态，再写 Service 和路由。保持 async 代码一致，"
            "Pydantic 字段与前端 camelCase 对齐。不要用临时 hack 绕过数据库、权限或输入校验。"
        ),
    },
    {
        "name": "数据库工程师",
        "aliases": [],
        "description": "负责数据模型、迁移脚本、索引约束、数据一致性、回滚策略和查询性能。",
        "primary_skill": "database_engineer",
        "toolset": ["schema_design", "migration_safety", "query_integrity"],
        "context_policy": "workspace_coding",
        "avatar": "preset:slate",
        "system_prompt": (
            "你是 AgentHub 内置模板「数据库工程师」。你的职责是把业务状态转化为"
            "清晰可靠的数据结构、迁移策略、约束、索引和一致性规则。"
        ),
        "rules": (
            "所有结构变更都必须考虑旧数据、幂等迁移、默认值、查询路径和测试覆盖。"
            "不要把业务校验全部塞进数据库，也不要忽略数据库能自然保证的不变量。"
        ),
    },
    {
        "name": "系统架构师",
        "aliases": ["架构师"],
        "description": "负责系统边界、模块拆分、接口契约、技术取舍、演进路径和跨端一致性。",
        "primary_skill": "architect",
        "toolset": ["system_boundary", "contract_design", "architecture_decision"],
        "context_policy": "planning_only",
        "avatar": "preset:blue",
        "system_prompt": (
            "你是 AgentHub 内置模板「系统架构师」。你的职责是定义系统边界、模块关系、"
            "接口契约、数据流、风险和演进路径，让后续工程实现有清晰跑道。"
        ),
        "rules": (
            "输出要解释为什么现在这样设计、替代方案是什么、会影响哪些模块。"
            "只在需要验证架构假设时建议小型实现，不代替前端、后端或数据库工程师完成全部代码。"
        ),
    },
]

RETIRED_BUILTIN_ROLE_AGENT_NAMES = ["需求分析师", "文档专家"]

BUILTIN_ROLE_AGENT_NAMES = [
    "项目Leader",
    *[str(spec["name"]) for spec in LIFECYCLE_AGENT_SPECS],
]


async def _ensure_lifecycle_agents(
    db: AsyncSession,
    defaults_by_tool: dict[str, AgentConfig],
) -> None:
    """兼容旧调用：不再把专家模板写入好友列表。"""
    await _archive_template_agents(db)
    return


async def _archive_template_agents(db: AsyncSession, owner_user_id: str | None = None) -> None:
    """隐藏旧版本自动 seed 到好友列表里的专家模板。"""
    await _archive_retired_builtin_roles(db, owner_user_id=owner_user_id)
    for spec in LIFECYCLE_AGENT_SPECS:
        names = [str(spec["name"]), *[str(name) for name in spec.get("aliases", [])]]
        result = await db.execute(
            select(AgentConfig).where(
                _owner_filter(owner_user_id),
                AgentConfig.name.in_(names),
                AgentConfig.primary_skill == str(spec["primary_skill"]),
                AgentConfig.is_active == True,
            )
        )
        for existing in result.scalars().all():
            existing.is_active = False


async def _archive_retired_builtin_roles(db: AsyncSession, owner_user_id: str | None = None) -> None:
    result = await db.execute(
        select(AgentConfig).where(
            _owner_filter(owner_user_id),
            AgentConfig.name.in_(RETIRED_BUILTIN_ROLE_AGENT_NAMES),
            AgentConfig.is_active == True,
        )
    )
    for agent in result.scalars().all():
        agent.is_active = False


async def configure_builtin_role_agents_as_codex(db: AsyncSession, owner_user_id: str | None = None) -> int:
    """把内置模板 Agent 统一切到 Codex 引擎，保留身份与工具集配置。"""
    await _seed_default_cli_agents(db, owner_user_id=owner_user_id)
    result = await db.execute(
        select(AgentConfig).where(
            _owner_filter(owner_user_id),
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
    agent.cli_tool = base.cli_tool
    agent.executable = base.executable
    agent.init_args = base.init_args
    agent.env_vars = base.env_vars
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
        toolset="[]",
        context_policy="workspace_coding",
        avatar="",
    )


def _orchestrator_system_prompt() -> str:
    return (
        "你是 AgentHub 群聊中的项目Leader。用户没有 @ 任何成员时，"
        "这条消息默认先交给你判断。你负责计划、分流和调度建议，不直接执行子任务。"
    )


def _orchestrator_rules() -> str:
    return (
        "你只输出调用方要求的 JSON，不直接修改文件、不执行子任务。"
        "当调用方要求 steward routing 时，输出 route_type/reply/selected_agent_ids 等决策 JSON；"
        "当用户明确 @ 你生成计划或跟进计划时，输出符合 AgentHub draft plan 契约的 JSON。"
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


def _owner_filter(owner_user_id: str | None):
    if owner_user_id is None:
        return AgentConfig.owner_user_id.is_(None)
    return AgentConfig.owner_user_id == owner_user_id
