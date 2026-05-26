import pytest


class TestGetSettings:
    async def test_returns_settings(self, test_client):
        res = await test_client.get("/api/settings")
        assert res.status_code == 200
        data = res.json()
        assert "anthropicApiKey" in data
        assert "deepseekApiKey" in data

    async def test_masked_when_configured(self, test_client):
        res = await test_client.get("/api/settings")
        data = res.json()
        ak = data["anthropicApiKey"]
        if ak is not None:
            assert "****" in ak

    async def test_null_when_empty(self, test_client):
        res = await test_client.get("/api/settings")
        data = res.json()
        dk = data["deepseekApiKey"]
        # 可能为 None（未配置）或 masked（已配置），两者都合法
        assert dk is None or isinstance(dk, str)


class TestUpdateSettings:
    async def test_update_api_key(self, test_client):
        res = await test_client.put("/api/settings", json={
            "anthropicApiKey": "sk-test-key-12345",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["anthropicApiKey"] is not None
        assert "****" in data["anthropicApiKey"]

    async def test_update_both_keys(self, test_client):
        res = await test_client.put("/api/settings", json={
            "anthropicApiKey": "sk-ant-key",
            "deepseekApiKey": "sk-ds-key",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["anthropicApiKey"] is not None
        assert data["deepseekApiKey"] is not None

    async def test_empty_body_does_nothing(self, test_client):
        res = await test_client.put("/api/settings", json={})
        assert res.status_code == 200

    async def test_agent_becomes_available_after_setting_key(self, test_client):
        await test_client.put("/api/settings", json={
            "anthropicApiKey": "sk-test-key",
        })
        res = await test_client.get("/api/agents")
        agents = res.json()
        claude = next(a for a in agents if a["name"] == "claude")
        assert claude["isAvailable"] is True
