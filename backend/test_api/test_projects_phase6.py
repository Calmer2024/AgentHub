"""Phase 6A Workspace Runtime API 验收测试。"""

from pathlib import Path

import pytest


@pytest.mark.asyncio
class TestProjectRuntimeApi:
    async def test_create_project_initializes_workspace(self, test_client):
        resp = await test_client.post("/api/projects", json={
            "name": "Phase 6 Demo",
        })

        assert resp.status_code == 201
        data = resp.json()
        workspace = Path(data["workspacePath"])
        assert data["name"] == "Phase 6 Demo"
        assert data["status"] == "ready"
        assert workspace.exists()
        assert (workspace / ".agenthub" / "project.json").exists()

    async def test_external_folder_requires_grant(self, test_client, tmp_path):
        resp = await test_client.post("/api/projects", json={
            "name": "outside",
            "workspacePath": str(tmp_path),
        })

        assert resp.status_code == 400

    async def test_create_existing_folder_with_grant(self, test_client, tmp_path):
        from app.services.project_service import register_folder_grant

        token = register_folder_grant(str(tmp_path))
        resp = await test_client.post("/api/projects", json={
            "name": "existing",
            "workspacePath": str(tmp_path),
            "folderToken": token,
        })

        assert resp.status_code == 201
        assert resp.json()["workspacePath"] == str(tmp_path.resolve())

    async def test_reopen_archived_existing_folder_restores_project(self, test_client, tmp_path):
        from app.services.project_service import register_folder_grant

        first_token = register_folder_grant(str(tmp_path))
        first = await test_client.post("/api/projects", json={
            "name": "existing",
            "workspacePath": str(tmp_path),
            "folderToken": first_token,
        })
        assert first.status_code == 201

        archived = await test_client.post(f"/api/projects/{first.json()['id']}/archive")
        assert archived.status_code == 200

        second_token = register_folder_grant(str(tmp_path))
        reopened = await test_client.post("/api/projects", json={
            "name": "existing reopened",
            "workspacePath": str(tmp_path),
            "folderToken": second_token,
        })

        assert reopened.status_code == 201
        assert reopened.json()["id"] == first.json()["id"]
        assert reopened.json()["name"] == "existing reopened"
        assert reopened.json()["status"] == "ready"

    async def test_rename_project_updates_metadata(self, test_client):
        project = (await test_client.post("/api/projects", json={"name": "old"})).json()

        resp = await test_client.patch(
            f"/api/projects/{project['id']}",
            json={"name": "new name"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new name"
        metadata = (Path(data["workspacePath"]) / ".agenthub" / "project.json").read_text(
            encoding="utf-8",
        )
        assert "new name" in metadata

    async def test_delete_project_with_files_removes_workspace(self, test_client):
        project = (await test_client.post("/api/projects", json={"name": "delete-me"})).json()
        workspace = Path(project["workspacePath"])
        (workspace / "index.html").write_text("<h1>bye</h1>", encoding="utf-8")

        resp = await test_client.delete(
            f"/api/projects/{project['id']}",
            params={"deleteFiles": "true"},
        )

        assert resp.status_code == 200
        assert resp.json()["filesDeleted"] is True
        assert not workspace.exists()

    async def test_delete_project_requires_matching_workspace_marker(self, test_client):
        project = (await test_client.post("/api/projects", json={"name": "unsafe"})).json()
        workspace = Path(project["workspacePath"])
        (workspace / ".agenthub" / "project.json").write_text(
            '{"projectId":"other"}',
            encoding="utf-8",
        )

        resp = await test_client.delete(
            f"/api/projects/{project['id']}",
            params={"deleteFiles": "true"},
        )

        assert resp.status_code == 400
        assert workspace.exists()

    async def test_tree_and_file_reject_path_escape(self, test_client):
        project = (await test_client.post("/api/projects", json={"name": "safe"})).json()

        tree = await test_client.get(f"/api/projects/{project['id']}/tree")
        file_resp = await test_client.get(
            f"/api/projects/{project['id']}/files",
            params={"path": "../../secret"},
        )

        assert tree.status_code == 200
        assert file_resp.status_code == 403

    async def test_snapshot_diff_detects_file_changes(self, test_client):
        project = (await test_client.post("/api/projects", json={"name": "diffable"})).json()
        workspace = Path(project["workspacePath"])
        (workspace / "index.html").write_text("<h1>v1</h1>\n", encoding="utf-8")

        snap = await test_client.post(
            f"/api/projects/{project['id']}/snapshot",
            json={"label": "before"},
        )
        assert snap.status_code == 201

        (workspace / "index.html").write_text("<h1>v2</h1>\n", encoding="utf-8")
        (workspace / "src").mkdir()
        (workspace / "src" / "app.js").write_text("console.log('ok')\n", encoding="utf-8")

        diff = await test_client.get(
            f"/api/projects/{project['id']}/diff",
            params={"baseRef": snap.json()["snapshotId"]},
        )

        assert diff.status_code == 200
        changes = {item["path"]: item["change"] for item in diff.json()["changedFiles"]}
        assert changes["index.html"] == "modified"
        assert changes["src/app.js"] == "created"

    async def test_static_preview_returns_local_url(self, test_client):
        project = (await test_client.post("/api/projects", json={"name": "preview"})).json()
        workspace = Path(project["workspacePath"])
        (workspace / "index.html").write_text("<html>Hello</html>", encoding="utf-8")

        resp = await test_client.post(
            f"/api/projects/{project['id']}/preview",
            json={"type": "static"},
        )

        assert resp.status_code == 200
        assert resp.json()["previewUrl"].endswith("/index.html")

    async def test_static_preview_can_target_artifact_file_path(self, test_client):
        project = (await test_client.post("/api/projects", json={"name": "preview-file"})).json()
        workspace = Path(project["workspacePath"])
        (workspace / "pages").mkdir()
        (workspace / "pages" / "demo.html").write_text("<html>Demo</html>", encoding="utf-8")

        resp = await test_client.post(
            f"/api/projects/{project['id']}/preview",
            json={"type": "static", "filePath": "pages/demo.html"},
        )

        assert resp.status_code == 200
        assert resp.json()["previewUrl"].endswith("/pages/demo.html")

    async def test_session_cwd_uses_project_workspace(self, test_client, test_agent):
        project = (await test_client.post("/api/projects", json={"name": "cwd"})).json()
        session = await test_client.post("/api/sessions", json={
            "projectId": project["id"],
            "agentConfigId": test_agent.id,
        })

        resp = await test_client.get(f"/api/sessions/{session.json()['id']}/workspace")

        assert resp.status_code == 200
        assert resp.json()["workspacePath"] == project["workspacePath"]
