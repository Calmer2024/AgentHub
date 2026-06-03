"""Phase 5 artifact versioning, diff, and editing acceptance tests."""

import uuid

import pytest

from app.agents.base import AgentCapability, AgentResponse
from app.models import AgentConfig, Artifact, Message


async def _seed_artifact(db_session, session_id: str, agent_id: str | None = None) -> Artifact:
    message = Message(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="assistant",
        content="生成了一个代码产物",
        agent_name="测试 Agent",
        source_type="agent",
        source_id=agent_id,
        source_name="测试 Agent",
    )
    artifact = Artifact(
        id=str(uuid.uuid4()),
        session_id=session_id,
        message_id=message.id,
        type="code_diff",
        title="hello.py",
        content="def hello():\n    return 'hello'\n",
        status="ready",
        version=1,
    )
    db_session.add_all([message, artifact])
    await db_session.commit()
    return artifact


@pytest.mark.asyncio
class TestPhase5ArtifactVersioning:
    async def test_create_version_then_list_chain_and_diff(self, test_client, db_session, test_session):
        from app.services.artifact_service import ArtifactService

        artifact = await _seed_artifact(db_session, test_session)
        created = await ArtifactService(db_session).create_version(
            artifact.id,
            "def hello(name):\n    return f'hello {name}'\n",
        )

        versions = await test_client.get(f"/api/artifacts/{created.id}/versions")
        assert versions.status_code == 200
        assert [v["version"] for v in versions.json()] == [1, 2]
        assert versions.json()[0]["id"] == artifact.id
        assert versions.json()[1]["id"] == created.id

        diff = await test_client.get(
            f"/api/artifacts/{created.id}/diff",
            params={"v1": 1, "v2": 2},
        )
        assert diff.status_code == 200
        data = diff.json()
        assert data["fromVersion"] == 1
        assert data["toVersion"] == 2
        assert "-def hello():" in data["diff"]
        assert "+def hello(name):" in data["diff"]

    async def test_diff_missing_version_returns_404(self, test_client, db_session, test_session):
        artifact = await _seed_artifact(db_session, test_session)

        diff = await test_client.get(
            f"/api/artifacts/{artifact.id}/diff",
            params={"v1": 1, "v2": 99},
        )

        assert diff.status_code == 404

    async def test_session_artifacts_expose_phase5_fields(self, test_client, db_session, test_session):
        artifact = await _seed_artifact(db_session, test_session)

        resp = await test_client.get(f"/api/sessions/{test_session}/artifacts")

        assert resp.status_code == 200
        data = resp.json()[0]
        assert data["id"] == artifact.id
        assert data["version"] == 1
        assert data["parentArtifactId"] is None

    async def test_session_artifacts_return_latest_heads_only(
        self, test_client, db_session, test_session,
    ):
        from app.services.artifact_service import ArtifactService

        artifact = await _seed_artifact(db_session, test_session)
        created = await ArtifactService(db_session).create_version(
            artifact.id,
            "def hello():\n    return 'v2'\n",
        )

        resp = await test_client.get(f"/api/sessions/{test_session}/artifacts")

        assert resp.status_code == 200
        data = resp.json()
        assert [a["id"] for a in data] == [created.id]
        assert data[0]["parentArtifactId"] == artifact.id


@pytest.mark.asyncio
class TestPhase5ArtifactEditing:
    async def test_preview_edit_does_not_create_version_until_confirmed(
        self, test_client, db_session, test_session,
    ):
        artifact = await _seed_artifact(db_session, test_session)

        preview = await test_client.post(
            f"/api/artifacts/{artifact.id}/edit",
            json={
                "selection": "return 'hello'",
                "instruction": "改成返回 Hello World",
            },
        )

        assert preview.status_code == 200
        preview_data = preview.json()
        assert preview_data["newVersion"] is None
        assert preview_data["artifact"] is None
        assert "Hello World!" in preview_data["proposedContent"]
        assert "+    Hello World!" in preview_data["diff"]["diff"]

        versions = await test_client.get(f"/api/artifacts/{artifact.id}/versions")
        assert [v["version"] for v in versions.json()] == [1]

        applied = await test_client.post(
            f"/api/artifacts/{artifact.id}/edit",
            json={
                "selection": "return 'hello'",
                "instruction": "确认应用",
                "apply": True,
                "proposedContent": preview_data["proposedContent"],
            },
        )

        assert applied.status_code == 200
        applied_data = applied.json()
        assert applied_data["newVersion"] == 2
        assert applied_data["artifact"]["parentArtifactId"] == artifact.id
        assert "Hello World!" in applied_data["artifact"]["content"]

        versions_after = await test_client.get(f"/api/artifacts/{artifact.id}/versions")
        assert [v["version"] for v in versions_after.json()] == [1, 2]

    async def test_selection_not_found_returns_400(self, test_client, db_session, test_session):
        artifact = await _seed_artifact(db_session, test_session)

        resp = await test_client.post(
            f"/api/artifacts/{artifact.id}/edit",
            json={"selection": "missing()", "instruction": "改一下"},
        )

        assert resp.status_code == 400

    async def test_tool_calling_agent_uses_edit_artifact_tool(
        self, test_client, db_session, test_session, monkeypatch,
    ):
        from app.agents.registry import agent_registry

        class ToolAgent:
            MODELS = ["tool-model"]
            DEFAULT_MODEL = "tool-model"

            @property
            def capability(self):
                return AgentCapability(name="tool", supports_tool_call=True)

            async def chat(self, messages, system_prompt, on_token=None, model=None, tools=None):
                assert tools and tools[0]["name"] == "edit_artifact"
                return AgentResponse(
                    content="",
                    tool_calls=[{
                        "name": "edit_artifact",
                        "input": {
                            "selection": "return 'hello'",
                            "instruction": "改返回值",
                            "edit_type": "replace",
                            "replacement": "return 'tool edited'",
                        },
                    }],
                )

            async def chat_stream(self, messages, system_prompt, model=None, tools=None):
                yield "unused"

        agent = AgentConfig(
            id=str(uuid.uuid4()),
            name="工具 Agent",
            provider="deepseek",
            model="tool-model",
        )
        db_session.add(agent)
        await db_session.commit()
        artifact = await _seed_artifact(db_session, test_session, agent.id)
        monkeypatch.setitem(agent_registry._adapters, "deepseek", ToolAgent())

        resp = await test_client.post(
            f"/api/artifacts/{artifact.id}/edit",
            json={"selection": "return 'hello'", "instruction": "改返回值"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy"] == "tool_call"
        assert "return 'tool edited'" in data["proposedContent"]

    async def test_non_tool_agent_falls_back_to_context_injection(
        self, test_client, db_session, test_session, monkeypatch,
    ):
        from app.agents.registry import agent_registry

        class PlainAgent:
            MODELS = ["plain-model"]
            DEFAULT_MODEL = "plain-model"

            @property
            def capability(self):
                return AgentCapability(name="plain", supports_tool_call=False)

            async def chat(self, messages, system_prompt, on_token=None, model=None, tools=None):
                assert tools is None
                prompt = messages[0]["content"]
                assert "选中内容" in prompt
                return AgentResponse(content="return 'fallback edited'")

            async def chat_stream(self, messages, system_prompt, model=None, tools=None):
                yield "unused"

        agent = AgentConfig(
            id=str(uuid.uuid4()),
            name="普通 Agent",
            provider="deepseek",
            model="plain-model",
        )
        db_session.add(agent)
        await db_session.commit()
        artifact = await _seed_artifact(db_session, test_session, agent.id)
        monkeypatch.setitem(agent_registry._adapters, "deepseek", PlainAgent())

        resp = await test_client.post(
            f"/api/artifacts/{artifact.id}/edit",
            json={"selection": "return 'hello'", "instruction": "改返回值"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy"] == "fallback_context"
        assert "return 'fallback edited'" in data["proposedContent"]
