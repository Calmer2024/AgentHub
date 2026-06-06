from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import AgentConfig, Session
from ..services.orchestrator_execution import PlanExecutionError, execution_registry

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class ExecutePlanBody(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    normalized_plan: dict[str, Any] = Field(..., alias="normalizedPlan")

    model_config = {"populate_by_name": True}


@router.post("/plans/execute")
async def execute_orchestrator_plan(
    data: ExecutePlanBody,
    db: AsyncSession = Depends(get_db),
):
    if not data.session_id.strip():
        raise HTTPException(status_code=400, detail="sessionId 不能为空")

    session = await db.get(Session, data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session 不存在")

    active_agent_ids = await _active_agent_ids(db)
    try:
        return execution_registry.create_execution(
            session_id=data.session_id,
            plan=data.normalized_plan,
            active_agent_ids=active_agent_ids,
        )
    except PlanExecutionError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "调度计划无法执行",
                "errors": exc.errors,
                "warnings": exc.warnings,
            },
        ) from exc


async def _active_agent_ids(db: AsyncSession) -> set[str]:
    result = await db.execute(select(AgentConfig.id).where(AgentConfig.is_active == True))
    return {str(agent_id) for agent_id in result.scalars().all()}
