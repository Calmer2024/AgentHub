import pytest


class TestListAgents:
    async def test_returns_agent_list(self, test_client):
        res = await test_client.get("/api/agents")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_each_agent_has_required_fields(self, test_client):
        res = await test_client.get("/api/agents")
        data = res.json()
        for agent in data:
            assert "name" in agent
            assert "displayName" in agent
            assert "provider" in agent
            assert "isAvailable" in agent
            assert "capability" in agent
            cap = agent["capability"]
            assert "supportsStreaming" in cap
            assert "maxContextTokens" in cap
            assert "tags" in cap

    async def test_claude_is_in_list(self, test_client):
        res = await test_client.get("/api/agents")
        names = [a["name"] for a in res.json()]
        assert "claude" in names

    async def test_deepseek_is_in_list(self, test_client):
        res = await test_client.get("/api/agents")
        names = [a["name"] for a in res.json()]
        assert "deepseek" in names

    async def test_gemini_is_in_list(self, test_client):
        res = await test_client.get("/api/agents")
        names = [a["name"] for a in res.json()]
        assert "gemini" in names

    async def test_unavailable_agent_has_reason(self, test_client):
        res = await test_client.get("/api/agents")
        data = res.json()
        for agent in data:
            if not agent["isAvailable"]:
                assert "unavailableReason" in agent


class TestSessionAgentValidation:
    async def test_create_session_with_valid_agent(self, test_client):
        res = await test_client.post("/api/sessions", json={
            "title": "测试",
            "agentName": "claude",
        })
        assert res.status_code == 201
        assert res.json()["agentName"] == "claude"

    async def test_create_session_with_invalid_agent(self, test_client):
        res = await test_client.post("/api/sessions", json={
            "title": "测试",
            "agentName": "nonexistent_agent",
        })
        assert res.status_code == 400
        assert "unknown agent" in res.json()["detail"]

    async def test_update_session_agent(self, test_client, test_session):
        res = await test_client.patch(f"/api/sessions/{test_session}", json={
            "agentName": "deepseek",
        })
        assert res.status_code == 200
        assert res.json()["agentName"] == "deepseek"

    async def test_update_session_invalid_agent(self, test_client, test_session):
        res = await test_client.patch(f"/api/sessions/{test_session}", json={
            "agentName": "invalid_agent",
        })
        assert res.status_code == 400
