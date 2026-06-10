"""SaaS 云端 CLI 凭据配置契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .phase10_schemas import SecretScope


CliTool = Literal["claude_code", "codex", "opencode"]
CliProviderType = Literal["official", "proxy", "cc_switch", "custom"]


class CliCredentialUpsert(BaseModel):
    scope: SecretScope = "user"
    owner_id: str | None = Field(default=None, alias="ownerId")
    provider_type: CliProviderType = Field(default="official", alias="providerType")
    provider_id: str | None = Field(default=None, alias="providerId")
    provider_name: str | None = Field(default=None, alias="providerName")
    base_url: str | None = Field(default=None, alias="baseUrl")
    model: str | None = None
    auth_env_key: str | None = Field(default=None, alias="authEnvKey")
    api_key: str | None = Field(default=None, alias="apiKey")
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @field_validator("provider_id", "provider_name", "base_url", "model", "auth_env_key", "api_key")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        clean = (value or "").strip()
        return clean or None


class CliCredentialConfigRead(BaseModel):
    cli_tool: CliTool = Field(alias="cliTool")
    scope: str
    owner_id: str = Field(alias="ownerId")
    provider_type: str = Field(alias="providerType")
    provider_id: str = Field(alias="providerId")
    provider_name: str = Field(alias="providerName")
    base_url: str | None = Field(default=None, alias="baseUrl")
    model: str | None = None
    auth_env_key: str = Field(alias="authEnvKey")
    configured: bool
    secret_names: list[str] = Field(default_factory=list, alias="secretNames")
    config: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class CliCredentialListRead(BaseModel):
    items: list[CliCredentialConfigRead]


class CliModelOptionRead(BaseModel):
    id: str
    name: str
    label: str
    provider_id: str = Field(alias="providerId")
    reasoning: bool = False
    tool_call: bool = Field(default=False, alias="toolCall")
    context: int | None = None
    output: int | None = None
    last_updated: str | None = Field(default=None, alias="lastUpdated")

    model_config = {"populate_by_name": True}


class CliModelListRead(BaseModel):
    cli_tool: CliTool = Field(alias="cliTool")
    provider_id: str = Field(alias="providerId")
    source: str
    items: list[CliModelOptionRead]

    model_config = {"populate_by_name": True}
