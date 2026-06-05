"""AgentExecutor DAG 集成测试。"""

import uuid
import pytest

from app.domain.execution_planner import AgentCall, DAGPhase
from app.models import AgentConfig
from app.services.agent_executor import AgentExecutor
from app.services.shared_context import SharedContext
from app.services.token_event import TokenEvent


def make_agent(name: str) -> AgentConfig:
    return AgentConfig(
        id=str(uuid.uuid4()),
        name=name,
        description="",
        system_prompt="测试系统提示",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable="python",
        init_args="[]",
        env_vars="{}",
    )


class CaptureCliRunner:
    def __init__(self):
        self.calls: list[list[dict]] = []

    async def execute(self, call, *, session_id: str, workspace_path: str):
        self.calls.append([dict(m) for m in call.input_messages])
        yield TokenEvent(
            agent_id=call.agent.id,
            agent_name=call.agent.name,
            token="OUT",
            metadata={
                "task": call.task,
                "role": call.role,
                "phase": call.phase,
                "depends_on": list(call.depends_on),
            },
        )
        yield TokenEvent(
            agent_id=call.agent.id,
            agent_name=call.agent.name,
            done=True,
            metadata={"task": call.task, "role": call.role, "phase": call.phase},
        )


@pytest.mark.asyncio
async def test_execute_dag_emits_phase_change_and_injects_context():
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
    executor._cli_runner = CaptureCliRunner()
    async for ev in executor.execute(
        calls,
        "dag",
        dag_phases=phases,
        shared_context=SharedContext(base),
        session_id="s1",
        workspace_path=".",
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
async def test_single_without_workspace_returns_cli_workspace_error():
    call = AgentCall(make_agent("缺失适配器"), task="primary", role="executor")
    executor = AgentExecutor()

    events = [ev async for ev in executor.execute([call], "single")]

    assert events[-1].error == "CLI Agent requires a project workspace"
    assert "只支持 CLI Agent" in events[-1].token
