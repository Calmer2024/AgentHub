import json
import sys
from pathlib import Path

import pytest


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
    )
    assert session.status_code == 201, session.text
    return agent.json(), project.json(), session.json()


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
    assert "agent.process.started" in types
    assert "agent.output" in types
    assert "artifact.created" in types
    assert events[-1]["done"] is True
    assert "super-secret-value" not in response.text
    assert "[REDACTED]" in response.text

    run_started = next(event for event in events if event.get("type") == "run.started")
    run_id = run_started["runId"]
    sandbox_id = run_started["run"]["metadata"]["sandboxId"]
    logs = await test_client.get(f"/api/runs/{run_id}/logs")
    assert logs.status_code == 200, logs.text
    log_text = "\n".join(chunk["text"] for chunk in logs.json()["chunks"])
    assert "super-secret-value" not in log_text
    assert "[REDACTED]" in log_text

    messages = await test_client.get(f"/api/sessions/{session['id']}/messages")
    assert messages.status_code == 200
    assert "super-secret-value" not in messages.text
    assert "[REDACTED]" in messages.text

    artifacts = await test_client.get(f"/api/sessions/{session['id']}/artifacts")
    assert artifacts.status_code == 200, artifacts.text
    assert any(item["filePath"] == "index.html" for item in artifacts.json())

    stopped = await test_client.post(
        f"/api/sandboxes/{sandbox_id}/stop",
        json={"reason": "验收停止"},
        headers=OWNER,
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "stopped"

    snapshot = await test_client.post(
        f"/api/workspaces/{project['workspaceId']}/snapshots",
        json={"label": "sandbox stopped 后"},
        headers=OWNER,
    )
    assert snapshot.status_code == 201, snapshot.text


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

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert third.status_code == 409
    quota = await test_client.get("/api/quotas/me", headers=OWNER)
    assert quota.status_code == 200
    assert quota.json()["concurrentRunsLimit"] == 2


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
