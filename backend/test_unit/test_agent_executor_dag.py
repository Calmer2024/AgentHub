"""AgentExecutor DAG 集成测试。"""

import uuid
import pytest

from app.domain.execution_planner import AgentCall, DAGPhase
from app.event_bus import EventType
from app.models import AgentConfig
from app.services.agent_executor import AgentExecutor
from app.services.shared_context import SharedContext


def make_agent(name: str) -> AgentConfig:
    return AgentConfig(
        id=str(uuid.uuid4()),
        name=name,
        description="",
        provider="deepseek",
        model="test-model",
        system_prompt="测试系统提示",
    )


class CaptureAdapter:
    def __init__(self):
        self.calls: list[list[dict]] = []

    async def chat_stream(self, messages, system_prompt, model=None, tools=None):
        self.calls.append([dict(m) for m in messages])
        for token in ["OUT"]:
            yield token


class CaptureBus:
    def __init__(self):
        self.events: list[tuple[EventType, dict]] = []

    async def publish(self, event_type: EventType, payload: dict):
        self.events.append((event_type, payload))


@pytest.mark.asyncio
async def test_execute_dag_emits_phase_change_and_injects_context(monkeypatch):
    adapter = CaptureAdapter()
    from app.agents.registry import agent_registry

    monkeypatch.setattr(agent_registry, "get_adapter", lambda provider: adapter)

    planner = make_agent("架构师")
    frontend = make_agent("前端")
    reviewer = make_agent("审查员")
    base = [{"role": "user", "content": "做登录系统"}]
    calls = [
        AgentCall(planner, task="planning", role="planner", input_messages=list(base), phase=0),
        AgentCall(frontend, task="frontend", role="executor", input_messages=list(base),
                  depends_on=["planning"], phase=1),
        AgentCall(reviewer, task="review", role="reviewer", input_messages=list(base),
                  depends_on=["frontend"], phase=2),
    ]
    phases = [
        DAGPhase(0, [calls[0]], "serial"),
        DAGPhase(1, [calls[1]], "serial"),
        DAGPhase(2, [calls[2]], "serial"),
    ]

    events = []
    executor = AgentExecutor()
    async for ev in executor.execute(
        calls, "dag", dag_phases=phases, shared_context=SharedContext(base),
    ):
        events.append(ev)

    phase_events = [e for e in events if e.event_type == "phase_change"]
    assert [e.metadata["status"] for e in phase_events] == [
        "running", "completed", "running", "completed", "running", "completed",
    ]
    assert any(e.token == "OUT" and e.metadata["phase"] == 1 for e in events)
    assert any("上一步 (planning) 完整产出" in m["content"] for m in calls[1].input_messages)
    assert any("上一步 (frontend) 完整产出" in m["content"] for m in calls[2].input_messages)


@pytest.mark.asyncio
async def test_agent_call_completed_emitted_on_adapter_missing(monkeypatch):
    """失败路径也必须发布 AGENT_CALL_COMPLETED 生命周期事件。"""
    from app.agents.registry import agent_registry

    monkeypatch.setattr(agent_registry, "get_adapter", lambda provider: None)
    bus = CaptureBus()
    call = AgentCall(make_agent("缺失适配器"), task="primary", role="executor")
    executor = AgentExecutor(event_bus=bus)

    events = [ev async for ev in executor.execute([call], "single")]

    assert events[-1].error == "adapter not found"
    completed = [e for e in bus.events if e[0] == EventType.AGENT_CALL_COMPLETED]
    assert len(completed) == 1
    assert completed[0][1]["status"] == "error"
    assert completed[0][1]["error"] == "adapter not found"
