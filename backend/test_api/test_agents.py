import pytest


class TestCreateAgent:
    async def test_create_with_name(self, test_client):
        res = await test_client.post("/api/agents", json={
            "name": "代码审查员",
            "systemPrompt": "你是代码审查专家。",
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "代码审查员"
        assert data["systemPrompt"] == "你是代码审查专家。"
        assert data["provider"] == "deepseek"
        assert "id" in data

    async def test_create_defaults(self, test_client):
        res = await test_client.post("/api/agents", json={"name": "Test"})
        assert res.status_code == 201
        data = res.json()
        assert data["provider"] == "deepseek"
        assert data["model"] == "deepseek-v4-flash"
        assert data["temperature"] == 0.7

    async def test_create_invalid_provider(self, test_client):
        res = await test_client.post("/api/agents", json={
            "name": "Bad", "provider": "nonexistent"
        })
        assert res.status_code == 400


class TestListAgents:
    async def test_list_empty(self, test_client):
        res = await test_client.get("/api/agents")
        assert res.status_code == 200
        assert res.json() == []

    async def test_list_after_create(self, test_client):
        await test_client.post("/api/agents", json={"name": "A1"})
        await test_client.post("/api/agents", json={"name": "A2"})
        res = await test_client.get("/api/agents")
        assert len(res.json()) == 2


class TestUpdateAgent:
    async def test_update_name(self, test_client, test_agent):
        res = await test_client.patch(f"/api/agents/{test_agent.id}", json={
            "name": "新名称", "temperature": 0.3
        })
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "新名称"
        assert data["temperature"] == 0.3

    async def test_update_nonexistent(self, test_client):
        res = await test_client.patch("/api/agents/nonexistent", json={"name": "X"})
        assert res.status_code == 404


class TestDeleteAgent:
    async def test_soft_delete(self, test_client, test_agent):
        res = await test_client.delete(f"/api/agents/{test_agent.id}")
        assert res.status_code == 200
        # 已软删除，列表不再出现
        r2 = await test_client.get("/api/agents")
        assert len(r2.json()) == 0
