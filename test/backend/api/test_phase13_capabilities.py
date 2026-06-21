import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_capabilities_default_local_desktop(test_client):
    response = await test_client.get("/api/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["edition"] == "local"
    assert body["surface"] == "desktop"
    assert body["authRequired"] is False
    assert body["features"]["localWorkspace"] is True
    assert body["features"]["localCliRuntime"] is True
    assert body["features"]["cloudWorkspace"] is False
    assert body["features"]["deployment"] is False


@pytest.mark.asyncio
async def test_capabilities_saas_mobile_matrix(test_client, monkeypatch):
    monkeypatch.setattr(settings, "agenthub_edition", "saas")
    monkeypatch.setattr(settings, "agenthub_surface", "mobile")
    monkeypatch.setattr(settings, "agenthub_api_base_url", "https://api.agenthub.example")

    response = await test_client.get("/api/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["edition"] == "saas"
    assert body["surface"] == "mobile"
    assert body["authRequired"] is True
    assert body["apiBaseUrl"] == "https://api.agenthub.example"
    assert body["features"]["cloudWorkspace"] is True
    assert body["features"]["notifications"] is True
    assert body["features"]["mobileApprovals"] is True
    assert body["features"]["localWorkspace"] is False
    assert body["features"]["deployment"] is False
