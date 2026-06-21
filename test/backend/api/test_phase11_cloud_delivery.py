from pathlib import Path

import pytest

from app.config import settings
from app.core.timezone import china_now
from app.models import Artifact, DeploymentTarget, Message, PreviewSession
from app.services.cloud_storage import ensure_cloud_workspace


OWNER = {
    "X-AgentHub-User-Email": "phase11-owner@example.com",
    "X-AgentHub-User-Name": "Phase11 Owner",
}
VIEWER = {
    "X-AgentHub-User-Email": "phase11-viewer@example.com",
    "X-AgentHub-User-Name": "Phase11 Viewer",
}


def _configure_deployment(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "deployments"
    monkeypatch.setattr(settings, "agenthub_deployment_root", str(root))
    monkeypatch.setattr(settings, "agenthub_deployment_public_base_url", "http://deploy.test/deployments")
    return root


async def _cloud_artifact(test_client, db_session, *, content: str = "<main>Phase11</main>"):
    project = (await test_client.post(
        "/api/projects",
        json={"name": "Phase11 Cloud", "workspaceMode": "cloud"},
        headers=OWNER,
    )).json()
    session = (await test_client.post(
        "/api/sessions",
        json={"title": "Phase11 会话", "projectId": project["id"]},
        headers=OWNER,
    )).json()
    workspace = ensure_cloud_workspace(project["workspaceId"], {"projectId": project["id"]})
    Path(workspace, "index.html").write_text(content, encoding="utf-8")
    message = Message(
        id="phase11-message",
        session_id=session["id"],
        role="assistant",
        content="已创建 index.html",
        source_type="agent",
    )
    artifact = Artifact(
        id="phase11-artifact",
        session_id=session["id"],
        message_id=message.id,
        project_id=project["id"],
        type="web_preview",
        title="Phase11 Web",
        content=content,
        status="ready",
        version=1,
        file_path="index.html",
    )
    db_session.add(message)
    db_session.add(artifact)
    await db_session.commit()
    return project, session, artifact


@pytest.mark.asyncio
async def test_cloud_artifact_preview_ttl_revoke_and_source_validation(test_client, db_session, monkeypatch, tmp_path):
    deployment_root = _configure_deployment(monkeypatch, tmp_path)
    _project, _session, artifact = await _cloud_artifact(test_client, db_session)

    created = await test_client.post(
        f"/api/artifacts/{artifact.id}/previews",
        json={"source": "static", "ttlSeconds": 120},
        headers=OWNER,
    )

    assert created.status_code == 201, created.text
    preview = created.json()
    assert preview["url"].startswith("http://deploy.test/deployments/previews/")
    assert "agenthub.local" not in preview["url"]
    assert "localhost" not in preview["url"]
    assert preview["status"] == "ready"
    assert Path(deployment_root, "previews", preview["id"], "index.html").read_text(encoding="utf-8") == artifact.content

    got = await test_client.get(f"/api/previews/{preview['id']}", headers=OWNER)
    assert got.status_code == 200

    invalid = await test_client.post(
        f"/api/artifacts/{artifact.id}/previews",
        json={"source": "unknown"},
        headers=OWNER,
    )
    assert invalid.status_code == 400

    db_preview = await db_session.get(PreviewSession, preview["id"])
    db_preview.expires_at = china_now()
    await db_session.commit()
    expired = await test_client.get(f"/api/previews/{preview['id']}", headers=OWNER)
    assert expired.status_code == 410

    fresh = (await test_client.post(
        f"/api/artifacts/{artifact.id}/previews",
        json={"source": "dev_server"},
        headers=OWNER,
    )).json()
    revoked = await test_client.post(
        f"/api/previews/{fresh['id']}/revoke",
        json={"reason": "验收撤销"},
        headers=OWNER,
    )
    assert revoked.status_code == 202
    assert revoked.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_deployment_provider_target_contract(test_client, monkeypatch, tmp_path):
    _configure_deployment(monkeypatch, tmp_path)

    providers = await test_client.get("/api/deployment-providers", headers=OWNER)
    assert providers.status_code == 200
    provider = providers.json()["items"][0]
    assert provider["id"] == "static_site"
    assert "release" in provider["capabilities"]
    assert provider["publicBaseUrl"] == "http://deploy.test/deployments"

    targets = await test_client.get("/api/deployment-targets", headers=OWNER)
    assert targets.status_code == 200
    assert any(item["scope"] == "user" and item["provider"] == "static_site" for item in targets.json()["items"])

    created = await test_client.post(
        "/api/deployment-targets",
        json={"name": "用户静态站点", "provider": "static_site", "scope": "user"},
        headers=OWNER,
    )
    assert created.status_code == 201
    assert created.json()["name"] == "用户静态站点"


@pytest.mark.asyncio
async def test_deployment_pipeline_failure_retry_logs_and_rollback(test_client, db_session, monkeypatch, tmp_path):
    deployment_root = _configure_deployment(monkeypatch, tmp_path)
    _project, _session, artifact = await _cloud_artifact(
        test_client,
        db_session,
        content="<main>DEPLOY_FAIL</main>",
    )

    failed = await test_client.post(
        "/api/deployments",
        json={
            "artifactId": artifact.id,
            "artifactVersionId": artifact.id,
            "target": "static_hosting",
            "visibility": "private",
        },
        headers=OWNER,
    )
    assert failed.status_code == 202, failed.text
    failed_data = failed.json()
    assert failed_data["status"] == "failed"
    assert failed_data["stage"] == "build"
    assert failed_data["errorSummary"] == "发布构建失败"

    logs = await test_client.get(f"/api/deployments/{failed_data['id']}/logs", headers=OWNER)
    assert logs.status_code == 200
    assert "DEPLOY_FAIL" in "\n".join(chunk["text"] for chunk in logs.json()["chunks"])

    retried = await test_client.post(
        f"/api/deployments/{failed_data['id']}/retry",
        json={"fromStage": "build"},
        headers=OWNER,
    )
    assert retried.status_code == 202, retried.text
    published = retried.json()
    assert published["status"] == "published"
    assert published["url"].startswith("http://deploy.test/deployments/sites/")
    assert "agenthub.local" not in published["url"]
    assert published["provider"] == "static_site"
    assert published["targetId"]
    assert published["activeReleaseId"]
    assert published["bundleUri"].startswith("static-site://agenthub/releases/")
    assert published["artifactVersionId"] == artifact.id
    target = await db_session.get(DeploymentTarget, published["targetId"])
    assert Path(deployment_root, "sites", target.id, "index.html").read_text(encoding="utf-8") == artifact.content

    v2 = Artifact(
        id="phase11-v2",
        session_id=artifact.session_id,
        message_id=artifact.message_id,
        project_id=artifact.project_id,
        type="web_preview",
        title="Phase11 Web v2",
        content="<main>Phase16 v2</main>",
        status="ready",
        version=2,
        parent_artifact_id=artifact.id,
        file_path="index.html",
    )
    db_session.add(v2)
    await db_session.commit()

    second = (await test_client.post(
        "/api/deployments",
        json={
            "artifactId": artifact.id,
            "artifactVersionId": v2.id,
            "target": "static_hosting",
            "visibility": "team",
        },
        headers=OWNER,
    )).json()
    assert second["url"] == published["url"]
    assert Path(deployment_root, "sites", target.id, "index.html").read_text(encoding="utf-8") == v2.content
    rollback = await test_client.post(
        f"/api/deployments/{second['id']}/rollback",
        json={"targetDeploymentId": published["id"]},
        headers=OWNER,
    )
    assert rollback.status_code == 202
    assert rollback.json()["status"] == "rolled_back"
    assert rollback.json()["url"] == published["url"]
    assert rollback.json()["activeReleaseId"] == published["activeReleaseId"]
    assert Path(deployment_root, "sites", target.id, "index.html").read_text(encoding="utf-8") == artifact.content


@pytest.mark.asyncio
async def test_phase11_blocks_viewer_preview_and_deploy(test_client, db_session, monkeypatch, tmp_path):
    _configure_deployment(monkeypatch, tmp_path)
    team = (await test_client.post("/api/teams", json={"name": "Phase11 Team"}, headers=OWNER)).json()
    await test_client.post(
        f"/api/teams/{team['id']}/members",
        json={"email": "phase11-viewer@example.com", "role": "viewer"},
        headers=OWNER,
    )
    project = (await test_client.post(
        "/api/projects",
        json={"name": "Phase11 Team Cloud", "workspaceMode": "cloud", "teamId": team["id"]},
        headers=OWNER,
    )).json()
    session = (await test_client.post(
        "/api/sessions",
        json={"title": "Phase11 权限", "projectId": project["id"]},
        headers=OWNER,
    )).json()
    workspace = ensure_cloud_workspace(project["workspaceId"], {"projectId": project["id"]})
    Path(workspace, "index.html").write_text("<main>Denied</main>", encoding="utf-8")
    message = Message(id="phase11-perm-message", session_id=session["id"], role="assistant", content="x", source_type="agent")
    artifact = Artifact(
        id="phase11-perm-artifact",
        session_id=session["id"],
        message_id=message.id,
        project_id=project["id"],
        type="web_preview",
        title="Denied",
        content="<main>Denied</main>",
        status="ready",
        version=1,
        file_path="index.html",
    )
    db_session.add(message)
    db_session.add(artifact)
    await db_session.commit()

    preview = await test_client.post(
        f"/api/artifacts/{artifact.id}/previews",
        json={"source": "static"},
        headers=VIEWER,
    )
    deploy = await test_client.post(
        "/api/deployments",
        json={"artifactId": artifact.id, "artifactVersionId": artifact.id, "target": "static_hosting", "visibility": "team"},
        headers=VIEWER,
    )

    assert preview.status_code == 403
    assert deploy.status_code == 403
