import json

import pytest

from app.config import settings
from app.models import ApprovalCheckpoint, Message, Run, RunTask


def _enable_saas_production(monkeypatch):
    monkeypatch.setattr(settings, "agenthub_edition", "saas")
    monkeypatch.setattr(settings, "agenthub_surface", "desktop")
    monkeypatch.setattr(settings, "agenthub_auth_required", True)
    monkeypatch.setattr(settings, "agenthub_environment", "production")
    monkeypatch.setattr(settings, "agenthub_dev_auth_enabled", False)


async def _login(test_client, email: str, name: str):
    response = await test_client.post(
        "/api/auth/login",
        json={"email": email, "displayName": name},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    return {"Authorization": f"Bearer {data['accessToken']}"}, data


@pytest.mark.asyncio
async def test_production_auth_disables_dev_headers_and_rotates_session(test_client, monkeypatch):
    _enable_saas_production(monkeypatch)

    dev_header = await test_client.get(
        "/api/auth/me",
        headers={"X-AgentHub-User-Email": "spoof@example.com"},
    )
    assert dev_header.status_code == 401

    projects = await test_client.get("/api/projects")
    assert projects.status_code == 401

    disabled_provider = await test_client.post(
        "/api/auth/login",
        json={"email": "spoof@example.com", "provider": "dev_header"},
    )
    assert disabled_provider.status_code == 401

    headers, session = await _login(test_client, "owner14@example.com", "Phase14 Owner")
    me = await test_client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "owner14@example.com"
    assert me.json()["defaultSpace"]["kind"] == "personal"

    refreshed = await test_client.post(
        "/api/auth/refresh",
        json={"refreshToken": session["refreshToken"]},
    )
    assert refreshed.status_code == 200, refreshed.text
    new_headers = {"Authorization": f"Bearer {refreshed.json()['accessToken']}"}

    logged_out = await test_client.post(
        "/api/auth/logout",
        json={"refreshToken": refreshed.json()["refreshToken"]},
        headers=new_headers,
    )
    assert logged_out.status_code == 204
    expired = await test_client.get("/api/auth/me", headers=new_headers)
    assert expired.status_code == 401


@pytest.mark.asyncio
async def test_personal_cloud_projects_are_filtered_by_tenant_scope(test_client, monkeypatch):
    _enable_saas_production(monkeypatch)
    owner_headers, _ = await _login(test_client, "owner14-a@example.com", "Owner A")
    other_headers, _ = await _login(test_client, "owner14-b@example.com", "Owner B")

    owner_project = await test_client.post(
        "/api/projects",
        json={"name": "Owner A Cloud", "workspaceMode": "cloud"},
        headers=owner_headers,
    )
    assert owner_project.status_code == 201, owner_project.text
    other_project = await test_client.post(
        "/api/projects",
        json={"name": "Owner B Cloud", "workspaceMode": "cloud"},
        headers=other_headers,
    )
    assert other_project.status_code == 201, other_project.text

    listed = await test_client.get("/api/projects", headers=owner_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [owner_project.json()["id"]]

    forbidden_detail = await test_client.get(
        f"/api/projects/{other_project.json()['id']}",
        headers=owner_headers,
    )
    assert forbidden_detail.status_code == 403

    forbidden_write = await test_client.patch(
        f"/api/projects/{other_project.json()['id']}",
        json={"name": "越权改名"},
        headers=owner_headers,
    )
    assert forbidden_write.status_code == 403

    audit = await test_client.get("/api/audit-logs", headers=owner_headers)
    assert audit.status_code == 200, audit.text
    assert all(item.get("projectId") != other_project.json()["id"] for item in audit.json()["items"])


@pytest.mark.asyncio
async def test_team_viewer_can_read_but_cannot_write_cloud_resources(test_client, db_session, monkeypatch):
    _enable_saas_production(monkeypatch)
    owner_headers, _ = await _login(test_client, "team-owner14@example.com", "Team Owner")
    viewer_headers, _ = await _login(test_client, "team-viewer14@example.com", "Team Viewer")

    team = await test_client.post("/api/teams", json={"name": "Phase14 Team"}, headers=owner_headers)
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    member = await test_client.post(
        f"/api/teams/{team_id}/members",
        json={"email": "team-viewer14@example.com", "role": "viewer"},
        headers=owner_headers,
    )
    assert member.status_code == 201, member.text

    project = await test_client.post(
        "/api/projects",
        json={"name": "Team Cloud", "workspaceMode": "cloud", "teamId": team_id},
        headers=owner_headers,
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    viewer_projects = await test_client.get("/api/projects", headers=viewer_headers)
    assert viewer_projects.status_code == 200
    assert [item["id"] for item in viewer_projects.json()] == [project_id]

    readable = await test_client.get(f"/api/projects/{project_id}", headers=viewer_headers)
    assert readable.status_code == 200

    rename = await test_client.patch(
        f"/api/projects/{project_id}",
        json={"name": "Viewer Rename"},
        headers=viewer_headers,
    )
    assert rename.status_code == 403

    viewer_session_create = await test_client.post(
        "/api/sessions",
        json={"title": "Viewer should not write", "projectId": project_id},
        headers=viewer_headers,
    )
    assert viewer_session_create.status_code == 403

    owner_session = await test_client.post(
        "/api/sessions",
        json={"title": "Owner writes", "projectId": project_id},
        headers=owner_headers,
    )
    assert owner_session.status_code == 201, owner_session.text
    session_id = owner_session.json()["id"]
    viewer_session = await test_client.get(f"/api/sessions/{session_id}", headers=viewer_headers)
    assert viewer_session.status_code == 200

    message = Message(
        id="phase14-forward-source",
        session_id=session_id,
        role="assistant",
        content="tenant message",
        source_type="agent",
        source_name="Codex",
    )
    run = Run(
        id="phase14-run",
        session_id=session_id,
        project_id=project_id,
        mode="single",
        status="waiting_input",
    )
    task = RunTask(
        id="phase14-task",
        run_id=run.id,
        session_id=session_id,
        name="primary",
        status="waiting_input",
    )
    approval = ApprovalCheckpoint(
        id="phase14-approval",
        run_id=run.id,
        task_id=task.id,
        session_id=session_id,
        message_id=message.id,
        title="Phase14 审批",
        summary="viewer 不能审批",
        status="pending_review",
        metadata_json=json.dumps({"phase": 14}, ensure_ascii=False),
    )
    db_session.add(message)
    db_session.add(run)
    db_session.add(task)
    db_session.add(approval)
    await db_session.commit()

    forward = await test_client.post(
        "/api/sessions/forward",
        json={"messageIds": [message.id], "targetSessionIds": [session_id]},
        headers=viewer_headers,
    )
    assert forward.status_code == 403

    viewer_decision = await test_client.post(
        f"/api/mobile/approvals/{approval.id}/decision",
        json={"decision": "approve", "comment": "viewer approve"},
        headers=viewer_headers,
    )
    assert viewer_decision.status_code == 403

    owner_decision = await test_client.post(
        f"/api/mobile/approvals/{approval.id}/decision",
        json={"decision": "approve", "comment": "owner approve"},
        headers=owner_headers,
    )
    assert owner_decision.status_code == 202, owner_decision.text
