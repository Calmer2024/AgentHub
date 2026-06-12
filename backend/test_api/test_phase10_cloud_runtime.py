import asyncio
import json
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.timezone import china_now
from app.models import RuntimeRun, Sandbox, User
from app.services.quota_service import QuotaService


OWNER = {
    "X-AgentHub-User-Email": "phase10-owner@example.com",
    "X-AgentHub-User-Name": "Phase10 Owner",
}


def _events(text: str) -> list[dict]:
    items: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block.startswith("data: "):
            continue
        items.append(json.loads(block[6:]))
    return items


def _phase10_cli() -> Path:
    script = Path(__file__).resolve().parents[1] / ".test-bin" / "phase10_cloud_cli.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "import os, sys, time\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "with open('.agenthub-phase10-stdin.txt', 'w', encoding='utf-8') as f:\n"
        "    f.write(data)\n"
        "secret = os.environ.get('PHASE10_TOKEN', '')\n"
        "if secret:\n"
        "    sys.stdout.write(f'secret={secret}\\n')\n"
        "    sys.stdout.flush()\n"
        "if 'WRITE_HTML_ARTIFACT' in data:\n"
        "    with open('index.html', 'w', encoding='utf-8') as f:\n"
        "        f.write('<!doctype html><html><body><main>Phase10 Cloud Artifact</main></body></html>')\n"
        "    sys.stdout.write('created index.html\\n')\n"
        "    sys.exit(0)\n"
        "if 'SLEEP' in data:\n"
        "    sys.stdout.write('sleep started\\n')\n"
        "    sys.stdout.flush()\n"
        "    time.sleep(10)\n"
        "    sys.exit(0)\n"
        "sys.stdout.write('cloud ok\\n')\n",
        encoding="utf-8",
    )
    return script


def _cloud_group_worker_cli() -> Path:
    script = Path(__file__).resolve().parents[1] / ".test-bin" / "phase10_cloud_group_worker.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "import os, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "if 'WRITE_HTML_ARTIFACT' in data:\n"
        "    with open('index.html', 'w', encoding='utf-8') as f:\n"
        "        f.write('<!doctype html><html><body><main>Cloud Group Artifact</main></body></html>')\n"
        "    sys.stdout.write('created cloud group index.html\\n')\n"
        "else:\n"
        "    sys.stdout.write('cloud group direct dialog reply\\n')\n",
        encoding="utf-8",
    )
    return script


def _cloud_group_orchestrator_cli() -> Path:
    script = Path(__file__).resolve().parents[1] / ".test-bin" / "phase10_cloud_group_orchestrator.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "import json, os, re, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "match = re.search(r'\"id\"\\s*:\\s*\"([^\"]+)\"', data)\n"
        "selected = match.group(1) if match else ''\n"
        "payload = {\n"
        "    'route_type': 'direct_dialog',\n"
        "    'reply': '我先请群成员出来和你连续对齐。',\n"
        "    'reason': '用户想与具体成员进行连续沟通。',\n"
        "    'selected_agent_ids': [selected] if selected else [],\n"
        "    'task_brief': '云端群聊直接对话验证',\n"
        "    'confidence': 0.95,\n"
        "    'requires_approval': False,\n"
        "    'risk_level': 'low',\n"
        "}\n"
        "sys.stdout.write(json.dumps(payload, ensure_ascii=False))\n",
        encoding="utf-8",
    )
    return script


def _cloud_group_plan_worker_cli() -> Path:
    script = Path(__file__).resolve().parents[1] / ".test-bin" / "phase10_cloud_group_plan_worker.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "import os, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "with open('.agenthub-plan-worker-stdin.txt', 'w', encoding='utf-8') as f:\n"
        "    f.write(data)\n"
        "if 'APPROVED_PLAN_ARTIFACT' in data or 'approved-plan.html' in data:\n"
        "    with open('approved-plan.html', 'w', encoding='utf-8') as f:\n"
        "        f.write('<!doctype html><html><body><main>Cloud Plan Approval Artifact</main></body></html>')\n"
        "    sys.stdout.write('cloud approved plan task completed\\n')\n"
        "else:\n"
        "    sys.stdout.write('cloud plan worker reply\\n')\n",
        encoding="utf-8",
    )
    return script


def _cloud_group_plan_orchestrator_cli(worker: dict) -> Path:
    script = Path(__file__).resolve().parents[1] / ".test-bin" / "phase10_cloud_group_plan_orchestrator.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "import json, os, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "if '确认' in data or '开始执行' in data or 'approve_plan' in data:\n"
        "    payload = {\n"
        "        'action': 'approve_plan',\n"
        "        'target_plan_id': 'cloud_plan_approval_001',\n"
        "        'reason': '用户明确确认执行',\n"
        "    }\n"
        "else:\n"
        "    payload = {\n"
        "        'plan_id': 'cloud_plan_approval_001',\n"
        "        'tasks': [{\n"
        "            'task_id': 'T1',\n"
        "            'title': '生成云端计划批准产物',\n"
        "            'goal': 'APPROVED_PLAN_ARTIFACT: 生成 approved-plan.html 并输出完成信息',\n"
        "            'required_skills': ['frontend'],\n"
        f"            'assigned_agent_id': {worker['id']!r},\n"
        f"            'assigned_agent_name': {worker['name']!r},\n"
        "            'depends_on': [],\n"
        "        }],\n"
        "    }\n"
        "sys.stdout.write(json.dumps(payload, ensure_ascii=False))\n",
        encoding="utf-8",
    )
    return script


async def _create_cloud_session(test_client) -> tuple[dict, dict, dict]:
    agent = await test_client.post(
        "/api/agents",
        json={
            "name": "Phase10 Fixture Agent",
            "description": "Phase 10 fixture",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [str(_phase10_cli())],
            "systemPrompt": "你是 Phase 10 云端 runtime 测试 Agent。",
        },
    )
    assert agent.status_code == 201, agent.text
    project = await test_client.post(
        "/api/projects",
        json={"name": "Phase10 Cloud Runtime", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "Phase10 云端会话",
            "projectId": project.json()["id"],
            "agentConfigId": agent.json()["id"],
        },
        headers=OWNER,
    )
    assert session.status_code == 201, session.text
    return agent.json(), project.json(), session.json()


async def _create_cloud_group_session(test_client) -> tuple[dict, dict, dict, dict]:
    worker = await test_client.post(
        "/api/agents",
        json={
            "name": "Phase10 Cloud Group Worker",
            "description": "Phase 10 cloud group worker",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [str(_cloud_group_worker_cli())],
            "systemPrompt": "你是云端群聊执行 Agent。",
        },
        headers=OWNER,
    )
    assert worker.status_code == 201, worker.text
    orchestrator = await test_client.post(
        "/api/agents",
        json={
            "name": "Phase10 Cloud Group Orchestrator",
            "description": "Phase 10 cloud group orchestrator",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [str(_cloud_group_orchestrator_cli())],
            "systemPrompt": "你是云端群聊调度器。",
            "primarySkill": "orchestrator_planner",
            "contextPolicy": "planning_only",
        },
        headers=OWNER,
    )
    assert orchestrator.status_code == 201, orchestrator.text
    project = await test_client.post(
        "/api/projects",
        json={"name": "Phase10 Cloud Group Runtime", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "Phase10 云端群聊",
            "mode": "group",
            "projectId": project.json()["id"],
            "agentConfigIds": [worker.json()["id"], orchestrator.json()["id"]],
        },
        headers=OWNER,
    )
    assert session.status_code == 201, session.text
    return worker.json(), orchestrator.json(), project.json(), session.json()


async def _create_cloud_group_plan_session(test_client) -> tuple[dict, dict, dict, dict]:
    worker = await test_client.post(
        "/api/agents",
        json={
            "name": "Phase10 Cloud Plan Worker",
            "description": "Phase 10 cloud plan worker",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [str(_cloud_group_plan_worker_cli())],
            "systemPrompt": "你是云端计划任务执行 Agent。",
        },
        headers=OWNER,
    )
    assert worker.status_code == 201, worker.text
    orchestrator = await test_client.post(
        "/api/agents",
        json={
            "name": "Phase10 Cloud Plan Orchestrator",
            "description": "Phase 10 cloud plan orchestrator",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [str(_cloud_group_plan_orchestrator_cli(worker.json()))],
            "systemPrompt": "你是云端群聊计划调度器。",
            "primarySkill": "orchestrator_planner",
            "contextPolicy": "planning_only",
        },
        headers=OWNER,
    )
    assert orchestrator.status_code == 201, orchestrator.text
    project = await test_client.post(
        "/api/projects",
        json={"name": "Phase10 Cloud Plan Runtime", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "Phase10 云端计划批准群聊",
            "mode": "group",
            "projectId": project.json()["id"],
            "agentConfigIds": [worker.json()["id"], orchestrator.json()["id"]],
        },
        headers=OWNER,
    )
    assert session.status_code == 201, session.text
    return worker.json(), orchestrator.json(), project.json(), session.json()


@pytest.mark.asyncio
async def test_cloud_chat_creates_sandbox_artifact_logs_and_persistent_snapshot(test_client):
    _agent, project, session = await _create_cloud_session(test_client)
    secret = await test_client.post(
        "/api/secrets",
        json={"name": "PHASE10_TOKEN", "value": "super-secret-value"},
        headers=OWNER,
    )
    assert secret.status_code == 201, secret.text
    assert secret.json()["name"] == "PHASE10_TOKEN"

    response = await test_client.post(
        f"/api/sessions/{session['id']}/chat",
        json={"content": "WRITE_HTML_ARTIFACT and print secret"},
        headers=OWNER,
    )

    assert response.status_code == 200, response.text
    events = _events(response.text)
    types = [event.get("type") for event in events]
    assert "run.started" in types
    assert "sandbox.ready" in types
    assert "workspace.sync.started" in types
    assert "workspace.sync.completed" in types
    assert "sandbox.disposed" in types
    assert "agent.process.started" in types
    assert "agent.output" in types
    assert "artifact.created" in types
    assert events[-1]["done"] is True
    assert "super-secret-value" not in response.text
    assert "[REDACTED]" in response.text

    run_started = next(event for event in events if event.get("type") == "run.started")
    run_id = run_started["runId"]
    sandbox_id = run_started["run"]["metadata"]["sandboxId"]
    logs = await test_client.get(f"/api/runs/{run_id}/logs", headers=OWNER)
    assert logs.status_code == 200, logs.text
    log_text = "\n".join(chunk["text"] for chunk in logs.json()["chunks"])
    assert "super-secret-value" not in log_text
    assert "process completed" in log_text
    assert "created index.html" not in log_text

    messages = await test_client.get(f"/api/sessions/{session['id']}/messages", headers=OWNER)
    assert messages.status_code == 200
    assert "super-secret-value" not in messages.text
    assert "[REDACTED]" in messages.text
    assistant_message = next(item for item in messages.json() if item["role"] == "assistant")
    metadata = assistant_message["metadata"]
    assert metadata["workspacePath"].startswith("cloud://agenthub/workspaces/")
    assert metadata["cloudRuntime"]["provider"] == "local_dev"
    assert metadata["runStatus"] == "completed"
    assert metadata["workspaceSync"]["changedFiles"]
    assert "D:\\" not in json.dumps(metadata)

    artifacts = await test_client.get(f"/api/sessions/{session['id']}/artifacts", headers=OWNER)
    assert artifacts.status_code == 200, artifacts.text
    assert any(item["filePath"] == "index.html" for item in artifacts.json())

    stopped = await test_client.post(
        f"/api/sandboxes/{sandbox_id}/stop",
        json={"reason": "验收停止"},
        headers=OWNER,
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "disposed"

    sandbox = await test_client.get(f"/api/sandboxes/{sandbox_id}", headers=OWNER)
    assert sandbox.status_code == 200, sandbox.text
    assert sandbox.json()["disposedAt"]

    snapshot = await test_client.post(
        f"/api/workspaces/{project['workspaceId']}/snapshots",
        json={"label": "sandbox stopped 后"},
        headers=OWNER,
    )
    assert snapshot.status_code == 201, snapshot.text


@pytest.mark.asyncio
async def test_cloud_group_chat_uses_desktop_direct_dialog_contract(test_client):
    worker, orchestrator, _project, session = await _create_cloud_group_session(test_client)

    response = await test_client.post(
        f"/api/sessions/{session['id']}/chat",
        json={"content": "我想先和执行成员单独连续对齐需求，不要直接进入 DAG。"},
        headers=OWNER,
    )

    assert response.status_code == 200, response.text
    events = _events(response.text)
    types = [event.get("type") for event in events]
    assert "run.started" in types
    assert "orchestrator.steward_decision" in types
    assert "group.direct_dialog_started" in types
    assert "group.direct_dialog_waiting" in types
    assert "orchestrator.route" not in types
    assert "orchestrator.task_started" not in types
    agent_starts = [event for event in events if event.get("type") == "agent.start"]
    assert agent_starts[0]["agentId"] == orchestrator["id"]
    assert any(
        event["agentId"] == worker["id"] and event.get("task") == "direct dialog"
        for event in agent_starts
    )

    messages = await test_client.get(f"/api/sessions/{session['id']}/messages", headers=OWNER)
    assert messages.status_code == 200, messages.text
    direct_message = next(
        item for item in messages.json()
        if item["role"] == "assistant" and item["sourceId"] == worker["id"]
    )
    metadata = direct_message["metadata"]
    assert metadata["groupDialog"]["status"] == "awaiting_user_input"
    assert metadata["workspacePath"].startswith("cloud://agenthub/workspaces/")
    assert "artifactWorkspacePath" not in metadata
    assert "D:\\" not in json.dumps(metadata)


@pytest.mark.asyncio
async def test_cloud_group_chat_scans_agent_artifacts_without_path_leak(test_client):
    worker, _orchestrator, _project, session = await _create_cloud_group_session(test_client)

    response = await test_client.post(
        f"/api/sessions/{session['id']}/chat",
        json={
            "content": f"@{worker['name']} WRITE_HTML_ARTIFACT",
            "mentions": [worker["id"]],
        },
        headers=OWNER,
    )

    assert response.status_code == 200, response.text
    events = _events(response.text)
    types = [event.get("type") for event in events]
    assert "agent.process.started" in types
    assert "artifact.created" in types
    assert "artifact.scan.completed" in types

    artifacts = await test_client.get(f"/api/sessions/{session['id']}/artifacts", headers=OWNER)
    assert artifacts.status_code == 200, artifacts.text
    assert any(item["filePath"] == "index.html" for item in artifacts.json())

    messages = await test_client.get(f"/api/sessions/{session['id']}/messages", headers=OWNER)
    assert messages.status_code == 200, messages.text
    assistant_message = next(
        item for item in messages.json()
        if item["role"] == "assistant" and item["sourceId"] == worker["id"]
    )
    metadata = assistant_message["metadata"]
    assert metadata["workspacePath"].startswith("cloud://agenthub/workspaces/")
    assert "artifactWorkspacePath" not in metadata
    assert "D:\\" not in json.dumps(metadata)


@pytest.mark.asyncio
async def test_cloud_group_plan_approval_executes_cloud_task_and_scans_artifacts(test_client):
    worker, orchestrator, _project, session = await _create_cloud_group_plan_session(test_client)

    draft = await test_client.post(
        f"/api/sessions/{session['id']}/chat",
        json={
            "content": f"@{orchestrator['name']} 请制定一个需要执行的计划。",
            "mentions": [orchestrator["id"]],
        },
        headers=OWNER,
    )
    assert draft.status_code == 200, draft.text
    draft_events = _events(draft.text)
    assert "agent.start" in [event.get("type") for event in draft_events]
    assert any(event.get("done") and event.get("messageId") for event in draft_events)

    approval = await test_client.post(
        f"/api/sessions/{session['id']}/chat",
        json={
            "content": f"@{orchestrator['name']} 确认，开始执行。",
            "mentions": [orchestrator["id"]],
        },
        headers=OWNER,
    )
    assert approval.status_code == 200, approval.text
    approval_events = _events(approval.text)
    execution_event = next(
        event for event in approval_events
        if event.get("type") == "orchestrator.plan_execution_created"
    )
    execution_id = execution_event["executionId"]

    completed = None
    for _ in range(60):
        response = await test_client.get(f"/api/orchestrator/executions/{execution_id}", headers=OWNER)
        assert response.status_code == 200, response.text
        body = response.json()
        if body.get("status") in {"completed", "failed", "cancelled"}:
            completed = body
            break
        await asyncio.sleep(0.05)
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["tasks"][0]["runnerType"] == "cli"
    assert completed["tasks"][0]["visibleMessageId"]

    artifacts = await test_client.get(f"/api/sessions/{session['id']}/artifacts", headers=OWNER)
    assert artifacts.status_code == 200, artifacts.text
    assert any(item["filePath"] == "approved-plan.html" for item in artifacts.json())

    messages = await test_client.get(f"/api/sessions/{session['id']}/messages", headers=OWNER)
    assert messages.status_code == 200, messages.text
    worker_message = next(
        item for item in messages.json()
        if item["role"] == "assistant" and item["sourceId"] == worker["id"]
    )
    metadata = worker_message["metadata"]
    assert metadata["workspacePath"].startswith("cloud://agenthub/workspaces/")
    assert "artifactWorkspacePath" not in metadata
    assert "D:\\" not in json.dumps(metadata)


@pytest.mark.asyncio
async def test_sandbox_quota_limits_concurrent_sandboxes(test_client):
    _agent, project, _session = await _create_cloud_session(test_client)

    first = await test_client.post(
        "/api/sandboxes",
        json={"workspaceId": project["workspaceId"]},
        headers=OWNER,
    )
    second = await test_client.post(
        "/api/sandboxes",
        json={"workspaceId": project["workspaceId"]},
        headers=OWNER,
    )
    third = await test_client.post(
        "/api/sandboxes",
        json={"workspaceId": project["workspaceId"]},
        headers=OWNER,
    )
    fourth = await test_client.post(
        "/api/sandboxes",
        json={"workspaceId": project["workspaceId"]},
        headers=OWNER,
    )
    fifth = await test_client.post(
        "/api/sandboxes",
        json={"workspaceId": project["workspaceId"]},
        headers=OWNER,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert third.status_code == 201, third.text
    assert fourth.status_code == 201, fourth.text
    assert fifth.status_code == 409
    quota = await test_client.get("/api/quotas/me", headers=OWNER)
    assert quota.status_code == 200
    assert quota.json()["concurrentRunsLimit"] == 4
    assert quota.json()["diskMbLimit"] == 1024


@pytest.mark.asyncio
async def test_quota_ignores_other_users_active_cloud_runs(test_client, db_session):
    other = {
        "X-AgentHub-User-Email": "phase10-other@example.com",
        "X-AgentHub-User-Name": "Phase10 Other",
    }
    _owner_agent, _owner_project, _owner_session = await _create_cloud_session(test_client)
    other_agent, _other_project, other_session = await _create_cloud_session_for(test_client, other)
    owner = await _user_by_email(db_session, OWNER["X-AgentHub-User-Email"])
    other_user = await _user_by_email(db_session, other["X-AgentHub-User-Email"])
    now = china_now()
    db_session.add(RuntimeRun(
        id=str(uuid.uuid4()),
        session_id=other_session["id"],
        agent_id=other_agent["id"],
        actor_user_id=other_user.id,
        runtime_mode="cloud",
        status="running",
        queued_at=now,
        started_at=now,
    ))
    await db_session.commit()

    assert await QuotaService(db_session).active_runtime_count(owner) == 0
    assert await QuotaService(db_session).active_runtime_count(other_user) == 1


@pytest.mark.asyncio
async def test_quota_reaps_orphaned_active_cloud_runs(test_client, db_session):
    agent, _project, _session = await _create_cloud_session(test_client)
    owner = await _user_by_email(db_session, OWNER["X-AgentHub-User-Email"])
    old = china_now() - timedelta(seconds=9999)
    orphan_id = str(uuid.uuid4())
    db_session.add(RuntimeRun(
        id=orphan_id,
        session_id="missing-session",
        agent_id=agent["id"],
        actor_user_id=owner.id,
        runtime_mode="cloud",
        status="running",
        queued_at=old,
        started_at=old,
    ))
    await db_session.commit()

    service = QuotaService(db_session)
    assert await service.active_runtime_count(owner) == 0
    assert await service.reap_stale_active_runs(owner) == 1
    orphan = await db_session.get(RuntimeRun, orphan_id)
    assert orphan.status == "timed_out"
    assert orphan.finished_at is not None


@pytest.mark.asyncio
async def test_quota_reaps_prestart_active_cloud_runs(test_client, db_session):
    agent, _project, session = await _create_cloud_session(test_client)
    owner = await _user_by_email(db_session, OWNER["X-AgentHub-User-Email"])
    service = QuotaService(db_session)
    old = china_now() - timedelta(seconds=service.prestart_seconds_limit + 5)
    run_id = str(uuid.uuid4())
    db_session.add(RuntimeRun(
        id=run_id,
        session_id=session["id"],
        agent_id=agent["id"],
        actor_user_id=owner.id,
        runtime_mode="cloud",
        status="running",
        queued_at=old,
        started_at=old,
    ))
    await db_session.commit()

    assert await service.active_runtime_count(owner) == 1
    assert await service.reap_stale_active_runs(owner) == 1
    runtime_run = await db_session.get(RuntimeRun, run_id)
    assert runtime_run.status == "timed_out"
    assert runtime_run.finished_at is not None
    assert "CLI 进程启动前" in runtime_run.error_summary


@pytest.mark.asyncio
async def test_quota_counts_team_project_runs_by_actor_user(test_client, db_session):
    member_headers = {
        "X-AgentHub-User-Email": "phase10-team-member@example.com",
        "X-AgentHub-User-Name": "Phase10 Team Member",
    }
    team = await test_client.post("/api/teams", json={"name": "Phase10 Runtime Team"}, headers=OWNER)
    assert team.status_code == 201, team.text
    add_member = await test_client.post(
        f"/api/teams/{team.json()['id']}/members",
        json={"email": member_headers["X-AgentHub-User-Email"], "role": "member"},
        headers=OWNER,
    )
    assert add_member.status_code == 201, add_member.text
    agent = await test_client.post(
        "/api/agents",
        json={
            "name": "Phase10 Team Runtime Agent",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [str(_phase10_cli())],
        },
        headers=OWNER,
    )
    assert agent.status_code == 201, agent.text
    project = await test_client.post(
        "/api/projects",
        json={
            "name": "Phase10 Team Runtime Project",
            "workspaceMode": "cloud",
            "teamId": team.json()["id"],
        },
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "Phase10 团队云端会话",
            "projectId": project.json()["id"],
            "agentConfigId": agent.json()["id"],
        },
        headers=OWNER,
    )
    assert session.status_code == 201, session.text
    owner = await _user_by_email(db_session, OWNER["X-AgentHub-User-Email"])
    member = await _user_by_email(db_session, member_headers["X-AgentHub-User-Email"])
    now = china_now()
    db_session.add(RuntimeRun(
        id=str(uuid.uuid4()),
        session_id=session.json()["id"],
        agent_id=agent.json()["id"],
        actor_user_id=member.id,
        runtime_mode="cloud",
        status="running",
        queued_at=now,
        started_at=now,
    ))
    await db_session.commit()

    assert await QuotaService(db_session).active_runtime_count(owner) == 0
    assert await QuotaService(db_session).active_runtime_count(member) == 1


@pytest.mark.asyncio
async def test_sandbox_quota_counts_by_actor_user(test_client, db_session):
    other = {
        "X-AgentHub-User-Email": "phase10-sandbox-other@example.com",
        "X-AgentHub-User-Name": "Phase10 Sandbox Other",
    }
    _owner_agent, _owner_project, _owner_session = await _create_cloud_session(test_client)
    _other_agent, other_project, _other_session = await _create_cloud_session_for(test_client, other)
    owner = await _user_by_email(db_session, OWNER["X-AgentHub-User-Email"])
    other_user = await _user_by_email(db_session, other["X-AgentHub-User-Email"])
    now = china_now()
    db_session.add(Sandbox(
        id=str(uuid.uuid4()),
        workspace_id=other_project["workspaceId"],
        actor_user_id=other_user.id,
        status="running",
        image="agenthub/test",
        resource_limits_json="{}",
        created_at=now,
        updated_at=now,
    ))
    await db_session.commit()

    service = QuotaService(db_session)
    assert await service.active_sandbox_count(owner) == 0
    assert await service.active_sandbox_count(other_user) == 1


@pytest.mark.asyncio
async def test_explicit_local_runtime_does_not_require_sandbox(test_client):
    agent = await test_client.post(
        "/api/agents",
        json={
            "name": "Phase10 Local Fixture Agent",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [str(_phase10_cli())],
        },
    )
    project = await test_client.post(
        "/api/projects",
        json={"name": "Phase10 Local Still Works"},
    )
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "Phase10 本地会话",
            "projectId": project.json()["id"],
            "agentConfigId": agent.json()["id"],
        },
    )
    run = await test_client.post(
        f"/api/sessions/{session.json()['id']}/runs",
        json={"agentId": agent.json()["id"], "runtime": "local"},
    )

    assert run.status_code == 202, run.text
    assert run.json()["runtime"] == "local"
    assert run.json()["sandboxId"] is None


async def _create_cloud_session_for(test_client, headers: dict[str, str]) -> tuple[dict, dict, dict]:
    agent = await test_client.post(
        "/api/agents",
        json={
            "name": f"Phase10 Fixture Agent {headers['X-AgentHub-User-Email']}",
            "description": "Phase 10 fixture",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [str(_phase10_cli())],
            "systemPrompt": "你是 Phase 10 云端 runtime 测试 Agent。",
        },
        headers=headers,
    )
    assert agent.status_code == 201, agent.text
    project = await test_client.post(
        "/api/projects",
        json={"name": f"Phase10 Cloud Runtime {headers['X-AgentHub-User-Email']}", "workspaceMode": "cloud"},
        headers=headers,
    )
    assert project.status_code == 201, project.text
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "Phase10 云端会话",
            "projectId": project.json()["id"],
            "agentConfigId": agent.json()["id"],
        },
        headers=headers,
    )
    assert session.status_code == 201, session.text
    return agent.json(), project.json(), session.json()


async def _user_by_email(db_session, email: str) -> User:
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalars().one()
    return user
