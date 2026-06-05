import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.registry import agent_registry
from ..config import settings
from ..database import get_db
from ..domain.orchestrator_debug import OrchestratorPlanBridge
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

    bridge = OrchestratorPlanBridge()
    agents = await _load_agents(db, data.agent_ids, data.use_mock_agents)
    bridge_input = bridge.build_input(data.content, agents)
    provider = data.provider or getattr(settings, "orchestrator_provider", "deepseek") or "deepseek"
    model = data.model or getattr(settings, "orchestrator_model", "") or _default_model_for(provider)
    adapter = agent_registry.get_adapter(provider)
    if not adapter:
        raise HTTPException(status_code=400, detail=f"调度器模型 provider 不存在: {provider}")

    try:
        response = await adapter.chat(
            messages=[{"role": "user", "content": bridge_input["prompt"]}],
            system_prompt="你是 AgentHub 的 Orchestrator 调度器，只输出 draft plan JSON。",
            model=model or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"调用调度器模型失败: {exc}") from exc

    parsed = bridge.parse_output(response.content, bridge_input["candidateAgents"])
    return {
        **bridge_input,
        "llm": {
            "provider": provider,
            "model": model,
        },
        **parsed,
    }


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


def _default_model_for(provider: str) -> str:
    field_name = {
        "openai": "openai_model",
        "claude": "claude_model",
        "deepseek": "deepseek_model",
        "gemini": "gemini_model",
        "minimax": "minimax_model",
        "glm": "glm_model",
    }.get(provider)
    if field_name:
        value = getattr(settings, field_name, "")
        if value:
            return value
    return agent_registry.get_default_model(provider)


def _mock_agents() -> list[AgentConfig]:
    specs = [
        ("mock_architect", "架构专家", "系统架构与技术方案", "擅长架构设计、技术方案、需求拆解"),
        ("mock_frontend", "前端专家", "React 前端与 UI 组件", "擅长 React、TypeScript、前端、UI、组件"),
        ("mock_backend", "后端专家", "Python API 与数据库", "擅长 Python、FastAPI、后端、API、数据库"),
        ("mock_reviewer", "审查专家", "测试、安全与代码审查", "擅长审查、测试、安全、质量评估"),
        ("mock_researcher", "研究专家", "调研分析与综合写作", "擅长调研、分析、比较、总结、批判"),
    ]
    return [
        AgentConfig(
            id=agent_id or str(uuid.uuid4()),
            name=name,
            description=description,
            system_prompt=system_prompt,
            provider="debug",
            model="manual-bridge",
        )
        for agent_id, name, description, system_prompt in specs
    ]
