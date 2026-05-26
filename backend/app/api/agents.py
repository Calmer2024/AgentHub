import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import AgentConfig
from ..agents.registry import agent_registry

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentConfigCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = Field("你是一个有帮助的 AI 助手。", alias="systemPrompt")
    provider: str = "deepseek"
    model: str = "deepseek-v4-flash"
    temperature: float = 0.7

    model_config = {"populate_by_name": True}


class AgentConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = Field(None, alias="systemPrompt")
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    is_active: bool | None = Field(None, alias="isActive")

    model_config = {"populate_by_name": True}


class AgentConfigRead(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str = Field(alias="systemPrompt")
    provider: str
    model: str
    temperature: float
    is_active: bool = Field(alias="isActive")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_orm_with_iso(cls, obj: AgentConfig):
        return cls(
            id=obj.id,
            name=obj.name,
            description=obj.description,
            system_prompt=obj.system_prompt,
            provider=obj.provider,
            model=obj.model,
            temperature=obj.temperature,
            is_active=obj.is_active,
            created_at=obj.created_at.isoformat() if obj.created_at else "",
            updated_at=obj.updated_at.isoformat() if obj.updated_at else "",
        )


@router.get("", response_model=List[AgentConfigRead])
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentConfig).where(AgentConfig.is_active == True).order_by(AgentConfig.updated_at.desc())
    )
    return [AgentConfigRead.from_orm_with_iso(a) for a in result.scalars().all()]


@router.post("", response_model=AgentConfigRead, status_code=201)
async def create_agent(data: AgentConfigCreate, db: AsyncSession = Depends(get_db)):
    if data.provider not in agent_registry.get_agent_names():
        raise HTTPException(status_code=400, detail=f"未知供应商: {data.provider}")

    agent = AgentConfig(
        id=str(uuid.uuid4()),
        name=data.name,
        description=data.description,
        system_prompt=data.system_prompt,
        provider=data.provider,
        model=data.model,
        temperature=data.temperature,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return AgentConfigRead.from_orm_with_iso(agent)


@router.get("/{agent_id}", response_model=AgentConfigRead)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await db.get(AgentConfig, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return AgentConfigRead.from_orm_with_iso(agent)


@router.patch("/{agent_id}", response_model=AgentConfigRead)
async def update_agent(agent_id: str, data: AgentConfigUpdate, db: AsyncSession = Depends(get_db)):
    agent = await db.get(AgentConfig, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    for field in ("name", "description", "system_prompt", "provider", "model", "temperature", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)
    return AgentConfigRead.from_orm_with_iso(agent)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await db.get(AgentConfig, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    agent.is_active = False
    await db.commit()
    return {"ok": True}
