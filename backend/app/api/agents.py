from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import AgentConfig
from ..agents.cli_runtime_registry import cli_runtime_registry
from ..services.cli_agent_registry import (
    CliAgentNotFoundError,
    CliAgentRegistry,
    ExecutableStatus,
    InvalidCliAgentError,
    decode_json_dict,
    decode_json_list,
)
from ..services.agent_seed import (
    configure_builtin_role_agents_as_codex,
    ensure_user_default_cli_agents,
    seed_default_cli_agents,
)
from ..services.codex_local_config_service import (
    CodexLocalConfigError,
    CodexLocalConfigService,
)
from ..services.auth_service import AuthRequiredError, AuthService, cloud_auth_required


RUNTIME_CLI_TOOLS = {
    "claude_code": "claude",
    "codex": "codex",
    "opencode": "opencode",
}
RUNTIME_EXECUTABLE_TOOLS = {"claude", "codex", "opencode"}


async def require_agents_api_access(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    if not cloud_auth_required():
        return
    try:
        await AuthService(db).require_request_user(request)
    except AuthRequiredError:
        raise HTTPException(status_code=401, detail="请先登录后继续")


router = APIRouter(
    prefix="/agents",
    tags=["agents"],
    dependencies=[Depends(require_agents_api_access)],
)


class AgentConfigCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = Field("", alias="systemPrompt")
    rules: str = ""
    agent_type: str = Field("cli_wrapper", alias="agentType")
    cli_tool: str = Field("custom", alias="cliTool")
    executable: str | None = None
    init_args: list[str] = Field(default_factory=list, alias="initArgs")
    env_vars: dict[str, str] = Field(default_factory=dict, alias="envVars")
    toolset: list[str] = Field(default_factory=list)
    primary_skill: str = Field("general_coding", alias="primarySkill")
    auxiliary_skills: list[str] = Field(default_factory=list, alias="auxiliarySkills")
    context_policy: str = Field("workspace_coding", alias="contextPolicy")
    avatar: str = ""

    model_config = {"populate_by_name": True}


class AgentConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = Field(None, alias="systemPrompt")
    rules: str | None = None
    agent_type: str | None = Field(None, alias="agentType")
    cli_tool: str | None = Field(None, alias="cliTool")
    executable: str | None = None
    init_args: list[str] | None = Field(None, alias="initArgs")
    env_vars: dict[str, str] | None = Field(None, alias="envVars")
    toolset: list[str] | None = None
    primary_skill: str | None = Field(None, alias="primarySkill")
    auxiliary_skills: list[str] | None = Field(None, alias="auxiliarySkills")
    context_policy: str | None = Field(None, alias="contextPolicy")
    avatar: str | None = None
    is_active: bool | None = Field(None, alias="isActive")

    model_config = {"populate_by_name": True}


class AgentConfigRead(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str = Field(alias="systemPrompt")
    rules: str = ""
    agent_type: str = Field(alias="agentType")
    cli_tool: str = Field(alias="cliTool")
    executable: str | None = None
    init_args: list[str] = Field(alias="initArgs")
    env_vars: dict[str, str] = Field(alias="envVars")
    toolset: list[str] = Field(default_factory=list)
    primary_skill: str = Field(alias="primarySkill")
    auxiliary_skills: list[str] = Field(alias="auxiliarySkills")
    context_policy: str = Field(alias="contextPolicy")
    avatar: str = ""
    status: str = "not_found"
    version: str | None = None
    executable_path: str | None = Field(None, alias="executablePath")
    is_active: bool = Field(alias="isActive")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_model(cls, agent: AgentConfig):
        status = _agent_executable_status(agent)
        return cls(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            rules=getattr(agent, "rules", "") or "",
            agent_type=agent.agent_type or "cli_wrapper",
            cli_tool=agent.cli_tool or "custom",
            executable=agent.executable,
            init_args=decode_json_list(agent.init_args),
            env_vars=decode_json_dict(agent.env_vars, cli_tool=agent.cli_tool),
            toolset=decode_json_list(getattr(agent, "toolset", "[]")),
            primary_skill=agent.primary_skill or "general_coding",
            auxiliary_skills=decode_json_list(agent.auxiliary_skills),
            context_policy=agent.context_policy or "workspace_coding",
            avatar=getattr(agent, "avatar", "") or "",
            status=status.status,
            version=status.version,
            executable_path=status.executable_path,
            is_active=agent.is_active,
            created_at=agent.created_at.isoformat() if agent.created_at else "",
            updated_at=agent.updated_at.isoformat() if agent.updated_at else "",
        )


def _agent_executable_status(agent: AgentConfig) -> ExecutableStatus:
    runtime_status = _cloud_runtime_executable_status(agent)
    if runtime_status:
        return runtime_status
    return CliAgentRegistry.executable_status(agent.executable)


def _cloud_runtime_executable_status(agent: AgentConfig) -> ExecutableStatus | None:
    if not cloud_auth_required():
        return None
    if settings.agenthub_runner_provider.strip().lower() not in {"docker", "ssh_docker", "remote_docker"}:
        return None
    tool = _runtime_tool_name(agent)
    if not tool:
        return None
    images = _configured_runtime_images()
    if any(tool in image.lower() for image in images):
        return ExecutableStatus(
            status="ready",
            version=f"{tool} 由云端 Runtime Image 提供",
            executable_path=None,
        )
    return None


def _runtime_tool_name(agent: AgentConfig) -> str | None:
    cli_tool = (agent.cli_tool or "").strip().lower()
    if cli_tool in RUNTIME_CLI_TOOLS:
        return RUNTIME_CLI_TOOLS[cli_tool]
    executable = Path(agent.executable or "").name.lower()
    if executable in RUNTIME_EXECUTABLE_TOOLS:
        return executable
    return None


def _configured_runtime_images() -> list[str]:
    configured = [
        item.strip()
        for item in (settings.agenthub_runtime_images or "").split(",")
        if item.strip()
    ]
    return [item.lower() for item in (configured or [settings.agenthub_runtime_image]) if item.strip()]


class CodexLocalConfigRead(BaseModel):
    codex_home: str = Field(alias="codexHome")
    config_exists: bool = Field(alias="configExists")
    env_exists: bool = Field(alias="envExists")
    connection: str
    provider_id: str = Field(alias="providerId")
    provider_name: str = Field(alias="providerName")
    base_url: str = Field(alias="baseUrl")
    model: str
    wire_api: str = Field(alias="wireApi")
    auth_mode: str = Field(alias="authMode")
    env_key: str = Field(alias="envKey")
    api_key_set: bool = Field(alias="apiKeySet")
    api_key_source: str = Field("", alias="apiKeySource")
    has_chatgpt_auth: bool = Field(alias="hasChatgptAuth")
    needs_api_key: bool = Field(False, alias="needsApiKey")
    repair_applied: bool = Field(False, alias="repairApplied")
    ready: bool
    message: str

    model_config = {"populate_by_name": True}


class CodexLocalConfigUpdate(BaseModel):
    connection: str
    base_url: str = Field("", alias="baseUrl")
    model: str = ""
    api_key: str = Field("", alias="apiKey")
    provider_id: str = Field("", alias="providerId")
    provider_name: str = Field("", alias="providerName")
    use_chatgpt_auth: bool = Field(False, alias="useChatgptAuth")

    model_config = {"populate_by_name": True}


async def _owner_user_id_for_agents(request: Request, db: AsyncSession) -> str | None:
    if not cloud_auth_required():
        return None
    try:
        user = await AuthService(db).require_request_user(request)
    except AuthRequiredError:
        raise HTTPException(status_code=401, detail="请先登录后继续")
    await ensure_user_default_cli_agents(db, user.id)
    return user.id


def _registry(db: AsyncSession, owner_user_id: str | None = None) -> CliAgentRegistry:
    return CliAgentRegistry(db, owner_user_id=owner_user_id)


@router.get("", response_model=List[AgentConfigRead])
async def list_agents(request: Request, db: AsyncSession = Depends(get_db)):
    owner_user_id = await _owner_user_id_for_agents(request, db)
    agents = await _registry(db, owner_user_id).list_active()
    return [AgentConfigRead.from_model(agent) for agent in agents]


@router.post("/seed-defaults", response_model=List[AgentConfigRead])
async def seed_default_agents(request: Request, db: AsyncSession = Depends(get_db)):
    owner_user_id = await _owner_user_id_for_agents(request, db)
    if owner_user_id is None:
        await seed_default_cli_agents(db)
    agents = await _registry(db, owner_user_id).list_active()
    return [AgentConfigRead.from_model(agent) for agent in agents]


@router.post("/configure-builtins-codex", response_model=List[AgentConfigRead])
async def configure_builtin_agents_codex(request: Request, db: AsyncSession = Depends(get_db)):
    owner_user_id = await _owner_user_id_for_agents(request, db)
    await configure_builtin_role_agents_as_codex(db, owner_user_id=owner_user_id)
    agents = await _registry(db, owner_user_id).list_active()
    return [AgentConfigRead.from_model(agent) for agent in agents]


@router.post("", response_model=AgentConfigRead, status_code=201)
async def create_agent(data: AgentConfigCreate, request: Request, db: AsyncSession = Depends(get_db)):
    owner_user_id = await _owner_user_id_for_agents(request, db)
    try:
        agent = await _registry(db, owner_user_id).create(data)
    except InvalidCliAgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return AgentConfigRead.from_model(agent)


@router.get("/check-executable")
async def check_executable(path: str):
    if not path.strip():
        raise HTTPException(status_code=400, detail="path must not be empty")
    return CliAgentRegistry.executable_status(path).to_api()


@router.get("/codex-config", response_model=CodexLocalConfigRead)
async def get_codex_config():
    return CodexLocalConfigService().status().to_api()


@router.put("/codex-config", response_model=CodexLocalConfigRead)
async def update_codex_config(data: CodexLocalConfigUpdate):
    try:
        status = CodexLocalConfigService().configure(
            connection=data.connection,
            base_url=data.base_url,
            model=data.model,
            api_key=data.api_key,
            provider_id=data.provider_id,
            provider_name=data.provider_name,
            use_chatgpt_auth=data.use_chatgpt_auth,
        )
    except CodexLocalConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return status.to_api()


@router.get("/runtime/processes")
async def list_cli_processes(sessionId: str | None = None):
    return {"processes": cli_runtime_registry.active_snapshots(sessionId)}


@router.get("/{agent_id}", response_model=AgentConfigRead)
async def get_agent(agent_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    owner_user_id = await _owner_user_id_for_agents(request, db)
    try:
        agent = await _registry(db, owner_user_id).get(agent_id)
    except CliAgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return AgentConfigRead.from_model(agent)


@router.patch("/{agent_id}", response_model=AgentConfigRead)
async def update_agent(agent_id: str, data: AgentConfigUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    owner_user_id = await _owner_user_id_for_agents(request, db)
    try:
        agent = await _registry(db, owner_user_id).update(agent_id, data)
    except CliAgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    except InvalidCliAgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return AgentConfigRead.from_model(agent)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    owner_user_id = await _owner_user_id_for_agents(request, db)
    try:
        await _registry(db, owner_user_id).soft_delete(agent_id)
    except CliAgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return {"ok": True}
