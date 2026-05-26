import pytest


class TestGetSettings:
    async def test_returns_settings(self, test_client):
        res = await test_client.get("/api/settings")
        assert res.status_code == 200
        data = res.json()
        assert "openaiApiKey" in data
        assert "deepseekApiKey" in data
        assert "minimaxApiKey" in data
        assert "glmApiKey" in data
        assert "openaiModel" in data
        assert "deepseekModel" in data

    async def test_model_fields_have_defaults(self, test_client):
        res = await test_client.get("/api/settings")
        data = res.json()
        assert data["openaiModel"] == "gpt-4o"
        assert data["deepseekModel"] == "deepseek-v4-flash"
        assert data["glmModel"] == "glm-5.1"


class TestUpdateSettings:
    async def test_update_api_key(self, test_client):
        res = await test_client.put("/api/settings", json={
            "openaiApiKey": "sk-test-key-12345",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["openaiApiKey"] is not None

    async def test_update_model(self, test_client):
        res = await test_client.put("/api/settings", json={
            "openaiModel": "gpt-4o-mini",
        })
        assert res.status_code == 200
        assert res.json()["openaiModel"] == "gpt-4o-mini"

    async def test_empty_body_does_nothing(self, test_client):
        res = await test_client.put("/api/settings", json={})
        assert res.status_code == 200

    async def test_agent_list_still_works_after_key_change(self, test_client):
        await test_client.put("/api/settings", json={
            "deepseekApiKey": "sk-test-key-1234567890",
        })
        res = await test_client.get("/api/agents")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
