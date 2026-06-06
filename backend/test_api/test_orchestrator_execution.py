import json
import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AgentConfig, Message, Project, Session


async def _wait_execution_completed(test_client, execution_id: str, attempts: int = 20) -> dict:
    latest = None
    for _ in range(attempts):
        lookup = await test_client.get(f"/api/orchestrator/executions/{execution_id}")
        assert lookup.status_code == 200
        latest = lookup.json()
        if latest["status"] in {"completed", "failed"}:
            return latest
        await asyncio.sleep(0.05)
    assert latest is not None
    return latest


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
async def test_execute_plan_starts_async_scheduler_then_completes(test_client, db_session):
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
    assert data["status"] == "running"
    assert data["startedAt"] is not None
    assert data["completedAt"] is None
    assert [task["status"] for task in data["tasks"]] == ["pending", "pending"]
    assert data["tasks"][1]["dependsOn"] == ["T1"]
    assert data["validation"]["ok"] is True

    completed = await _wait_execution_completed(test_client, data["executionId"])
    assert completed["executionId"] == data["executionId"]
    assert completed["status"] == "completed"
    assert completed["completedAt"] is not None
    assert [task["status"] for task in completed["tasks"]] == ["completed", "completed"]
    assert completed["tasks"][0]["summary"] == (
        "T1 已完成：模拟执行 后端专家 / required_skills=backend_engineer"
    )
    assert all(task["resultMessageId"] for task in completed["tasks"])

    rows = await db_session.execute(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.content_type == "orchestrator_task_result",
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    task_messages = list(rows.scalars().all())
    assert len(task_messages) == 2
    metadata = json.loads(task_messages[0].metadata_json)
    result = metadata["orchestratorTaskResult"]
    assert result["executionId"] == data["executionId"]
    assert result["planId"] == "plan_exec_001"
    assert result["taskId"] == "T1"
    assert result["assignedAgentId"] == "agent_backend_exec"

    visible_messages = (await test_client.get(f"/api/sessions/{session_id}/messages")).json()
    assert not any(message["contentType"] == "orchestrator_task_result" for message in visible_messages)


@pytest.mark.asyncio
async def test_execute_plan_simulates_parallel_ready_tasks(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    plan = _valid_plan()
    plan["tasks"] = [
        {
            "task_id": "T1",
            "title": "后端建模",
            "goal": "完成领域模型",
            "required_skills": ["backend"],
            "assigned_agent_id": "agent_backend_exec",
            "assigned_agent_name": "后端专家",
            "depends_on": [],
        },
        {
            "task_id": "T2",
            "title": "前端草图",
            "goal": "完成页面草图",
            "required_skills": ["frontend"],
            "assigned_agent_id": "agent_frontend_exec",
            "assigned_agent_name": "前端专家",
            "depends_on": [],
        },
        {
            "task_id": "T3",
            "title": "联调验收",
            "goal": "完成验收",
            "required_skills": ["backend", "frontend"],
            "assigned_agent_id": "agent_backend_exec",
            "assigned_agent_name": "后端专家",
            "depends_on": ["T1", "T2"],
        },
    ]

    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": plan,
    })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "running"

    data = await _wait_execution_completed(test_client, data["executionId"])
    assert data["status"] == "completed"
    batch_events = [event for event in data["events"] if event["type"] == "scheduler_batch_running"]
    assert batch_events[0]["taskIds"] == ["T1", "T2"]
    assert batch_events[1]["taskIds"] == ["T3"]
    started_events = [event for event in data["events"] if event["type"] == "task_started"]
    assert [event["taskId"] for event in started_events[:2]] == ["T1", "T2"]
    assert [task["status"] for task in data["tasks"]] == ["completed", "completed", "completed"]


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
