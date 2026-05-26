import json
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
class TestWebSocket:
    async def test_nonexistent_session_returns_error(self):
        """不存在的会话应返回错误。"""
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/ws/sessions/nonexistent-id")
            assert r.status_code in (404, 426, 400)

class TestWSManager:
    async def test_broadcast_does_not_crash_on_empty(self):
        from app.api.ws_manager import manager
        await manager.broadcast("nonexistent-session", {"type": "test"})

    async def test_manager_connect_disconnect(self):
        from app.api.ws_manager import manager
        # 验证没有连接的 session 不会残留
        assert "test-session-123" not in manager._sessions


@pytest.mark.asyncio
class TestChatWSIntegration:
    async def test_chat_with_ws_broadcast(self, test_client, test_session):
        """聊天时 WS broadcast 不会因无连接而崩溃。"""
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        assert resp.status_code == 200
        # SSE 正常返回
        body = resp.text
        assert "data:" in body
