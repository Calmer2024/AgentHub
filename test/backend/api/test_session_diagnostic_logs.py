import json
import uuid

import pytest

from app.models import Message, Run, RunProcess, RunTask


pytestmark = pytest.mark.asyncio


async def test_session_diagnostic_logs_aggregate_runtime_entities_and_redact_trace(
    test_client, db_session, test_session, test_agent,
):
    user_message = Message(
        id=str(uuid.uuid4()),
        session_id=test_session,
        role="user",
        content="请排查 token=super-secret-token",
        source_type="user",
        source_name="用户",
        metadata_json=json.dumps({"executionTrace": {"items": ["旧轨迹"]}}),
    )
    run = Run(
        id=str(uuid.uuid4()),
        session_id=test_session,
        mode="orchestrated",
        status="running",
        current_message_id=user_message.id,
        metadata_json="{}",
    )
    task = RunTask(
        id=str(uuid.uuid4()),
        run_id=run.id,
        session_id=test_session,
        agent_id=test_agent.id,
        name="实现日志面板",
        role="executor",
        status="running",
        depends_on_json="[]",
        metadata_json="{}",
    )
    process = RunProcess(
        id=str(uuid.uuid4()),
        run_id=run.id,
        task_id=task.id,
        session_id=test_session,
        agent_id=test_agent.id,
        message_id=user_message.id,
        process_id="cli-test-process",
        executable="codex",
        cwd="D:/workspace",
        status="running",
    )
    db_session.add_all([user_message, run, task, process])
    await db_session.commit()

    response = await test_client.get(f"/api/sessions/{test_session}/diagnostic-logs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["id"] == test_session
    assert payload["counts"] == {
        "entries": 5,
        "messages": 1,
        "runs": 1,
        "tasks": 1,
        "processes": 1,
        "artifacts": 0,
        "plans": 0,
    }
    categories = {entry["category"] for entry in payload["entries"]}
    assert {"session", "message", "run", "task", "process"} <= categories
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "super-secret-token" not in serialized
    assert "旧轨迹" not in serialized
    assert "由独立诊断日志替代" in serialized
