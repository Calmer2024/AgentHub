import pytest


@pytest.mark.asyncio
async def test_orchestrator_debug_dry_run_returns_dag(test_client):
    res = await test_client.post("/api/debug/orchestrator/dry-run", json={
        "content": "先设计登录系统再前后端实现最后审查",
        "useMockAgents": True,
    })

    assert res.status_code == 200
    data = res.json()
    assert data["intent"]["type"] == "code_gen"
    assert data["executionPlan"]["mode"] == "dag"
    assert data["executionPlan"]["decomposerUsed"] is True
    assert [p["phase"] for p in data["executionPlan"]["dagPhases"]] == [0, 1, 2]
    assert "flowchart LR" in data["visualization"]["mermaid"]
    assert "planning" in data["visualization"]["mermaid"]


@pytest.mark.asyncio
async def test_orchestrator_debug_rejects_empty_content(test_client):
    res = await test_client.post("/api/debug/orchestrator/dry-run", json={
        "content": "   ",
    })

    assert res.status_code == 400
