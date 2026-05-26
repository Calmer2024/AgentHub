import os
from fastapi import APIRouter
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
}

_API_KEY_FIELDS = ("anthropic_api_key", "deepseek_api_key", "gemini_api_key",
                   "openai_api_key", "minimax_api_key", "glm_api_key")

_MODEL_FIELDS = ("openai_model", "claude_model", "deepseek_model",
                 "gemini_model", "minimax_model", "glm_model")

_MODEL_DEFAULTS = {
    "openai_model": "gpt-4o",
    "claude_model": "claude-3-5-sonnet-20241022",
    "deepseek_model": "deepseek-v4-flash",
    "gemini_model": "gemini-3.5-flash",
    "minimax_model": "MiniMax-M2.7",
    "glm_model": "glm-5.1",
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

    model_config = {"populate_by_name": True}


def _build_settings_read() -> SettingsRead:
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
    )


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

    if env_updates:
        _write_env(env_updates)

    return _build_settings_read()
