import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import settings
from ..agents.registry import agent_registry

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

_ENV_KEY_MAP = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "minimax_api_key": "MINIMAX_API_KEY",
    "glm_api_key": "GLM_API_KEY",
    "openai_model": "OPENAI_MODEL",
    "claude_model": "CLAUDE_MODEL",
    "deepseek_model": "DEEPSEEK_MODEL",
    "gemini_model": "GEMINI_MODEL",
    "minimax_model": "MINIMAX_MODEL",
    "glm_model": "GLM_MODEL",
    "orchestrator_provider": "ORCHESTRATOR_PROVIDER",
    "orchestrator_model": "ORCHESTRATOR_MODEL",
}

_API_KEY_FIELDS = ("anthropic_api_key", "deepseek_api_key", "gemini_api_key",
                   "openai_api_key", "minimax_api_key", "glm_api_key")

_MODEL_FIELDS = ("openai_model", "claude_model", "deepseek_model",
                 "gemini_model", "minimax_model", "glm_model")

_ORCHESTRATOR_FIELDS = ("orchestrator_provider", "orchestrator_model")

_MODEL_DEFAULTS = {
    "openai_model": "gpt-4o",
    "claude_model": "claude-3-5-sonnet-20241022",
    "deepseek_model": "deepseek-v4-flash",
    "gemini_model": "gemini-3.5-flash",
    "minimax_model": "MiniMax-M2.7",
    "glm_model": "glm-5.1",
}

_PROVIDER_MODEL_FIELD = {
    "openai": "openai_model",
    "claude": "claude_model",
    "deepseek": "deepseek_model",
    "gemini": "gemini_model",
    "minimax": "minimax_model",
    "glm": "glm_model",
}


def _mask_key(key: str) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return key[:2] + "****"
    return key[:3] + "****" + key[-3:]


def _read_env() -> dict[str, str]:
    result = {}
    if not os.path.exists(ENV_PATH):
        return result
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                result[key] = value
    return result


def _write_env(updates: dict[str, str]) -> None:
    env = _read_env()
    env.update(updates)
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for key, value in env.items():
            f.write(f"{key}={value}\n")


class SettingsRead(BaseModel):
    anthropic_api_key: str | None = Field(None, alias="anthropicApiKey")
    deepseek_api_key: str | None = Field(None, alias="deepseekApiKey")
    gemini_api_key: str | None = Field(None, alias="geminiApiKey")
    openai_api_key: str | None = Field(None, alias="openaiApiKey")
    minimax_api_key: str | None = Field(None, alias="minimaxApiKey")
    glm_api_key: str | None = Field(None, alias="glmApiKey")
    openai_model: str = Field("gpt-4o", alias="openaiModel")
    claude_model: str = Field("claude-3-5-sonnet-20241022", alias="claudeModel")
    deepseek_model: str = Field("deepseek-v4-flash", alias="deepseekModel")
    gemini_model: str = Field("gemini-3.5-flash", alias="geminiModel")
    minimax_model: str = Field("MiniMax-M2.7", alias="minimaxModel")
    glm_model: str = Field("glm-5.1", alias="glmModel")
    orchestrator_provider: str = Field("deepseek", alias="orchestratorProvider")
    orchestrator_model: str = Field("deepseek-v4-flash", alias="orchestratorModel")

    model_config = {"populate_by_name": True}


class SettingsUpdate(BaseModel):
    anthropic_api_key: str | None = Field(None, alias="anthropicApiKey")
    deepseek_api_key: str | None = Field(None, alias="deepseekApiKey")
    gemini_api_key: str | None = Field(None, alias="geminiApiKey")
    openai_api_key: str | None = Field(None, alias="openaiApiKey")
    minimax_api_key: str | None = Field(None, alias="minimaxApiKey")
    glm_api_key: str | None = Field(None, alias="glmApiKey")
    openai_model: str | None = Field(None, alias="openaiModel")
    claude_model: str | None = Field(None, alias="claudeModel")
    deepseek_model: str | None = Field(None, alias="deepseekModel")
    gemini_model: str | None = Field(None, alias="geminiModel")
    minimax_model: str | None = Field(None, alias="minimaxModel")
    glm_model: str | None = Field(None, alias="glmModel")
    orchestrator_provider: str | None = Field(None, alias="orchestratorProvider")
    orchestrator_model: str | None = Field(None, alias="orchestratorModel")

    model_config = {"populate_by_name": True}


def _build_settings_read() -> SettingsRead:
    orchestrator_provider = getattr(settings, "orchestrator_provider", "deepseek") or "deepseek"
    return SettingsRead(
        anthropic_api_key=_mask_key(settings.anthropic_api_key),
        deepseek_api_key=_mask_key(settings.deepseek_api_key),
        gemini_api_key=_mask_key(settings.gemini_api_key),
        openai_api_key=_mask_key(settings.openai_api_key),
        minimax_api_key=_mask_key(settings.minimax_api_key),
        glm_api_key=_mask_key(settings.glm_api_key),
        openai_model=getattr(settings, "openai_model", "gpt-4o"),
        claude_model=getattr(settings, "claude_model", "claude-3-5-sonnet-20241022"),
        deepseek_model=getattr(settings, "deepseek_model", "deepseek-v4-flash"),
        gemini_model=getattr(settings, "gemini_model", "gemini-3.5-flash"),
        minimax_model=getattr(settings, "minimax_model", "MiniMax-M2.7"),
        glm_model=getattr(settings, "glm_model", "glm-5.1"),
        orchestrator_provider=orchestrator_provider,
        orchestrator_model=getattr(settings, "orchestrator_model", "") or _default_model_for(
            orchestrator_provider,
        ),
    )


def _default_model_for(provider: str) -> str:
    field_name = _PROVIDER_MODEL_FIELD.get(provider)
    if field_name:
        value = getattr(settings, field_name, "")
        if value:
            return value
    return agent_registry.get_default_model(provider)


@router.get("", response_model=SettingsRead)
async def get_settings():
    return _build_settings_read()


@router.put("", response_model=SettingsRead)
async def update_settings(data: SettingsUpdate):
    env_updates = {}
    for field_name in _API_KEY_FIELDS:
        value = getattr(data, field_name)
        if value is not None:
            setattr(settings, field_name, value)
            env_updates[_ENV_KEY_MAP[field_name]] = value

    for field_name in _MODEL_FIELDS:
        value = getattr(data, field_name)
        if value is not None:
            setattr(settings, field_name, value)
            env_updates[_ENV_KEY_MAP[field_name]] = value

    next_orchestrator_provider = data.orchestrator_provider
    if next_orchestrator_provider is not None:
        if next_orchestrator_provider not in agent_registry.get_agent_names():
            raise HTTPException(status_code=400, detail="未知 Orchestrator 模型供应商")
        setattr(settings, "orchestrator_provider", next_orchestrator_provider)
        env_updates[_ENV_KEY_MAP["orchestrator_provider"]] = next_orchestrator_provider
        if data.orchestrator_model is None:
            default_model = _default_model_for(next_orchestrator_provider)
            setattr(settings, "orchestrator_model", default_model)
            env_updates[_ENV_KEY_MAP["orchestrator_model"]] = default_model

    for field_name in _ORCHESTRATOR_FIELDS:
        value = getattr(data, field_name)
        if value is not None:
            setattr(settings, field_name, value)
            env_updates[_ENV_KEY_MAP[field_name]] = value

    if env_updates:
        _write_env(env_updates)

    return _build_settings_read()
