import asyncio
import io
import json
import sys
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Artifact, ContextPackSnapshot, Message


async def _create_project(test_client, name: str = "Phase8 项目") -> dict:
    response = await test_client.post(
        "/api/projects",
        json={"name": f"{name}-{uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _write_file(test_client, project_id: str, path: str, content: str) -> None:
    response = await test_client.put(
        f"/api/projects/{project_id}/files",
        json={"path": path, "content": content},
    )
    assert response.status_code == 200, response.text


async def _wait_execution_done(test_client, execution_id: str) -> dict:
    latest: dict | None = None
    for _ in range(30):
        response = await test_client.get(f"/api/orchestrator/executions/{execution_id}")
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest["status"] in {"completed", "failed", "cancelled"}:
            return latest
        await asyncio.sleep(0.05)
    assert latest is not None
    return latest


@pytest.mark.asyncio
async def test_project_build_logs_preview_and_exports(test_client):
    project = await _create_project(test_client)
    project_id = project["id"]
    build_script = (
        "from pathlib import Path\n"
        "Path('dist').mkdir(exist_ok=True)\n"
        "Path('dist/index.html').write_text('<!doctype html><main>Phase8 Build</main>', encoding='utf-8')\n"
        "print('phase8 build ready')\n"
    )
    await _write_file(test_client, project_id, "build_phase8.py", build_script)
    await _write_file(test_client, project_id, "src/input.txt", "source payload")

    response = await test_client.post(
        f"/api/projects/{project_id}/builds",
        json={
            "command": f'"{sys.executable}" build_phase8.py',
            "artifactPath": "dist",
        },
    )

    assert response.status_code == 202, response.text
    data = response.json()
    assert data["status"] == "succeeded"
    build_id = data["buildId"]

    build_response = await test_client.get(f"/api/projects/{project_id}/builds/{build_id}")
    assert build_response.status_code == 200
    build = build_response.json()
    assert build["artifactPath"] == "dist"
    assert build["exitCode"] == 0

    list_response = await test_client.get(f"/api/projects/{project_id}/builds")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == [build_id]

    logs_response = await test_client.get(f"/api/projects/{project_id}/builds/{build_id}/logs")
    assert logs_response.status_code == 200
    chunks = logs_response.json()["chunks"]
    assert any("phase8 build ready" in chunk["text"] for chunk in chunks)

    preview_response = await test_client.post(
        f"/api/projects/{project_id}/previews",
        json={"source": "build", "buildId": build_id, "path": "index.html"},
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["source"] == "build"
    asset_response = await test_client.get(preview["url"])
    assert asset_response.status_code == 200
    assert "Phase8 Build" in asset_response.text

    source_zip_response = await test_client.get(f"/api/projects/{project_id}/exports/source")
    assert source_zip_response.status_code == 200
    assert source_zip_response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(source_zip_response.content)) as archive:
        assert any(name.endswith("src/input.txt") for name in archive.namelist())

    build_zip_response = await test_client.get(f"/api/projects/{project_id}/exports/builds/{build_id}")
    assert build_zip_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(build_zip_response.content)) as archive:
        names = archive.namelist()
        assert any(name.endswith("index.html") for name in names)
        html_name = next(name for name in names if name.endswith("index.html"))
        assert "Phase8 Build" in archive.read(html_name).decode("utf-8")


@pytest.mark.asyncio
async def test_project_build_failure_persists_logs(test_client):
    project = await _create_project(test_client)
    project_id = project["id"]
    await _write_file(
        test_client,
        project_id,
        "fail_build.py",
        "import sys\nsys.stderr.write('phase8 failure\\n')\nsys.exit(3)\n",
    )

    response = await test_client.post(
        f"/api/projects/{project_id}/builds",
        json={"command": f'"{sys.executable}" fail_build.py'},
    )

    assert response.status_code == 202, response.text
    data = response.json()
    assert data["status"] == "failed"
    logs_response = await test_client.get(
        f"/api/projects/{project_id}/builds/{data['buildId']}/logs",
    )
    assert logs_response.status_code == 200
    assert any("phase8 failure" in chunk["text"] for chunk in logs_response.json()["chunks"])


@pytest.mark.asyncio
async def test_project_preview_rejects_path_escape(test_client):
    project = await _create_project(test_client)

    response = await test_client.post(
        f"/api/projects/{project['id']}/previews",
        json={"source": "workspace", "path": "../../secret.txt"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_session_context_pack_preview_persists_snapshot(test_client, db_session, test_session):
    session_id = test_session
    session = await _session(db_session, session_id)
    message_id = str(uuid.uuid4())
    db_session.add(Message(
        id=message_id,
        session_id=session_id,
        role="user",
        content="请继续编辑这个产物",
        content_type="text",
        source_type="user",
        source_name="用户",
        is_pinned="1",
        metadata_json=json.dumps({"topic": "phase8"}, ensure_ascii=False),
    ))
    db_session.add(Artifact(
        id=str(uuid.uuid4()),
        session_id=session_id,
        message_id=message_id,
        project_id=session.project_id,
        type="web_preview",
        title="Phase8 Preview",
        content="<main>preview</main>",
        status="ready",
        file_path="index.html",
    ))
    await db_session.commit()

    response = await test_client.get(
        f"/api/sessions/{session_id}/context-pack",
        params={"purpose": "artifact_edit"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    block_types = {block["type"] for block in data["blocks"]}
    assert {"messages", "pinned_messages", "artifacts", "artifact_edit"}.issubset(block_types)
    assert data["warnings"] == []
    result = await db_session.execute(
        select(ContextPackSnapshot).where(ContextPackSnapshot.session_id == session_id)
    )
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_orchestrator_plan_resume_contract(test_client, test_session, test_agent):
    plan_id = f"phase8_plan_{uuid.uuid4().hex[:8]}"
    response = await test_client.post(
        "/api/orchestrator/plans/execute",
        json={
            "sessionId": test_session,
            "normalizedPlan": {
                "plan_id": plan_id,
                "status": "draft",
                "tasks": [
                    {
                        "task_id": "T1",
                        "title": "等待审批的任务",
                        "goal": "验证 resume 契约",
                        "required_skills": ["general_coding"],
                        "assigned_agent_id": test_agent.id,
                        "assigned_agent_name": test_agent.name,
                        "depends_on": [],
                        "expected_outputs": ["resume"],
                        "acceptance_criteria": ["plan can resume"],
                        "needs_approval": True,
                    },
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    execution = response.json()

    resume_response = await test_client.post(
        f"/api/orchestrator/plans/{plan_id}/resume",
        json={"approvalId": "approval-phase8", "message": "继续执行"},
    )

    assert resume_response.status_code == 200, resume_response.text
    plan = resume_response.json()
    assert plan["id"] == plan_id
    assert plan["status"] == "running"
    assert plan["currentStepId"] == "T1"
    assert plan["steps"][0]["status"] == "running"
    await _wait_execution_done(test_client, execution["executionId"])


async def _session(db_session, session_id: str):
    from app.models import Session

    session = await db_session.get(Session, session_id)
    assert session is not None
    return session
