import io
import zipfile

import pytest


OWNER = {
    "X-AgentHub-User-Email": "owner@example.com",
    "X-AgentHub-User-Name": "Owner",
}
VIEWER = {
    "X-AgentHub-User-Email": "viewer@example.com",
    "X-AgentHub-User-Name": "Viewer",
}


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("src/App.tsx", "export default function App() { return null }\n")
        archive.writestr("package.json", '{"scripts":{"dev":"vite"}}')
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_auth_me_requires_login_and_persists_user(test_client):
    unauth = await test_client.get("/api/auth/me")
    assert unauth.status_code == 401

    logged_in = await test_client.get("/api/auth/me", headers=OWNER)

    assert logged_in.status_code == 200
    data = logged_in.json()
    assert data["email"] == "owner@example.com"
    assert data["displayName"] == "Owner"


@pytest.mark.asyncio
async def test_team_member_rbac_blocks_viewer_project_create_and_delete(test_client):
    team = await test_client.post("/api/teams", json={"name": "Phase9 团队"}, headers=OWNER)
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]

    duplicate = await test_client.post("/api/teams", json={"name": "Phase9 团队"}, headers=OWNER)
    assert duplicate.status_code == 409

    member = await test_client.post(
        f"/api/teams/{team_id}/members",
        json={"email": "viewer@example.com", "role": "viewer"},
        headers=OWNER,
    )
    assert member.status_code == 201, member.text
    assert member.json()["role"] == "viewer"

    forbidden_create = await test_client.post(
        "/api/projects",
        json={"name": "viewer cloud", "workspaceMode": "cloud", "teamId": team_id},
        headers=VIEWER,
    )
    assert forbidden_create.status_code == 403

    project = await test_client.post(
        "/api/projects",
        json={"name": "owner cloud", "workspaceMode": "cloud", "teamId": team_id},
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    forbidden_delete = await test_client.delete(
        f"/api/projects/{project.json()['id']}",
        headers=VIEWER,
    )
    assert forbidden_delete.status_code == 403


@pytest.mark.asyncio
async def test_cloud_project_workspace_snapshot_restore_import_and_audit(test_client):
    team = (await test_client.post("/api/teams", json={"name": "Cloud Slice"}, headers=OWNER)).json()
    project_response = await test_client.post(
        "/api/projects",
        json={
            "name": "Phase9 Cloud",
            "workspaceMode": "cloud",
            "teamId": team["id"],
            "template": "vite-react",
        },
        headers=OWNER,
    )

    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    assert project["workspaceMode"] == "cloud"
    assert project["workspaceId"]
    assert project["workspacePath"] is None

    workspace_response = await test_client.get(
        f"/api/workspaces/{project['workspaceId']}",
        headers=OWNER,
    )
    assert workspace_response.status_code == 200, workspace_response.text
    workspace = workspace_response.json()
    assert workspace["storageUri"].startswith("cloud://agenthub/workspaces/")
    assert workspace["snapshots"] == []
    assert workspace["imports"] == []

    zip_import = await test_client.post(
        f"/api/workspaces/{project['workspaceId']}/imports/zip",
        files={"file": ("source.zip", _zip_bytes(), "application/zip")},
        headers=OWNER,
    )
    assert zip_import.status_code == 202, zip_import.text
    assert zip_import.json()["status"] == "completed"

    github_import = await test_client.post(
        f"/api/workspaces/{project['workspaceId']}/imports/github",
        json={"repoUrl": "https://github.com/example/repo", "branch": "main"},
        headers=OWNER,
    )
    assert github_import.status_code == 202, github_import.text
    assert github_import.json()["status"] == "queued"

    snapshot = await test_client.post(
        f"/api/workspaces/{project['workspaceId']}/snapshots",
        json={"label": "导入后"},
        headers=OWNER,
    )
    assert snapshot.status_code == 201, snapshot.text
    snapshot_id = snapshot.json()["id"]

    restore = await test_client.post(
        f"/api/workspaces/{project['workspaceId']}/snapshots/{snapshot_id}/restore",
        json={"strategy": "replace"},
        headers=OWNER,
    )
    assert restore.status_code == 202, restore.text
    assert restore.json()["restoreId"]

    refreshed = (await test_client.get(
        f"/api/workspaces/{project['workspaceId']}",
        headers=OWNER,
    )).json()
    assert [item["label"] for item in refreshed["snapshots"]] == ["导入后"]
    assert {item["source"] for item in refreshed["imports"]} == {"zip", "github"}
    assert refreshed["restores"][0]["status"] == "completed"

    audit = await test_client.get(
        "/api/audit-logs",
        params={"projectId": project["id"]},
        headers=OWNER,
    )
    assert audit.status_code == 200, audit.text
    actions = {item["action"] for item in audit.json()["items"]}
    assert {
        "project.created",
        "workspace.created",
        "workspace.import.completed",
        "workspace.snapshot.created",
        "workspace.restore.completed",
    }.issubset(actions)


@pytest.mark.asyncio
async def test_phase9_keeps_local_project_creation_unauthenticated(test_client):
    response = await test_client.post("/api/projects", json={"name": "Local Still Works"})

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["workspaceMode"] == "local"
    assert data["workspacePath"]
    assert data["workspaceId"] is None
