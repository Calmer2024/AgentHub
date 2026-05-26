"""会话 CRUD API 测试。"""
import pytest


@pytest.mark.asyncio
class TestCreateSession:
    async def test_create_with_title(self, test_client):
        resp = await test_client.post("/api/sessions", json={
            "title": "我的会话", "agent_name": "claude"
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "我的会话"
        assert data["agent_name"] == "claude"
        assert "id" in data
        assert "created_at" in data

    async def test_create_default_title(self, test_client):
        resp = await test_client.post("/api/sessions", json={
            "agent_name": "claude"
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "新对话"

    async def test_create_with_defaults(self, test_client):
        """传空 JSON 时使用所有字段的默认值。"""
        resp = await test_client.post("/api/sessions", json={})
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "新对话"
        assert data["agent_name"] == "claude"


@pytest.mark.asyncio
class TestListSessions:
    async def test_empty_list(self, test_client):
        resp = await test_client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(self, test_client):
        await test_client.post("/api/sessions", json={
            "title": "会话1", "agent_name": "claude"
        })
        await test_client.post("/api/sessions", json={
            "title": "会话2", "agent_name": "claude"
        })
        resp = await test_client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert "updated_at" in data[0]


@pytest.mark.asyncio
class TestGetSession:
    async def test_get_existing(self, test_client, test_session):
        resp = await test_client.get(f"/api/sessions/{test_session}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == test_session
        assert data["title"] == "测试会话"

    async def test_get_nonexistent(self, test_client):
        resp = await test_client.get("/api/sessions/nonexistent-id")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]
