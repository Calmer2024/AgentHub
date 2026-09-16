import json
import sys
import uuid
from pathlib import Path

import pytest

from app.agents.cli_events import CliEvent
from app.models import AgentConfig


BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"


def make_agent(name: str, *, skill: str | None = None) -> AgentConfig:
    cli = BACKEND_ROOT / ".test-bin" / "fixture_cli.py"
    return AgentConfig(
        id=str(uuid.uuid4()),
        name=name,
        description=f"{name} 的职责说明",
        system_prompt="",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable=sys.executable,
        init_args=json.dumps([str(cli)]),
        env_vars="{}",
        primary_skill=skill,
        is_active=True,
    )


def events(response) -> list[dict]:
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


async def create_group(test_client, db_session, workers: list[AgentConfig]) -> tuple[str, dict]:
    db_session.add_all(workers)
    await db_session.commit()
    response = await test_client.post("/api/sessions", json={
        "title": "统一协作群",
        "mode": "group",
        "agentConfigIds": [worker.id for worker in workers],
    })
    assert response.status_code == 201, response.text
    session_id = response.json()["id"]
    members = (await test_client.get(f"/api/sessions/{session_id}/members")).json()
    orchestrator = next(member for member in members if member["agentName"] == "项目Leader")
    return session_id, orchestrator


@pytest.mark.asyncio
async def test_group_session_adds_single_project_leader(test_client, test_agent):
    response = await test_client.post("/api/sessions", json={
        "mode": "group",
        "agentConfigIds": [test_agent.id],
    })
    assert response.status_code == 201
    members = (await test_client.get(f"/api/sessions/{response.json()['id']}/members")).json()
    assert [member["agentName"] for member in members].count("项目Leader") == 1
    assert any(member["agentConfigId"] == test_agent.id for member in members)


@pytest.mark.asyncio
async def test_single_worker_mention_is_direct_turn(test_client, test_agent):
    response = await test_client.post("/api/sessions", json={
        "mode": "group",
        "agentConfigIds": [test_agent.id],
    })
    session_id = response.json()["id"]
    chat = await test_client.post(f"/api/sessions/{session_id}/chat", json={
        "content": f"@{test_agent.name} 直接回答",
        "mentions": [test_agent.id],
    })
    payloads = events(chat)
    types = [item.get("type") for item in payloads]
    assert "group.direct_turn_started" in types
    assert "orchestrator.plan_execution_created" not in types
    starts = [item for item in payloads if item.get("type") == "agent.start"]
    assert [item["agentId"] for item in starts] == [test_agent.id]


@pytest.mark.asyncio
async def test_multiple_worker_mentions_generate_plan_without_running_workers(
    test_client, db_session, monkeypatch,
):
    workers = [make_agent("前端工程师"), make_agent("后端工程师")]
    session_id, orchestrator = await create_group(test_client, db_session, workers)

    async def fake_stream(self, **kwargs):
        agent = kwargs["agent"]
        assert agent.id == orchestrator["agentConfigId"]
        plan = {
            "plan_id": "plan_multi_scope",
            "status": "draft",
            "tasks": [
                {
                    "task_id": "T1",
                    "title": "实现接口",
                    "goal": "提供后端接口",
                    "assigned_agent_id": workers[1].id,
                    "assigned_agent_name": workers[1].name,
                    "assignment_reason": "负责后端实现",
                    "depends_on": [],
                    "expected_outputs": ["接口代码"],
                    "acceptance_criteria": ["接口可调用"],
                },
                {
                    "task_id": "T2",
                    "title": "接入页面",
                    "goal": "消费后端接口",
                    "assigned_agent_id": workers[0].id,
                    "assigned_agent_name": workers[0].name,
                    "assignment_reason": "负责前端实现",
                    "depends_on": ["T1"],
                    "expected_outputs": ["页面代码"],
                    "acceptance_criteria": ["页面可用"],
                },
            ],
        }
        yield CliEvent("agent.output", "planner", chunk=json.dumps(plan, ensure_ascii=False), chunk_type="text")
        yield CliEvent("agent.process.completed", "planner", exit_code=0)

    from app.services.cli_agent_service import CliAgentService
    monkeypatch.setattr(CliAgentService, "stream", fake_stream)
    response = await test_client.post(f"/api/sessions/{session_id}/chat", json={
        "content": "前后端协作实现功能",
        "mentions": [worker.id for worker in workers],
    })
    payloads = events(response)
    assert "group.direct_turn_started" not in [item.get("type") for item in payloads]
    starts = [item for item in payloads if item.get("type") == "agent.start"]
    assert {item["agentId"] for item in starts} == {orchestrator["agentConfigId"]}
    messages = (await test_client.get(f"/api/sessions/{session_id}/messages")).json()
    plan_message = next(item for item in messages if item["role"] == "assistant")
    assert plan_message["metadata"]["orchestratorPlan"]["ok"] is True
    assigned = {
        task["assigned_agent_id"]
        for task in plan_message["metadata"]["orchestratorPlan"]["normalizedPlan"]["tasks"]
    }
    assert assigned == {worker.id for worker in workers}


@pytest.mark.asyncio
async def test_no_mention_steward_routes_to_one_direct_turn(
    test_client, db_session, monkeypatch,
):
    worker = make_agent("产品经理")
    session_id, orchestrator = await create_group(test_client, db_session, [worker])
    calls: list[str] = []

    async def fake_stream(self, **kwargs):
        agent = kwargs["agent"]
        calls.append(agent.id)
        if agent.id == orchestrator["agentConfigId"]:
            decision = {
                "route_type": "direct_turn",
                "reply": "交给产品经理直接回答。",
                "reason": "单个成员足够",
                "selected_agent_ids": [worker.id],
                "task_brief": "回答产品问题",
            }
            yield CliEvent("agent.output", "steward", chunk=json.dumps(decision, ensure_ascii=False), chunk_type="text")
        else:
            yield CliEvent("agent.output", "worker", chunk="产品答复", chunk_type="text")
        yield CliEvent("agent.process.completed", agent.id, exit_code=0)

    from app.services.cli_agent_service import CliAgentService
    monkeypatch.setattr(CliAgentService, "stream", fake_stream)
    response = await test_client.post(f"/api/sessions/{session_id}/chat", json={"content": "解释一下需求"})
    payloads = events(response)
    route = next(item for item in payloads if item.get("type") == "orchestrator.route_decided")
    assert route["routeType"] == "direct_turn"
    assert calls == [orchestrator["agentConfigId"], worker.id]
    assert "group.direct_turn_started" in [item.get("type") for item in payloads]


@pytest.mark.asyncio
async def test_orchestrator_mention_creates_draft_plan(test_client, db_session, monkeypatch):
    worker = make_agent("后端工程师")
    session_id, orchestrator = await create_group(test_client, db_session, [worker])

    async def fake_stream(self, **kwargs):
        plan = {
            "plan_id": "plan_orchestrator_mention",
            "tasks": [{
                "task_id": "T1",
                "title": "实现接口",
                "goal": "交付 API",
                "assigned_agent_id": worker.id,
                "assigned_agent_name": worker.name,
                "assignment_reason": "后端职责匹配",
                "depends_on": [],
                "expected_outputs": ["API"],
                "acceptance_criteria": ["API 可调用"],
            }],
        }
        yield CliEvent("agent.output", "planner", chunk=json.dumps(plan, ensure_ascii=False), chunk_type="text")
        yield CliEvent("agent.process.completed", "planner", exit_code=0)

    from app.services.cli_agent_service import CliAgentService
    monkeypatch.setattr(CliAgentService, "stream", fake_stream)
    response = await test_client.post(f"/api/sessions/{session_id}/chat", json={
        "content": "生成计划",
        "mentions": [orchestrator["agentConfigId"]],
    })
    payloads = events(response)
    assert "agent.start" in [item.get("type") for item in payloads]
    assert "group.direct_turn_started" not in [item.get("type") for item in payloads]
    messages = (await test_client.get(f"/api/sessions/{session_id}/messages")).json()
    assert messages[-1]["metadata"]["orchestratorPlan"]["normalizedPlan"]["plan_id"] == "plan_orchestrator_mention"
