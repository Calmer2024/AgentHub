from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import AgentConfig
from ..agents.cli_runtime import cli_process_manager
from ..services.cli_agent_registry import (
    CliAgentNotFoundError,
    CliAgentRegistry,
    InvalidCliAgentError,
    decode_json_dict,
    decode_json_list,
)
from ..services.codex_local_config_service import (
    CodexLocalConfigError,
    CodexLocalConfigService,
)

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentConfigCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = Field("", alias="systemPrompt")
    agent_type: str = Field("cli_wrapper", alias="agentType")
    cli_tool: str = Field("custom", alias="cliTool")
    executable: str | None = None
    init_args: list[str] = Field(default_factory=list, alias="initArgs")
    env_vars: dict[str, str] = Field(default_factory=dict, alias="envVars")

    model_config = {"populate_by_name": True}


class AgentConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = Field(None, alias="systemPrompt")
    agent_type: str | None = Field(None, alias="agentType")
    cli_tool: str | None = Field(None, alias="cliTool")
    executable: str | None = None
    init_args: list[str] | None = Field(None, alias="initArgs")
    env_vars: dict[str, str] | None = Field(None, alias="envVars")
    is_active: bool | None = Field(None, alias="isActive")

    model_config = {"populate_by_name": True}


class AgentConfigRead(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str = Field(alias="systemPrompt")
    agent_type: str = Field(alias="agentType")
    cli_tool: str = Field(alias="cliTool")
    executable: str | None = None
    init_args: list[str] = Field(alias="initArgs")
    env_vars: dict[str, str] = Field(alias="envVars")
    status: str = "not_found"
    version: str | None = None
    executable_path: str | None = Field(None, alias="executablePath")
    is_active: bool = Field(alias="isActive")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_model(cls, agent: AgentConfig):
        status = CliAgentRegistry.executable_status(agent.executable)
        return cls(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            agent_type=agent.agent_type or "cli_wrapper",
            cli_tool=agent.cli_tool or "custom",
            executable=agent.executable,
            init_args=decode_json_list(agent.init_args),
            env_vars=decode_json_dict(agent.env_vars, cli_tool=agent.cli_tool),
            status=status.status,
            version=status.version,
            executable_path=status.executable_path,
            is_active=agent.is_active,
            created_at=agent.created_at.isoformat() if agent.created_at else "",
            updated_at=agent.updated_at.isoformat() if agent.updated_at else "",
        )


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


def _registry(db: AsyncSession) -> CliAgentRegistry:
    return CliAgentRegistry(db)


@router.get("", response_model=List[AgentConfigRead])
async def list_agents(db: AsyncSession = Depends(get_db)):
    agents = await _registry(db).list_active()
    return [AgentConfigRead.from_model(agent) for agent in agents]


@router.post("", response_model=AgentConfigRead, status_code=201)
async def create_agent(data: AgentConfigCreate, db: AsyncSession = Depends(get_db)):
    try:
        agent = await _registry(db).create(data)
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
    return {"processes": cli_process_manager.active_snapshots(sessionId)}


@router.get("/{agent_id}", response_model=AgentConfigRead)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    try:
        agent = await _registry(db).get(agent_id)
    except CliAgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return AgentConfigRead.from_model(agent)


@router.patch("/{agent_id}", response_model=AgentConfigRead)
async def update_agent(agent_id: str, data: AgentConfigUpdate, db: AsyncSession = Depends(get_db)):
    try:
        agent = await _registry(db).update(agent_id, data)
    except CliAgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    except InvalidCliAgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return AgentConfigRead.from_model(agent)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    try:
        await _registry(db).soft_delete(agent_id)
    except CliAgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return {"ok": True}
