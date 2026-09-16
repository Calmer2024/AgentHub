import asyncio
import sys
import uuid
from pathlib import Path

import pytest

from app.models import AgentConfig, Project, Session, SessionMember
from app.services.orchestrator_execution import (
    CliTaskRunner,
    OrchestratorPhaseReviewer,
    execution_registry,
)


def _agent(agent_id: str, name: str, primary_skill: str) -> AgentConfig:
    return AgentConfig(
        id=agent_id,
        name=name,
        description=f"{name}的职责说明",
        system_prompt="",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable=sys.executable,
        init_args="[]",
        env_vars="{}",
        primary_skill=primary_skill,
        auxiliary_skills="[]",
        context_policy="workspace_coding",
        is_active=True,
    )


async def _seed_group(db_session, *, with_orchestrator: bool = True):
    suffix = uuid.uuid4().hex[:8]
    workspace = Path(__file__).resolve().parents[3] / ".test-workspaces" / suffix
    workspace.mkdir(parents=True, exist_ok=True)
    project = Project(
        id=f"project_{suffix}",
        name="统一调度测试项目",
        workspace_path=str(workspace),
        status="ready",
    )
    backend = _agent(f"backend_{suffix}", "后端工程师", "backend_engineer")
    frontend = _agent(f"frontend_{suffix}", "前端工程师", "frontend_engineer")
    agents = [backend, frontend]
    orchestrator = None
    if with_orchestrator:
        orchestrator = _agent(f"orchestrator_{suffix}", "项目Leader", "orchestrator_planner")
        agents.append(orchestrator)
    session = Session(
        id=f"session_{suffix}",
        title="统一调度测试群",
        project_id=project.id,
        mode="group",
    )
    db_session.add_all([project, *agents, session])
    await db_session.flush()
    db_session.add_all([
        SessionMember(session_id=session.id, agent_config_id=agent.id)
        for agent in agents
    ])
    await db_session.commit()
    return session, orchestrator, backend, frontend


def _plan(backend: AgentConfig, frontend: AgentConfig) -> dict:
    return {
        "plan_id": f"plan_{uuid.uuid4().hex[:8]}",
        "status": "draft",
        "tasks": [
            {
                "task_id": "T1",
                "title": "实现后端接口",
                "goal": "提供可调用接口",
                "assigned_agent_id": backend.id,
                "assigned_agent_name": backend.name,
                "assignment_reason": "职责说明与后端任务匹配",
                "depends_on": [],
                "expected_outputs": ["后端代码"],
                "acceptance_criteria": ["接口可调用"],
                "max_attempts": 3,
            },
            {
                "task_id": "T2",
                "title": "接入前端页面",
                "goal": "消费后端接口",
                "assigned_agent_id": frontend.id,
                "assigned_agent_name": frontend.name,
                "assignment_reason": "职责说明与前端任务匹配",
                "depends_on": ["T1"],
                "expected_outputs": ["前端代码"],
                "acceptance_criteria": ["页面可用"],
                "max_attempts": 3,
            },
        ],
    }


async def _wait_completed(test_client, execution_id: str) -> dict:
    latest = None
    for _ in range(80):
        response = await test_client.get(f"/api/orchestrator/executions/{execution_id}")
        assert response.status_code == 200
        latest = response.json()
        if latest["status"] in {"completed", "failed"}:
            return latest
        await asyncio.sleep(0.03)
    raise AssertionError(f"执行未结束：{latest}")


@pytest.mark.asyncio
async def test_approved_plan_executes_and_restores_from_plan_record(test_client, db_session, monkeypatch):
    session, orchestrator, backend, frontend = await _seed_group(db_session)

    async def fake_run(self, task, execution, upstream_results):
        assert execution["groupContext"] == []
        return f"{task['taskId']} 已提交"

    async def accept(self, execution, phase, tasks):
        return {
            "phaseSummary": f"Phase {phase} 已验收",
            "tasks": [
                {"taskId": task["taskId"], "decision": "accepted", "feedback": "符合标准"}
                for task in tasks
            ],
        }

    monkeypatch.setattr(CliTaskRunner, "run", fake_run)
    monkeypatch.setattr(OrchestratorPhaseReviewer, "review", accept)
    response = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session.id,
        "normalizedPlan": _plan(backend, frontend),
    })
    assert response.status_code == 200, response.text
    execution_id = response.json()["executionId"]
    completed = await _wait_completed(test_client, execution_id)
    assert [task["status"] for task in completed["tasks"]] == ["accepted", "accepted"]
    assert [task["phase"] for task in completed["tasks"]] == [0, 1]
    assert completed["orchestratorAgentId"] == orchestrator.id

    execution_registry._executions.pop(execution_id, None)
    restored = await test_client.get(f"/api/orchestrator/executions/{execution_id}")
    assert restored.status_code == 200
    assert restored.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_plan_cannot_assign_agent_outside_group_scope(test_client, db_session):
    session, _, backend, frontend = await _seed_group(db_session)
    plan = _plan(backend, frontend)
    plan["tasks"][0]["assigned_agent_id"] = "outside_agent"
    response = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session.id,
        "normalizedPlan": plan,
    })
    assert response.status_code == 400
    assert "outside_agent" in response.text


@pytest.mark.asyncio
async def test_plan_execution_requires_group_orchestrator(test_client, db_session):
    session, _, backend, frontend = await _seed_group(db_session, with_orchestrator=False)
    response = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session.id,
        "normalizedPlan": _plan(backend, frontend),
    })
    assert response.status_code == 400
    assert "项目Leader" in response.text
