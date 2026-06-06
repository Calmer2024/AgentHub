from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.system_health_service import SystemHealthRead, SystemHealthService

router = APIRouter(prefix="/system", tags=["system"])


class SystemHealthCheckRequest(BaseModel):
    project_id: str | None = Field(default=None, alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")
    agent_id: str | None = Field(default=None, alias="agentId")

    model_config = {"populate_by_name": True}


@router.get("/health", response_model=SystemHealthRead)
async def get_system_health(
    projectId: str | None = None,
    sessionId: str | None = None,
    agentId: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await SystemHealthService(db).check(
        project_id=projectId,
        session_id=sessionId,
        agent_id=agentId,
    )


@router.post("/health/check", response_model=SystemHealthRead)
async def check_system_health(
    data: SystemHealthCheckRequest,
    db: AsyncSession = Depends(get_db),
):
    return await SystemHealthService(db).check(
        project_id=data.project_id,
        session_id=data.session_id,
        agent_id=data.agent_id,
    )
