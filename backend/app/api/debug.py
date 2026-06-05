import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..domain.orchestrator_debug import OrchestratorPlanBridge, mock_agent
from ..models import AgentConfig

router = APIRouter(prefix="/debug", tags=["debug"])


class BuildOrchestratorInputBody(BaseModel):
    content: str
    agent_ids: list[str] | None = Field(None, alias="agentIds")
    use_mock_agents: bool = Field(True, alias="useMockAgents")

    model_config = {"populate_by_name": True}


class ParseOrchestratorOutputBody(BaseModel):
    raw_output: str = Field(..., alias="rawOutput")
    candidate_agents: list[dict[str, Any]] = Field(default_factory=list, alias="candidateAgents")

    model_config = {"populate_by_name": True}


class GenerateOrchestratorPlanBody(BuildOrchestratorInputBody):
    provider: str | None = None
    model: str | None = None


@router.post("/orchestrator/build-input")
async def build_orchestrator_input(
    data: BuildOrchestratorInputBody,
    db: AsyncSession = Depends(get_db),
):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")

    agents = await _load_agents(db, data.agent_ids, data.use_mock_agents)
    return OrchestratorPlanBridge().build_input(data.content, agents)


@router.post("/orchestrator/parse-output")
async def parse_orchestrator_output(data: ParseOrchestratorOutputBody):
    if not data.raw_output.strip():
        raise HTTPException(status_code=400, detail="rawOutput 不能为空")
    return OrchestratorPlanBridge().parse_output(data.raw_output, data.candidate_agents)


@router.post("/orchestrator/generate-plan")
async def generate_orchestrator_plan(
    data: GenerateOrchestratorPlanBody,
    db: AsyncSession = Depends(get_db),
):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    raise HTTPException(
        status_code=501,
        detail="当前 CLI 基线不再使用旧 Provider 调试链路；请使用手动桥接，或在群聊中 @Orchestrator 调度器生成 draft plan。",
    )


async def _load_agents(
    db: AsyncSession,
    agent_ids: list[str] | None,
    use_mock_agents: bool,
) -> list[AgentConfig]:
    if agent_ids:
        result = await db.execute(
            select(AgentConfig).where(
                AgentConfig.is_active == True,
                AgentConfig.id.in_(agent_ids),
            )
        )
        agents = list(result.scalars().all())
        found = {a.id for a in agents}
        missing = [aid for aid in agent_ids if aid not in found]
        if missing:
            raise HTTPException(status_code=404, detail=f"Agent 不存在或已禁用: {', '.join(missing)}")
        order = {aid: i for i, aid in enumerate(agent_ids)}
        agents.sort(key=lambda a: order.get(a.id, 0))
        return agents

    if use_mock_agents:
        return _mock_agents()

    result = await db.execute(
        select(AgentConfig).where(AgentConfig.is_active == True).order_by(AgentConfig.updated_at.desc())
    )
    return list(result.scalars().all())


def _mock_agents() -> list[AgentConfig]:
    specs = [
        ("mock_architect", "架构专家", "系统架构与技术方案", "architect", ["api_design", "database_design"]),
        ("mock_frontend", "前端专家", "React 前端与 UI 组件", "frontend_engineer", ["react", "typescript", "web_preview"]),
        ("mock_backend", "后端专家", "Python API 与数据库", "backend_engineer", ["api_design", "database"]),
        ("mock_reviewer", "审查专家", "测试、安全与代码审查", "code_reviewer", ["testing", "security_review"]),
        ("mock_researcher", "研究专家", "调研分析与综合写作", "researcher", ["analysis", "writing"]),
    ]
    return [
        mock_agent(agent_id or str(uuid.uuid4()), name, description, primary_skill, auxiliary_skills)
        for agent_id, name, description, primary_skill, auxiliary_skills in specs
    ]
