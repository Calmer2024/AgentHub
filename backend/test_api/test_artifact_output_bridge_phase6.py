"""Phase 6F Artifact Output Bridge acceptance tests."""

import json
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AgentConfig, Artifact, Message, Project, Session, SessionMember
from app.services.artifact_output_bridge import ArtifactOutputBridge
from app.services.file_change_detector import FileChangeDetector


BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
class TestArtifactOutputBridgePhase6:
    async def test_fenced_diff_creates_code_diff_and_is_idempotent(
        self, db_session, test_session,
    ):
        message = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="assistant",
            content=(
                "这里是补丁：\n"
                "```diff\n"
                "--- a/app.py\n"
                "+++ b/app.py\n"
                "@@ -1 +1 @@\n"
                "-print('old')\n"
                "+print('new')\n"
                "```\n"
            ),
            source_type="agent",
        )
        db_session.add(message)
        await db_session.commit()

        first = await ArtifactOutputBridge(db_session).scan_message(message.id)
        second = await ArtifactOutputBridge(db_session).scan_message(message.id)

        assert len(first.created) == 1
        assert first.created[0].type == "code_diff"
        assert "--- a/app.py" in first.created[0].content
        assert len(second.created) == 0
        assert second.skipped[0]["reason"] == "duplicate"

    async def test_workspace_html_snapshot_creates_web_preview(
        self, db_session, test_session,
    ):
        session = await db_session.get(Session, test_session)
        project = await db_session.get(Project, session.project_id)
        detector = FileChangeDetector()
        snapshot = detector.create_snapshot(project.workspace_path, "before")
        Path(project.workspace_path, "index.html").write_text(
            "<!doctype html><html><body><h1>Hello</h1></body></html>",
            encoding="utf-8",
        )
        message = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="assistant",
            content="已写入 index.html",
            source_type="agent",
        )
        db_session.add(message)
        await db_session.commit()

        result = await ArtifactOutputBridge(db_session).scan_completed_message(
            session=session,
            message=message,
            workspace_path=project.workspace_path,
            visible_content=message.content,
            snapshot_id=snapshot.snapshot_id,
        )

        assert len(result.created) >= 1
        html = next(item for item in result.created if item.type == "web_preview")
        assert html.project_id == project.id
        assert html.file_path == "index.html"
        assert "Hello" in html.content

    async def test_workspace_multi_file_snapshot_creates_file_tree_and_code_diff(
        self, db_session, test_session,
    ):
        session = await db_session.get(Session, test_session)
        project = await db_session.get(Project, session.project_id)
        detector = FileChangeDetector()
        snapshot = detector.create_snapshot(project.workspace_path, "before")
        Path(project.workspace_path, "package.json").write_text(
            '{"scripts":{"dev":"vite"}}',
            encoding="utf-8",
        )
        src = Path(project.workspace_path, "src")
        src.mkdir(exist_ok=True)
        Path(src, "App.tsx").write_text(
            "export default function App() { return <main>Tree</main>; }",
            encoding="utf-8",
        )
        message = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="assistant",
            content="已创建 package.json 和 src/App.tsx",
            source_type="agent",
        )
        db_session.add(message)
        await db_session.commit()

        result = await ArtifactOutputBridge(db_session).scan_completed_message(
            session=session,
            message=message,
            workspace_path=project.workspace_path,
            visible_content=message.content,
            snapshot_id=snapshot.snapshot_id,
        )

        file_tree = next(item for item in result.created if item.type == "file_tree")
        assert file_tree.message_id == message.id
        changes = json.loads(file_tree.content)["changes"]
        assert [item["path"] for item in changes] == ["package.json", "src/App.tsx"]
        code_diff = next(item for item in result.created if item.type == "code_diff")
        assert "--- a/package.json" in code_diff.content
        assert "--- a/src/App.tsx" in code_diff.content

    async def test_manual_force_rescan_reads_workspace_file_hints(
        self, db_session, test_session,
    ):
        session = await db_session.get(Session, test_session)
        project = await db_session.get(Project, session.project_id)
        Path(project.workspace_path, "index.html").write_text(
            "<!doctype html><html><body><main>Manual</main></body></html>",
            encoding="utf-8",
        )
        message = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="assistant",
            content="已写入 index.html，可以预览。",
            source_type="agent",
        )
        db_session.add(message)
        await db_session.commit()

        first = await ArtifactOutputBridge(db_session).scan_message(message.id, force=False)
        second = await ArtifactOutputBridge(db_session).scan_message(message.id, force=True)

        assert first.created == []
        assert len(second.created) == 1
        assert second.created[0].type == "web_preview"
        assert second.created[0].source == "manual_rescan"
        assert second.created[0].file_path == "index.html"

    async def test_manual_rescan_does_not_duplicate_workspace_detection(
        self, db_session, test_session,
    ):
        session = await db_session.get(Session, test_session)
        project = await db_session.get(Project, session.project_id)
        detector = FileChangeDetector()
        snapshot = detector.create_snapshot(project.workspace_path, "before")
        Path(project.workspace_path, "index.html").write_text(
            "<!doctype html><html><body><main>Same</main></body></html>",
            encoding="utf-8",
        )
        message = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="assistant",
            content="已写入 index.html",
            source_type="agent",
        )
        db_session.add(message)
        await db_session.commit()

        automatic = await ArtifactOutputBridge(db_session).scan_completed_message(
            session=session,
            message=message,
            workspace_path=project.workspace_path,
            visible_content=message.content,
            snapshot_id=snapshot.snapshot_id,
        )
        manual = await ArtifactOutputBridge(db_session).scan_message(message.id, force=True)

        assert len([item for item in automatic.created if item.type == "web_preview"]) == 1
        assert manual.created == []
        assert any(item["reason"] == "duplicate" for item in manual.skipped)
        rows = (await db_session.execute(
            select(Artifact).where(Artifact.message_id == message.id, Artifact.type == "web_preview")
        )).scalars().all()
        assert len(rows) == 1

    async def test_markdown_candidate_is_saved_to_message_metadata_without_artifact(
        self, db_session, test_session,
    ):
        message = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="assistant",
            content=(
                "```md\n"
                "# 说明文档\n\n"
                "## 背景\n"
                "这是一段足够长的 Markdown 内容，用于验证低置信候选不会自动落库。"
                "它有标题结构，但没有明确的文件写入或期望输出，因此应该只进入 metadata。"
                "继续补充一些文字让长度超过阈值。"
                "用户界面后续可以基于这个候选提供确认创建入口，但当前桥接模块不应该自动创建文档产物。"
                "这可以避免普通解释性 Markdown 回复污染会话产物工作台。\n"
                "```\n"
            ),
            source_type="agent",
        )
        db_session.add(message)
        await db_session.commit()

        result = await ArtifactOutputBridge(db_session).scan_message(message.id)

        assert result.created == []
        refreshed = await db_session.get(Message, message.id)
        metadata = json.loads(refreshed.metadata_json)
        assert metadata["artifactBridge"]["candidateCount"] == 1
        assert metadata["artifactCandidates"][0]["artifactType"] == "document"

    async def test_scan_api_returns_created_artifact_and_versions_remain_usable(
        self, test_client, db_session, test_session,
    ):
        message = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="assistant",
            content=(
                "```html\n"
                "<html><body><main>Preview</main></body></html>\n"
                "```\n"
            ),
            source_type="agent",
        )
        db_session.add(message)
        await db_session.commit()

        resp = await test_client.post(f"/api/messages/{message.id}/artifacts/scan", json={"force": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["created"][0]["type"] == "web_preview"
        versions = await test_client.get(f"/api/artifacts/{data['created'][0]['id']}/versions")
        assert versions.status_code == 200
        assert versions.json()[0]["version"] == 1

    async def test_chat_stream_creates_artifact_before_final_done(
        self, test_client, db_session, test_session,
    ):
        session = await db_session.get(Session, test_session)
        project = await db_session.get(Project, session.project_id)

        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "WRITE_HTML_ARTIFACT"},
        )

        events = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        types = [event.get("type") or ("done" if event.get("done") else "token") for event in events]
        assert "artifact.scan.started" in types
        assert "artifact.created" in types
        assert "artifact.scan.completed" in types
        assert types.index("artifact.created") < len(types) - 1
        assert events[-1]["done"] is True

        artifacts_resp = await test_client.get(f"/api/sessions/{test_session}/artifacts")
        artifacts = artifacts_resp.json()
        html = next(item for item in artifacts if item["type"] == "web_preview")
        assert html["messageId"] == events[-1]["messageId"]
        assert html["projectId"] == project.id
        assert html["filePath"] == "index.html"
        assert "Fixture Bridge" in html["content"]

    async def test_group_chat_artifacts_bind_agent_messages_not_summary(
        self, test_client, db_session, test_session,
    ):
        session = await db_session.get(Session, test_session)
        session.mode = "group"
        session.agent_config_id = None
        cli = BACKEND_ROOT / ".test-bin" / "fixture_cli.py"
        agents = [
            AgentConfig(
                id=str(uuid.uuid4()),
                name=f"产物 Agent {index}",
                description="测试 HTML 产物",
                system_prompt="",
                agent_type="cli_wrapper",
                cli_tool="custom",
                executable=sys.executable,
                init_args=json.dumps([str(cli)]),
                env_vars="{}",
            )
            for index in range(2)
        ]
        db_session.add_all(agents)
        await db_session.flush()
        for agent in agents:
            db_session.add(SessionMember(session_id=test_session, agent_config_id=agent.id))
        await db_session.commit()

        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "EMIT_HTML_BLOCK"},
        )
        async for _line in resp.aiter_lines():
            pass

        artifacts_resp = await test_client.get(f"/api/sessions/{test_session}/artifacts")
        artifacts = artifacts_resp.json()
        messages_resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        messages = messages_resp.json()
        message_by_id = {item["id"]: item for item in messages}

        assert len(artifacts) == 2
        assert {item["sourceId"] for item in messages if item["role"] == "assistant"} == {
            agent.id for agent in agents
        }
        assert all(message_by_id[item["messageId"]]["sourceType"] == "agent" for item in artifacts)
        assert not any(message_by_id[item["messageId"]]["sourceType"] == "orchestrator" for item in artifacts)

    async def test_unclosed_code_block_is_ignored(self, db_session, test_session):
        message = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="assistant",
            content="```html\n<html><body>missing close",
            source_type="agent",
        )
        db_session.add(message)
        await db_session.commit()

        result = await ArtifactOutputBridge(db_session).scan_message(message.id)

        assert result.created == []
        assert result.candidates == []
        artifacts = (await db_session.execute(
            select(Artifact).where(Artifact.message_id == message.id)
        )).scalars().all()
        assert artifacts == []
