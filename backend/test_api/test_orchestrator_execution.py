import json
import asyncio
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AgentConfig, Message, Project, Session
from app.services.orchestrator_execution import execution_registry

BACKEND_ROOT = Path(__file__).resolve().parents[1]


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
    cli = _ensure_fixture_cli()
    return AgentConfig(
        id=agent_id,
        name=name,
        description=name,
        system_prompt="",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable=sys.executable,
        init_args=json.dumps([str(cli)]),
        env_vars="{}",
        primary_skill=primary_skill,
        auxiliary_skills=json.dumps(["workspace_editing"], ensure_ascii=False),
        context_policy="workspace_coding",
        is_active=True,
    )


def _ensure_fixture_cli() -> Path:
    script = BACKEND_ROOT / ".test-bin" / "orchestrator_task_fixture.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "import os, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "cwd = os.getcwd().replace('\\\\', '/')\n"
        "with open('HANDOFF.md', 'w', encoding='utf-8') as f:\n"
        "    f.write('# 任务交接\\n\\n已在任务工作包内写入交接产物。\\n')\n"
        "sys.stdout.buffer.write(f'真实任务输出：cwd={cwd}；已写 HANDOFF.md。'.encode('utf-8'))\n"
        "sys.stdout.buffer.flush()\n",
        encoding="utf-8",
    )
    return script


async def _seed_session_with_agents(db_session):
    workspace_path = Path(__file__).resolve().parents[1] / ".test-workspaces" / str(uuid.uuid4())
    workspace_path.mkdir(parents=True, exist_ok=True)
    project = Project(
        id=str(uuid.uuid4()),
        name="调度执行测试项目",
        workspace_path=str(workspace_path),
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
    assert completed["status"] == "completed", completed["events"][-1]
    assert completed["completedAt"] is not None
    assert [task["status"] for task in completed["tasks"]] == ["completed", "completed"]
    assert completed["tasks"][0]["runnerType"] == "cli"
    assert completed["tasks"][0]["visibleMessageId"]
    assert "真实任务输出" in completed["tasks"][0]["summary"]
    task_workspace = Path(completed["tasks"][0]["taskWorkspacePath"])
    task_parts = task_workspace.parts
    assert ".agenthub" in task_parts
    agenthub_index = task_parts.index(".agenthub")
    assert task_parts[agenthub_index:agenthub_index + 5] == (
        ".agenthub", "executions", data["executionId"], "tasks", "T1",
    )
    assert task_workspace.name == "T1"
    assert (task_workspace / "TASK.md").exists()
    assert (task_workspace / "HANDOFF.md").exists()
    assert completed["tasks"][1]["runnerType"] == "cli"
    assert completed["tasks"][1]["visibleMessageId"]
    assert all(task["resultMessageId"] for task in completed["tasks"])
    assert completed["tasks"][0]["upstreamResults"] == []
    assert completed["tasks"][1]["upstreamResults"] == [{
        "taskId": "T1",
        "title": "实现后端 API",
        "summary": completed["tasks"][0]["summary"],
        "resultMessageId": completed["tasks"][0]["resultMessageId"],
        "assignedAgentId": "agent_backend_exec",
        "assignedAgentName": "后端专家",
    }]

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
    assert result["runnerType"] == "cli"
    assert result["visibleMessageId"] == completed["tasks"][0]["visibleMessageId"]
    second_metadata = json.loads(task_messages[1].metadata_json)
    second_result = second_metadata["orchestratorTaskResult"]
    assert second_result["taskId"] == "T2"
    assert second_result["upstreamResults"][0]["taskId"] == "T1"
    assert second_result["upstreamResults"][0]["resultMessageId"] == completed["tasks"][0]["resultMessageId"]

    visible_messages = (await test_client.get(f"/api/sessions/{session_id}/messages")).json()
    assert not any(message["contentType"] == "orchestrator_task_result" for message in visible_messages)
    visible = next(
        message for message in visible_messages
        if message["id"] == completed["tasks"][0]["visibleMessageId"]
    )
    assert visible["metadata"]["executionTrace"]["status"] == "completed"
    assert visible["metadata"]["orchestratorTaskMessage"]["taskId"] == "T1"
    assert visible["metadata"]["taskWorkspacePath"] == str(task_workspace)
    assert visible["metadata"]["orchestratorTaskMessage"]["taskWorkspacePath"] == str(task_workspace)


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
    assert data["status"] == "completed", data["events"][-1]
    batch_events = [event for event in data["events"] if event["type"] == "scheduler_batch_running"]
    assert batch_events[0]["taskIds"] == ["T1", "T2"]
    assert batch_events[1]["taskIds"] == ["T3"]
    started_events = [event for event in data["events"] if event["type"] == "task_started"]
    assert [event["taskId"] for event in started_events[:2]] == ["T1", "T2"]
    assert [task["status"] for task in data["tasks"]] == ["completed", "completed", "completed"]
    assert [task["runnerType"] for task in data["tasks"]] == ["cli", "cli", "cli"]
    assert all(task["visibleMessageId"] for task in data["tasks"])
    t3 = next(task for task in data["tasks"] if task["taskId"] == "T3")
    assert [item["taskId"] for item in t3["upstreamResults"]] == ["T1", "T2"]


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
async def test_get_execution_falls_back_to_persisted_message_snapshot(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    execution = execution_registry.create_execution(
        session_id=session_id,
        plan=_valid_plan(),
        active_agent_ids={"agent_frontend_exec", "agent_backend_exec"},
    )
    execution_id = execution["executionId"]
    db_session.add(Message(
        id=f"msg_approval_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        role="assistant",
        content="已确认计划，创建执行。",
        content_type="text",
        agent_name="Orchestrator 调度器",
        source_type="agent",
        source_name="Orchestrator 调度器",
        metadata_json=json.dumps({"orchestratorExecution": execution}, ensure_ascii=False),
    ))
    await db_session.commit()
    execution_registry._executions.pop(execution_id, None)

    res = await test_client.get(f"/api/orchestrator/executions/{execution_id}")

    assert res.status_code == 200
    data = res.json()
    assert data["executionId"] == execution_id
    assert data["status"] == execution["status"]


@pytest.mark.asyncio
async def test_execute_plan_rejects_unknown_session(test_client):
    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": "missing-session",
        "normalizedPlan": _valid_plan(),
    })

    assert res.status_code == 404
