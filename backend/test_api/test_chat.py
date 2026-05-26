"""Chat SSE 流式 API 测试 + SSE JSON 合法性回归测试。"""
import json
import pytest


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
        assert "message_id" in last_data
        assert last_data["message_id"] is not None


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
