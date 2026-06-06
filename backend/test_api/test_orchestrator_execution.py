import json
import uuid
from pathlib import Path

import pytest

from app.models import AgentConfig, Project, Session


def _agent(agent_id: str, name: str, primary_skill: str) -> AgentConfig:
    return AgentConfig(
        id=agent_id,
        name=name,
        description=name,
        system_prompt="",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable="fixture-agent",
        init_args="[]",
        env_vars="{}",
        primary_skill=primary_skill,
        auxiliary_skills=json.dumps(["workspace_editing"], ensure_ascii=False),
        context_policy="workspace_coding",
        is_active=True,
    )


async def _seed_session_with_agents(db_session):
    project = Project(
        id=str(uuid.uuid4()),
        name="调度执行测试项目",
        workspace_path=str(Path(__file__).resolve().parents[1] / ".test-workspaces" / str(uuid.uuid4())),
        status="ready",
    )
    frontend = _agent("agent_frontend_exec", "前端专家", "frontend_engineer")
    backend = _agent("agent_backend_exec", "后端专家", "backend_engineer")
    session = Session(
        id=str(uuid.uuid4()),
        title="调度执行测试会话",
        project_id=project.id,
        mode="group",
    )
    db_session.add_all([project, frontend, backend, session])
    await db_session.commit()
    return session.id


def _valid_plan() -> dict:
    return {
        "plan_id": "plan_exec_001",
        "status": "draft",
        "execution_policy": {
            "mode": "plan_only",
            "requires_approval_before_execution": True,
        },
        "tasks": [
            {
                "task_id": "T1",
                "title": "实现后端 API",
                "goal": "完成基础接口",
                "required_skills": ["backend_engineer"],
                "assigned_agent_id": "agent_backend_exec",
                "assigned_agent_name": "后端专家",
                "assignment_reason": "匹配后端能力",
                "depends_on": [],
                "expected_outputs": ["api"],
                "acceptance_criteria": ["接口可调用"],
            },
            {
                "task_id": "T2",
                "title": "实现前端页面",
                "goal": "完成列表页面",
                "required_skills": ["frontend_engineer"],
                "assigned_agent_id": "agent_frontend_exec",
                "assigned_agent_name": "前端专家",
                "assignment_reason": "匹配前端能力",
                "depends_on": ["T1"],
                "expected_outputs": ["ui"],
                "acceptance_criteria": ["页面可用"],
            },
        ],
    }


@pytest.mark.asyncio
async def test_execute_plan_creates_pending_execution(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)

    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": _valid_plan(),
    })

    assert res.status_code == 200
    data = res.json()
    assert data["executionId"].startswith("exec_")
    assert data["sessionId"] == session_id
    assert data["planId"] == "plan_exec_001"
    assert data["status"] == "pending"
    assert [task["status"] for task in data["tasks"]] == ["pending", "pending"]
    assert data["tasks"][1]["dependsOn"] == ["T1"]
    assert data["validation"]["ok"] is True


@pytest.mark.asyncio
async def test_execute_plan_rejects_missing_assigned_agent(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    plan = _valid_plan()
    plan["tasks"][0]["assigned_agent_id"] = None

    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": plan,
    })

    assert res.status_code == 400
    detail = res.json()["detail"]
    assert any("缺少 assigned_agent_id" in error for error in detail["errors"])


@pytest.mark.asyncio
async def test_execute_plan_rejects_invalid_dag(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    plan = _valid_plan()
    plan["tasks"][0]["depends_on"] = ["missing"]

    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": plan,
    })

    assert res.status_code == 400
    detail = res.json()["detail"]
    assert any("不存在的任务" in error for error in detail["errors"])


@pytest.mark.asyncio
async def test_execute_plan_rejects_unknown_session(test_client):
    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": "missing-session",
        "normalizedPlan": _valid_plan(),
    })

    assert res.status_code == 404
