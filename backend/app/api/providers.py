from typing import List
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..agents.registry import agent_registry

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderCapabilityRead(BaseModel):
    supports_streaming: bool = Field(alias="supportsStreaming")
    supports_file_input: bool = Field(alias="supportsFileInput")
    supports_tool_call: bool = Field(alias="supportsToolCall")
    max_context_tokens: int = Field(alias="maxContextTokens")
    tags: list[str]

    model_config = {"populate_by_name": True}


class ProviderRead(BaseModel):
    name: str
    display_name: str = Field(alias="displayName")
    provider: str
    is_available: bool = Field(alias="isAvailable")
    unavailable_reason: str | None = Field(None, alias="unavailableReason")
    models: list[str] = []
    default_model: str = Field("", alias="defaultModel")
    capability: ProviderCapabilityRead

    model_config = {"populate_by_name": True}


@router.get("", response_model=List[ProviderRead])
async def list_providers():
    return agent_registry.get_agents_info()
