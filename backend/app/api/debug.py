import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..domain.context_manager import ContextManager
from ..domain.orchestrator_debug import OrchestratorDebugRequest, OrchestratorDebugRunner
from ..models import AgentConfig

router = APIRouter(prefix="/debug", tags=["debug"])


class OrchestratorDebugBody(BaseModel):
    content: str
    agent_ids: list[str] | None = Field(None, alias="agentIds")
    mentions: list[str] = Field(default_factory=list)
    use_mock_agents: bool = Field(True, alias="useMockAgents")
    supplemental: bool = False

    model_config = {"populate_by_name": True}


@router.post("/orchestrator/dry-run")
async def dry_run_orchestrator(
    data: OrchestratorDebugBody,
    db: AsyncSession = Depends(get_db),
):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")

    agents = await _load_agents(db, data)
    runner = OrchestratorDebugRunner(context_manager=ContextManager())
    return runner.run(OrchestratorDebugRequest(
        content=data.content,
        agents=agents,
        mentions=data.mentions,
        supplemental=data.supplemental,
    ))


async def _load_agents(db: AsyncSession, data: OrchestratorDebugBody) -> list[AgentConfig]:
    if data.agent_ids:
        result = await db.execute(
            select(AgentConfig).where(
                AgentConfig.is_active == True,
                AgentConfig.id.in_(data.agent_ids),
            )
        )
        agents = list(result.scalars().all())
        found = {a.id for a in agents}
        missing = [aid for aid in data.agent_ids if aid not in found]
        if missing:
            raise HTTPException(status_code=404, detail=f"Agent 不存在或已禁用: {', '.join(missing)}")
        order = {aid: i for i, aid in enumerate(data.agent_ids)}
        agents.sort(key=lambda a: order.get(a.id, 0))
        return agents

    if data.use_mock_agents:
        return _mock_agents()

    result = await db.execute(
        select(AgentConfig).where(AgentConfig.is_active == True).order_by(AgentConfig.updated_at.desc())
    )
    return list(result.scalars().all())


def _mock_agents() -> list[AgentConfig]:
    specs = [
        ("debug-planner", "架构师", "系统架构与技术方案", "擅长架构设计、技术方案、需求拆解"),
        ("debug-frontend", "前端专家", "React 前端与 UI 组件", "擅长 React、TypeScript、前端、UI、组件"),
        ("debug-backend", "后端专家", "Python API 与数据库", "擅长 Python、FastAPI、后端、API、数据库"),
        ("debug-reviewer", "审查员", "测试、安全与代码审查", "擅长审查、测试、安全、质量评估"),
        ("debug-researcher", "研究员", "调研分析与综合写作", "擅长调研、分析、比较、总结、批判"),
    ]
    return [
        AgentConfig(
            id=agent_id or str(uuid.uuid4()),
            name=name,
            description=description,
            system_prompt=system_prompt,
            provider="debug",
            model="dry-run",
        )
        for agent_id, name, description, system_prompt in specs
    ]
