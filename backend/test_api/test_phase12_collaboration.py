import json

import pytest

from app.models import (
    ApprovalCheckpoint,
    Artifact,
    Message,
    Project,
    Run,
    RunTask,
    Session,
)


OWNER = {
    "X-AgentHub-User-Email": "phase12-owner@example.com",
    "X-AgentHub-User-Name": "Phase12 Owner",
}
VIEWER = {
    "X-AgentHub-User-Email": "phase12-viewer@example.com",
    "X-AgentHub-User-Name": "Phase12 Viewer",
}


async def _cloud_project_session(test_client, *, title: str = "Phase12 会话"):
    project = (await test_client.post(
        "/api/projects",
        json={"name": "Phase12 Cloud", "workspaceMode": "cloud"},
        headers=OWNER,
    )).json()
    session = (await test_client.post(
        "/api/sessions",
        json={"title": title, "projectId": project["id"]},
    )).json()
    return project, session


async def _persist_message_and_artifact(db_session, project_id: str, session_id: str):
    message = Message(
        id=f"phase12-message-{session_id}",
        session_id=session_id,
        role="assistant",
        content="已生成 Phase 12 验收产物",
        source_type="agent",
        source_name="Codex",
    )
    artifact = Artifact(
        id=f"phase12-artifact-{session_id}",
        session_id=session_id,
        message_id=message.id,
        project_id=project_id,
        type="document",
        title="Phase12 文档",
        content="# Phase12\n\n验收内容",
        status="ready",
        version=1,
        file_path="phase12.md",
    )
    db_session.add(message)
    db_session.add(artifact)
    await db_session.commit()
    return message, artifact


@pytest.mark.asyncio
async def test_comments_notifications_and_permission_gate(test_client, db_session):
    team = (await test_client.post("/api/teams", json={"name": "Phase12 Team"}, headers=OWNER)).json()
    await test_client.post(
        f"/api/teams/{team['id']}/members",
        json={"email": "phase12-viewer@example.com", "role": "viewer"},
        headers=OWNER,
    )
    project = (await test_client.post(
        "/api/projects",
        json={"name": "Phase12 Team Project", "workspaceMode": "cloud", "teamId": team["id"]},
        headers=OWNER,
    )).json()
    session = (await test_client.post(
        "/api/sessions",
        json={"title": "Phase12 评论", "projectId": project["id"]},
    )).json()
    message, _artifact = await _persist_message_and_artifact(db_session, project["id"], session["id"])

    denied = await test_client.post(
        f"/api/projects/{project['id']}/comments",
        json={"targetType": "message", "targetId": message.id, "body": "viewer 不应可写"},
        headers=VIEWER,
    )
    assert denied.status_code == 403

    created = await test_client.post(
        f"/api/projects/{project['id']}/comments",
        json={"targetType": "message", "targetId": message.id, "body": "@viewer 请确认部署"},
        headers=OWNER,
    )
    assert created.status_code == 201, created.text
    comment = created.json()
    assert comment["targetType"] == "message"
    assert comment["body"] == "@viewer 请确认部署"

    listed = await test_client.get(
        f"/api/projects/{project['id']}/comments?targetType=message&targetId={message.id}",
        headers=VIEWER,
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == comment["id"]

    notifications = await test_client.get("/api/notifications", headers=VIEWER)
    assert notifications.status_code == 200
    assert any(item["type"] == "comment" for item in notifications.json()["items"])


@pytest.mark.asyncio
async def test_attachment_context_forward_reference_and_local_chat_regression(test_client, db_session, test_session):
    session = await db_session.get(Session, test_session)
    project = await db_session.get(Project, session.project_id)

    uploaded = await test_client.post(
        "/api/attachments",
        data={"projectId": project.id, "sessionId": test_session},
        files={"file": ("notes.md", b"# Context\nPhase12 upload", "text/markdown")},
        headers=OWNER,
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    assert attachment["mimeType"] == "text/markdown"

    rejected = await test_client.post(
        "/api/attachments",
        data={"projectId": project.id, "sessionId": test_session},
        files={"file": ("tool.exe", b"binary", "application/x-msdownload")},
        headers=OWNER,
    )
    assert rejected.status_code == 415

    chat = await test_client.post(
        f"/api/sessions/{test_session}/chat",
        json={"content": "请读取附件上下文", "attachmentIds": [attachment["id"]]},
    )
    assert chat.status_code == 200
    await chat.aread()
    stdin_path = project.workspace_path + "/.agenthub-cli-stdin.txt"
    with open(stdin_path, encoding="utf-8") as handle:
        prompt = handle.read()
    assert "[Attachment context]" in prompt
    assert "notes.md" in prompt

    target = (await test_client.post(
        "/api/sessions",
        json={"title": "Phase12 转发目标", "projectId": project.id},
    )).json()
    source_message = Message(
        id="phase12-forward-source",
        session_id=test_session,
        role="assistant",
        content="转发这条消息",
        source_type="agent",
        source_name="Codex",
    )
    source_artifact = Artifact(
        id="phase12-forward-artifact",
        session_id=test_session,
        message_id=source_message.id,
        project_id=project.id,
        type="web_preview",
        title="转发 Artifact",
        content="<main>forwarded</main>",
        status="ready",
        version=1,
    )
    db_session.add(source_message)
    db_session.add(source_artifact)
    await db_session.commit()

    forwarded = await test_client.post(
        f"/api/messages/{source_message.id}/forward",
        json={"targetSessionIds": [target["id"]], "includeArtifacts": True},
        headers=OWNER,
    )
    assert forwarded.status_code == 201, forwarded.text
    body = forwarded.json()
    assert body["messages"][0]["sessionId"] == target["id"]
    assert body["artifactReferences"][0]["artifactId"] == source_artifact.id
    assert body["artifactReferences"][0]["relation"] == "forwarded"


@pytest.mark.asyncio
async def test_mobile_sessions_approval_decision_and_advanced_artifacts(test_client, db_session):
    project, session = await _cloud_project_session(test_client, title="Phase12 Mobile")
    message, artifact = await _persist_message_and_artifact(db_session, project["id"], session["id"])
    run = Run(
        id="phase12-run",
        session_id=session["id"],
        project_id=project["id"],
        mode="single",
        status="waiting_input",
    )
    task = RunTask(
        id="phase12-task",
        run_id=run.id,
        session_id=session["id"],
        agent_id=None,
        name="primary",
        status="waiting_input",
    )
    approval = ApprovalCheckpoint(
        id="phase12-approval",
        run_id=run.id,
        task_id=task.id,
        session_id=session["id"],
        message_id=message.id,
        artifact_id=artifact.id,
        title="移动端审批",
        summary="确认后继续",
        status="pending_review",
        metadata_json=json.dumps({"source": "test"}, ensure_ascii=False),
    )
    db_session.add(run)
    db_session.add(task)
    db_session.add(approval)
    await db_session.commit()

    mobile = await test_client.get("/api/mobile/sessions", headers=OWNER)
    assert mobile.status_code == 200
    summary = next(item for item in mobile.json() if item["id"] == session["id"])
    assert summary["pendingApprovalCount"] == 1

    decided = await test_client.post(
        f"/api/mobile/approvals/{approval.id}/decision",
        json={"decision": "approve", "comment": "移动端同意"},
        headers=OWNER,
    )
    assert decided.status_code == 202, decided.text
    assert decided.json()["status"] == "approved"

    duplicate = await test_client.post(
        f"/api/mobile/approvals/{approval.id}/decision",
        json={"decision": "reject", "comment": "重复操作"},
        headers=OWNER,
    )
    assert duplicate.status_code == 409

    rendered = await test_client.get(f"/api/artifacts/{artifact.id}/render?format=html", headers=OWNER)
    assert rendered.status_code == 200
    assert rendered.json()["format"] == "html"
    assert "Phase12" in rendered.json()["content"]

    template = await test_client.post(
        "/api/agent-template-sessions",
        json={"seedPrompt": "专门负责 Cloud Preview 验收"},
        headers=OWNER,
    )
    assert template.status_code == 201
    assert template.json()["draft"]["runtimeConfig"]["cliTool"] == "custom"

    finalized = await test_client.post(
        f"/api/agent-template-sessions/{template.json()['id']}/finalize",
        json={"name": "Phase12 Reviewer", "engine": "codex"},
        headers=OWNER,
    )
    assert finalized.status_code == 201, finalized.text
    assert finalized.json()["cliTool"] == "codex"

    sync = await test_client.post(
        f"/api/projects/{project['id']}/git/sync",
        json={"remote": "origin", "branch": "main", "mode": "pull"},
        headers=OWNER,
    )
    assert sync.status_code == 202
    assert sync.json()["status"] == "completed"
    assert sync.json()["commitSha"]

    conflict = await test_client.post(
        f"/api/projects/{project['id']}/git/sync",
        json={"remote": "origin", "branch": "conflict/main", "mode": "pull"},
        headers=OWNER,
    )
    assert conflict.status_code == 202
    assert conflict.json()["status"] == "failed"
    assert conflict.json()["errorSummary"] == "git.conflict"
