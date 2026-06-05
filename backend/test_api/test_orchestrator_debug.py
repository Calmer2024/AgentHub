import json

import pytest


VALID_PLAN = {
    "plan_id": "plan_001",
    "status": "draft",
    "execution_policy": "manual_approval_required",
    "tasks": [
        {
            "task_id": "T1",
            "title": "需求澄清",
            "goal": "明确报销单权限边界",
            "required_skills": ["product_analysis"],
            "assigned_agent_id": "mock_architect",
            "assigned_agent_name": "架构专家",
            "assignment_reason": "匹配架构能力",
            "depends_on": [],
            "expected_outputs": ["document"],
            "acceptance_criteria": ["列出角色权限"],
            "needs_approval": True,
            "is_blocking": True,
        },
        {
            "task_id": "T2",
            "title": "API 契约",
            "goal": "定义报销单 API",
            "required_skills": ["api_design"],
            "assigned_agent_id": "mock_backend",
            "assigned_agent_name": "后端专家",
            "assignment_reason": "匹配后端 API 能力",
            "depends_on": ["T1"],
            "expected_outputs": ["document"],
            "acceptance_criteria": ["产出接口列表"],
            "needs_approval": True,
            "is_blocking": True,
        },
    ],
    "execution_strategy": {
        "summary": "先需求后契约",
        "phases": [
            {"phase": 1, "mode": "serial", "tasks": ["T1", "T2"], "reason": "契约依赖需求"},
        ],
    },
}


@pytest.mark.asyncio
async def test_build_orchestrator_input_returns_prompt(test_client):
    res = await test_client.post("/api/debug/orchestrator/build-input", json={
        "content": "开发员工报销单管理系统",
        "useMockAgents": True,
    })

    assert res.status_code == 200
    data = res.json()
    assert data["input"]["content"] == "开发员工报销单管理系统"
    assert data["input"]["agentCount"] == 5
    assert data["orchestratorAgent"]["engine"] == "manual_bridge"
    assert "只输出一个 JSON 对象" in data["prompt"]
    assert data["outputSchema"]["status"] == "draft"


@pytest.mark.asyncio
async def test_generate_orchestrator_plan_is_not_available_on_cli_baseline(test_client):
    res = await test_client.post("/api/debug/orchestrator/generate-plan", json={
        "content": "开发员工报销单管理系统",
        "useMockAgents": True,
    })

    assert res.status_code == 501
    assert "@Orchestrator" in res.json()["detail"]


@pytest.mark.asyncio
async def test_generate_orchestrator_plan_rejects_empty_content(test_client):
    res = await test_client.post("/api/debug/orchestrator/generate-plan", json={
        "content": "   ",
    })

    assert res.status_code == 400


@pytest.mark.asyncio
async def test_build_orchestrator_input_rejects_empty_content(test_client):
    res = await test_client.post("/api/debug/orchestrator/build-input", json={
        "content": "   ",
    })

    assert res.status_code == 400


@pytest.mark.asyncio
async def test_parse_orchestrator_output_accepts_fenced_json(test_client):
    raw = "```json\n" + json.dumps(VALID_PLAN, ensure_ascii=False) + "\n```"
    res = await test_client.post("/api/debug/orchestrator/parse-output", json={
        "rawOutput": raw,
        "candidateAgents": [
            {"id": "mock_architect", "name": "架构专家"},
            {"id": "mock_backend", "name": "后端专家"},
        ],
    })

    assert res.status_code == 200
    data = res.json()
    assert data["validation"]["ok"] is True
    assert data["normalizedPlan"]["tasks"][1]["depends_on"] == ["T1"]
    assert "graph TD" in data["visualization"]["mermaid"]


@pytest.mark.asyncio
async def test_parse_orchestrator_output_reports_missing_dependency(test_client):
    plan = {**VALID_PLAN, "tasks": [{**VALID_PLAN["tasks"][0], "depends_on": ["missing"]}]}
    res = await test_client.post("/api/debug/orchestrator/parse-output", json={
        "rawOutput": json.dumps(plan, ensure_ascii=False),
        "candidateAgents": [{"id": "mock_architect", "name": "架构专家"}],
    })

    assert res.status_code == 200
    data = res.json()
    assert data["validation"]["ok"] is False
    assert any("不存在的任务" in e for e in data["validation"]["errors"])


@pytest.mark.asyncio
async def test_parse_orchestrator_output_reports_cycle(test_client):
    plan = {
        **VALID_PLAN,
        "tasks": [
            {**VALID_PLAN["tasks"][0], "depends_on": ["T2"]},
            {**VALID_PLAN["tasks"][1], "depends_on": ["T1"]},
        ],
    }
    res = await test_client.post("/api/debug/orchestrator/parse-output", json={
        "rawOutput": json.dumps(plan, ensure_ascii=False),
        "candidateAgents": [
            {"id": "mock_architect", "name": "架构专家"},
            {"id": "mock_backend", "name": "后端专家"},
        ],
    })

    assert res.status_code == 200
    data = res.json()
    assert data["validation"]["ok"] is False
    assert any("循环依赖" in e for e in data["validation"]["errors"])


@pytest.mark.asyncio
async def test_parse_orchestrator_output_warns_unknown_agent(test_client):
    plan = {
        **VALID_PLAN,
        "tasks": [{**VALID_PLAN["tasks"][0], "assigned_agent_id": "missing_agent"}],
    }
    res = await test_client.post("/api/debug/orchestrator/parse-output", json={
        "rawOutput": json.dumps(plan, ensure_ascii=False),
        "candidateAgents": [{"id": "mock_architect", "name": "架构专家"}],
    })

    assert res.status_code == 200
    data = res.json()
    assert data["validation"]["ok"] is True
    assert any("不在候选 Agent" in w for w in data["validation"]["warnings"])
