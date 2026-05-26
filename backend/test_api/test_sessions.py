import pytest


@pytest.mark.asyncio
class TestCreateSession:
    async def test_create_with_title(self, test_client, test_agent):
        resp = await test_client.post("/api/sessions", json={
            "title": "我的会话", "agentConfigId": test_agent.id
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "我的会话"
        assert data["agentConfigId"] == test_agent.id
        assert "id" in data
        assert "createdAt" in data

    async def test_create_defaults(self, test_client, test_agent):
        """传空 JSON 时自动使用第一个可用 Agent。"""
        resp = await test_client.post("/api/sessions", json={})
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "新对话"
        assert data["agentConfigId"] == test_agent.id

    async def test_create_without_agent(self, test_client, db_session):
        """没有 Agent 时创建会话，agentConfigId 为空。"""
        resp = await test_client.post("/api/sessions", json={"title": "X"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["agentConfigId"] is None


@pytest.mark.asyncio
class TestListSessions:
    async def test_empty_list(self, test_client):
        resp = await test_client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(self, test_client, test_agent):
        await test_client.post("/api/sessions", json={"agentConfigId": test_agent.id})
        await test_client.post("/api/sessions", json={"agentConfigId": test_agent.id})
        resp = await test_client.get("/api/sessions")
        assert len(resp.json()) == 2


@pytest.mark.asyncio
class TestUpdateSession:
    async def test_switch_agent(self, test_client, test_session, db_session):
        from app.models import AgentConfig
        import uuid
        agent2 = AgentConfig(
            id=str(uuid.uuid4()), name="A2", provider="deepseek", model="d"
        )
        db_session.add(agent2)
        await db_session.commit()

        resp = await test_client.patch(f"/api/sessions/{test_session}", json={
            "agentConfigId": agent2.id
        })
        assert resp.status_code == 200
        assert resp.json()["agentConfigId"] == agent2.id

    async def test_switch_invalid_agent(self, test_client, test_session):
        resp = await test_client.patch(f"/api/sessions/{test_session}", json={
            "agentConfigId": "nonexistent-id"
        })
        assert resp.status_code == 400
