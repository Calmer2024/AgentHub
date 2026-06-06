"""Chat SSE 流式 API 测试 + SSE JSON 合法性回归测试。"""
import json
import sys
import uuid
from pathlib import Path
import pytest

from app.models import Project
from app.agents.cli_events import CliEvent


BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
class TestChatStream:
    async def test_sse_returns_200(self, test_client, test_session):
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        assert resp.status_code == 200

    async def test_sse_events_are_valid_json(self, test_client, test_session):
        """回归测试：修复 {token!r} 导致的 SSE 单引号 JSON 问题。"""
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        lines = [line async for line in resp.aiter_lines()]
        for line in lines:
            if line.startswith("data: "):
                data = json.loads(line[6:])
                assert "done" in data
                if "token" in data:
                    assert isinstance(data["token"], str)

    async def test_sse_stream_collects_all_tokens(self, test_client, test_session):
        """验证流式输出收集了全部 token。"""
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        full_content = ""
        got_done = False
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data["token"]:
                    full_content += data["token"]
                if data["done"]:
                    got_done = True
        assert got_done
        assert full_content == "Hello, World!"

    async def test_sse_final_event_has_message_id(self, test_client, test_session):
        """验证最后的 done 事件包含 message_id。"""
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        last_data = None
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                last_data = json.loads(line[6:])
        assert last_data["done"] is True
        assert "messageId" in last_data
        assert last_data["messageId"] is not None

    async def test_execution_trace_streamed(self, test_client, test_session):
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        trace_events = []
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if data.get("type") == "agent.trace.delta":
                trace_events.append(data)

        assert trace_events
        assert any(event["item"]["kind"] == "process" for event in trace_events)


@pytest.mark.asyncio
class TestChatErrors:
    async def test_empty_content(self, test_client, test_session):
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": ""},
        )
        assert resp.status_code == 400

    async def test_whitespace_only_content(self, test_client, test_session):
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "   "},
        )
        assert resp.status_code == 400

    async def test_nonexistent_session(self, test_client):
        resp = await test_client.post(
            "/api/sessions/nonexistent-id/chat",
            json={"content": "Hello"},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestChatPersistence:
    async def test_messages_persisted_after_chat(self, test_client, test_session):
        """验证聊天完成后 user + assistant 消息都已持久化。"""
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles

    async def test_execution_trace_persisted_after_chat(self, test_client, test_session):
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        assistant = [m for m in resp.json() if m["role"] == "assistant"][0]
        trace = assistant["metadata"]["executionTrace"]

        assert trace["status"] == "completed"
        assert trace["items"]
        assert trace["items"][0]["kind"] == "process"

    async def test_orchestrator_single_chat_persists_structured_plan(self, test_client, db_session, monkeypatch):
        async def fake_stream(self, **kwargs):
            yield CliEvent(
                "agent.output",
                "proc-1",
                chunk=json.dumps({
                    "plan_id": "plan_test",
                    "status": "draft",
                    "tasks": [{
                        "task_id": "T1",
                        "title": "需求澄清",
                        "goal": "明确员工报销业务边界",
                        "required_skills": ["requirements_analyst"],
                        "depends_on": [],
                    }],
                }, ensure_ascii=False),
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-1", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        project = Project(
            id=str(uuid.uuid4()),
            name="测试项目",
            workspace_path=str(BACKEND_ROOT / ".test-workspaces" / str(uuid.uuid4())),
            status="ready",
        )
        Path(project.workspace_path).mkdir(parents=True, exist_ok=True)
        db_session.add(project)
        await db_session.commit()

        agent_res = await test_client.post("/api/agents", json={
            "name": "Orchestrator 调度器",
            "description": "测试调度器",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [],
            "primarySkill": "orchestrator_planner",
            "auxiliarySkills": [],
            "contextPolicy": "planning_only",
        })
        assert agent_res.status_code == 201
        agent_id = agent_res.json()["id"]

        session_res = await test_client.post("/api/sessions", json={
            "title": "调度器单聊",
            "projectId": project.id,
            "agentConfigId": agent_id,
        })
        assert session_res.status_code == 201
        session_id = session_res.json()["id"]

        await test_client.post(f"/api/sessions/{session_id}/chat", json={"content": "生成 draft plan"})
        resp = await test_client.get(f"/api/sessions/{session_id}/messages")
        assistant = [message for message in resp.json() if message["role"] == "assistant"][0]

        assert "orchestratorPlan" in assistant["metadata"], assistant
        assert assistant["metadata"]["orchestratorPlan"]["ok"] is True
        assert assistant["metadata"]["orchestratorPlan"]["normalizedPlan"]["tasks"][0]["title"] == "需求澄清"
        assert "mermaid" in assistant["metadata"]["orchestratorPlan"]["visualization"]

    async def test_multiple_rounds_accumulate(self, test_client, test_session):
        """验证多轮对话消息累积。"""
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Round 1"},
        )
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Round 2"},
        )
        resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        messages = resp.json()
        assert len(messages) == 4  # 2 user + 2 assistant


@pytest.mark.asyncio
class TestMessagesEndpoint:
    async def test_empty_session(self, test_client, test_session):
        resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_messages_well_formed(self, test_client, test_session):
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        messages = resp.json()
        for m in messages:
            assert "id" in m
            assert "sessionId" in m
            assert "role" in m
            assert "content" in m
            assert "createdAt" in m
            assert m["role"] in ("user", "assistant")
