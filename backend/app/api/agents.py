from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Agent as DBAgent
from ..agents.registry import agent_registry

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCapabilityRead(BaseModel):
    supports_streaming: bool = Field(alias="supportsStreaming")
    supports_file_input: bool = Field(alias="supportsFileInput")
    supports_tool_call: bool = Field(alias="supportsToolCall")
    max_context_tokens: int = Field(alias="maxContextTokens")
    tags: list[str]

    model_config = {"populate_by_name": True}


class AgentRead(BaseModel):
    name: str
    display_name: str = Field(alias="displayName")
    provider: str
    is_available: bool = Field(alias="isAvailable")
    unavailable_reason: str | None = Field(None, alias="unavailableReason")
    capability: AgentCapabilityRead

    model_config = {"populate_by_name": True}


@router.get("", response_model=List[AgentRead])
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBAgent).where(DBAgent.is_active == True))
    db_agents = {a.name: a for a in result.scalars().all()}

    agents = []
    for info in agent_registry.get_agents_info():
        db_agent = db_agents.get(info["name"])
        info["is_configured"] = db_agent is not None
        if not info["is_available"]:
            info["unavailable_reason"] = "API Key 未配置"
        agents.append(info)

    return agents
