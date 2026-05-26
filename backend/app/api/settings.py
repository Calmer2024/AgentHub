import os
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..config import settings

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

_ENV_KEY_MAP = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
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

    model_config = {"populate_by_name": True}


class SettingsUpdate(BaseModel):
    anthropic_api_key: str | None = Field(None, alias="anthropicApiKey")
    deepseek_api_key: str | None = Field(None, alias="deepseekApiKey")
    gemini_api_key: str | None = Field(None, alias="geminiApiKey")
    openai_api_key: str | None = Field(None, alias="openaiApiKey")

    model_config = {"populate_by_name": True}


@router.get("", response_model=SettingsRead)
async def get_settings():
    return SettingsRead(
        anthropic_api_key=_mask_key(settings.anthropic_api_key),
        deepseek_api_key=_mask_key(settings.deepseek_api_key),
        gemini_api_key=_mask_key(settings.gemini_api_key),
        openai_api_key=_mask_key(settings.openai_api_key),
    )


@router.put("", response_model=SettingsRead)
async def update_settings(data: SettingsUpdate):
    env_updates = {}
    for field_name in ("anthropic_api_key", "deepseek_api_key", "gemini_api_key", "openai_api_key"):
        value = getattr(data, field_name)
        if value is not None:
            setattr(settings, field_name, value)
            env_updates[_ENV_KEY_MAP[field_name]] = value

    if env_updates:
        _write_env(env_updates)

    return SettingsRead(
        anthropic_api_key=_mask_key(settings.anthropic_api_key),
        deepseek_api_key=_mask_key(settings.deepseek_api_key),
        gemini_api_key=_mask_key(settings.gemini_api_key),
        openai_api_key=_mask_key(settings.openai_api_key),
    )
