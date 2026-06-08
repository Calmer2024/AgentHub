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
        ("mock_architect", "系统架构师", "系统边界、接口契约与演进路径", "architect", ["system_boundary", "contract_design"]),
        ("mock_designer", "UX/UI设计师", "信息架构、界面布局与交互状态", "ux_ui_designer", ["interaction_flow", "visual_system"]),
        ("mock_frontend", "前端工程师", "React 前端、状态管理与组件实现", "frontend_engineer", ["react_typescript", "responsive_ui"]),
        ("mock_backend", "后端工程师", "FastAPI 服务、业务逻辑与集成测试", "backend_engineer", ["fastapi_service", "integration_testing"]),
        ("mock_tester", "测试工程师", "测试策略、回归风险与验收报告", "test_engineer", ["risk_based_testing", "frontend_ux_testing"]),
    ]
    return [
        mock_agent(agent_id or str(uuid.uuid4()), name, description, primary_skill, auxiliary_skills)
        for agent_id, name, description, primary_skill, auxiliary_skills in specs
    ]
