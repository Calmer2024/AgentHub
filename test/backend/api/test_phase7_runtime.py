import json

import pytest
from sqlalchemy import select


async def _collect_sse(resp):
    events = []
    async for line in resp.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest.mark.asyncio
async def test_chat_creates_run_task_process_and_completes(test_client, test_session):
    resp = await test_client.post(
        f"/api/sessions/{test_session}/chat",
        json={"content": "Hello"},
    )
    assert resp.status_code == 200
    events = await _collect_sse(resp)

    assert any(event.get("type") == "run.started" for event in events)
    assert any(
        event.get("type") == "run.status_changed" and event.get("status") == "completed"
        for event in events
    )

    runs_resp = await test_client.get(f"/api/sessions/{test_session}/runs")
    assert runs_resp.status_code == 200
    runs = runs_resp.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "completed"
    assert runs[0]["currentMessageId"]

    tasks_resp = await test_client.get(f"/api/runs/{runs[0]['id']}/tasks")
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "completed"
    assert tasks[0]["messageId"] == runs[0]["currentMessageId"]

    processes_resp = await test_client.get(f"/api/runs/{runs[0]['id']}/processes")
    assert processes_resp.status_code == 200
    processes = processes_resp.json()
    assert len(processes) == 1
    assert processes[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_completed_run_cancel_is_idempotent(test_client, test_session):
    await test_client.post(
        f"/api/sessions/{test_session}/chat",
        json={"content": "Hello"},
    )
    runs = (await test_client.get(f"/api/sessions/{test_session}/runs")).json()

    first = await test_client.post(
        f"/api/runs/{runs[0]['id']}/cancel",
        json={"reason": "late click"},
    )
    second = await test_client.post(
        f"/api/runs/{runs[0]['id']}/cancel",
        json={"reason": "late click again"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "completed"
    assert second.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_cancelled_run_is_not_overwritten_by_late_process_completion(db_session, test_session):
    from app.models import RunProcess
    from app.models.session import Session
    from app.services.run_service import RunService

    session = await db_session.get(Session, test_session)
    service = RunService(db_session)
    run = await service.create_run(session, mode="single")
    task = await service.create_task(run, agent_id=session.agent_config_id, name="primary")
    await service.bind_process(
        run_id=run.id,
        task_id=task.id,
        session_id=test_session,
        agent_id=session.agent_config_id,
        message_id=None,
        process_id="late-process",
        snapshot={"pid": 123, "executable": "fixture", "cwd": "workspace"},
    )

    cancelled = await service.cancel_run(run.id, "stop")
    assert cancelled.status == "cancelled"

    await service.complete_process("late-process", exit_code=1)
    run_after = await service.mark_run_status(run.id, "failed")
    process = (await db_session.execute(
        select(RunProcess).where(RunProcess.process_id == "late-process")
    )).scalars().first()

    assert run_after.status == "cancelled"
    assert process.status == "cancelled"
    assert process.exit_code == 1


@pytest.mark.asyncio
async def test_cancel_run_appends_visible_cancel_message(db_session, test_session):
    from app.models import Message
    from app.models.session import Session
    from app.services.run_service import RunService

    session = await db_session.get(Session, test_session)
    service = RunService(db_session)
    run = await service.create_run(session, mode="single")
    await service.create_task(run, agent_id=session.agent_config_id, name="primary")

    await service.cancel_run(run.id, "人工验收停止")

    messages = (await db_session.execute(
        select(Message).where(Message.session_id == test_session, Message.source_name == "运行控制")
    )).scalars().all()
    assert len(messages) == 1
    assert "本次运行已中止" in messages[0].content
    assert "人工验收停止" in messages[0].content


@pytest.mark.asyncio
async def test_approval_checkpoint_created_from_explicit_approval_request(test_client, test_session):
    resp = await test_client.post(
        f"/api/sessions/{test_session}/chat",
        json={"content": "Hello，需要审批后确认继续"},
    )
    events = await _collect_sse(resp)

    approval_events = [event for event in events if event.get("type") == "approval.created"]
    assert approval_events

    approvals_resp = await test_client.get(f"/api/sessions/{test_session}/approvals")
    assert approvals_resp.status_code == 200
    approvals = approvals_resp.json()
    assert len(approvals) == 1
    assert approvals[0]["status"] == "pending_review"
    assert approvals[0]["messageId"]

    approve_resp = await test_client.post(f"/api/approvals/{approvals[0]['id']}/approve", json={})
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    runs = (await test_client.get(f"/api/sessions/{test_session}/runs")).json()
    assert runs[0]["status"] == "completed"

    repeat_resp = await test_client.post(f"/api/approvals/{approvals[0]['id']}/reject", json={"reason": "重来"})
    assert repeat_resp.status_code == 409


@pytest.mark.asyncio
async def test_system_health_returns_system_snapshot_without_context(test_client):
    resp = await test_client.get("/api/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall"] in {"warning", "error"}
    assert "blockingReasons" in data
    assert not _contains_secret(data)


@pytest.mark.asyncio
async def test_system_health_blocks_missing_workspace(test_client, db_session, test_agent):
    from app.models import Project, Session

    project = Project(
        id="missing-workspace-project",
        name="缺失目录",
        workspace_path="D:/definitely/not/a/real/agenthub/workspace",
        status="ready",
    )
    session = Session(
        id="missing-workspace-session",
        title="缺失目录会话",
        project_id=project.id,
        agent_config_id=test_agent.id,
    )
    db_session.add(project)
    db_session.add(session)
    await db_session.commit()

    resp = await test_client.get("/api/system/health?sessionId=missing-workspace-session")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall"] == "error"
    assert any("项目目录不存在" in reason for reason in data["blockingReasons"])


def _contains_secret(value) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return "sk-test-dummy-key" in text or "api_key" in text
