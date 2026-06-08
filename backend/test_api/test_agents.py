import json
import uuid

import pytest

from app.models import AgentConfig


class TestCreateAgent:
    async def test_create_with_name(self, test_client):
        res = await test_client.post("/api/agents", json={
            "name": "代码审查员",
            "systemPrompt": "你是代码审查专家。",
            "rules": "回答先列风险，再给建议。",
            "cliTool": "claude_code",
            "executable": "claude",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "代码审查员"
        assert data["systemPrompt"] == "你是代码审查专家。"
        assert data["rules"] == "回答先列风险，再给建议。"
        assert data["agentType"] == "cli_wrapper"
        assert data["cliTool"] == "claude_code"
        assert data["executable"] == "claude"
        assert data["toolset"] == []
        assert data["primarySkill"] == "general_coding"
        assert data["auxiliarySkills"] == []
        assert data["contextPolicy"] == "workspace_coding"
        assert data["avatar"] == ""
        assert "id" in data

    async def test_create_with_toolset_and_avatar(self, test_client):
        res = await test_client.post("/api/agents", json={
            "name": "前端工程师",
            "cliTool": "claude_code",
            "executable": "claude",
            "toolset": ["local-ui", "local-ui", "local-test"],
            "avatar": "preset:blue",
            "contextPolicy": "workspace_coding",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["toolset"] == ["local-ui", "local-test"]
        assert data["avatar"] == "preset:blue"
        assert data["contextPolicy"] == "workspace_coding"

    async def test_create_defaults(self, test_client):
        res = await test_client.post("/api/agents", json={"name": "Test"})
        assert res.status_code == 201
        data = res.json()
        assert data["agentType"] == "cli_wrapper"
        assert data["cliTool"] == "custom"
        assert data["initArgs"] == []
        assert data["systemPrompt"] == ""
        assert data["rules"] == ""

    async def test_rejects_legacy_http_agent_type(self, test_client):
        res = await test_client.post("/api/agents", json={
            "name": "Bad", "agentType": "http_provider"
        })
        assert res.status_code == 400

    async def test_agent_env_vars_drop_provider_api_keys(self, test_client):
        res = await test_client.post("/api/agents", json={
            "name": "Safe CLI",
            "cliTool": "custom",
            "executable": "safe-cli",
            "envVars": {
                "ANTHROPIC_API_KEY": "old",
                "OPENAI_API_KEY": "old",
                "DEEPSEEK_API_KEY": "internal",
                "CUSTOM_FLAG": "1",
            },
        })
        assert res.status_code == 201
        assert res.json()["envVars"] == {"CUSTOM_FLAG": "1"}

    async def test_codex_agent_allows_scoped_proxy_key_only(self, test_client):
        res = await test_client.post("/api/agents", json={
            "name": "Codex Proxy",
            "cliTool": "codex",
            "executable": "codex",
            "envVars": {
                "OPENAI_API_KEY": "old",
                "AGENTHUB_CODEX_BASE_URL": "https://proxy.example.com/v1",
                "AGENTHUB_CODEX_API_KEY": "proxy-key",
                "AGENTHUB_CODEX_MODEL": "gpt-5.5",
            },
        })
        assert res.status_code == 201
        assert res.json()["envVars"] == {
            "AGENTHUB_CODEX_BASE_URL": "https://proxy.example.com/v1",
            "AGENTHUB_CODEX_API_KEY": "proxy-key",
            "AGENTHUB_CODEX_MODEL": "gpt-5.5",
        }

    async def test_check_executable(self, test_client):
        res = await test_client.get("/api/agents/check-executable", params={"path": "definitely-missing-agenthub-cli"})
        assert res.status_code == 200
        assert res.json()["found"] is False

    async def test_codex_config_api_writes_local_config_without_returning_key(self, test_client, tmp_path, monkeypatch):
        monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))

        res = await test_client.put("/api/agents/codex-config", json={
            "connection": "proxy",
            "baseUrl": "https://proxy.example.com",
            "model": "gpt-5.5",
            "apiKey": "proxy-key",
            "providerId": "proxy",
            "providerName": "Proxy",
        })

        assert res.status_code == 200
        data = res.json()
        assert data["ready"] is True
        assert data["apiKeySet"] is True
        assert "proxy-key" not in res.text

        status = await test_client.get("/api/agents/codex-config")
        assert status.status_code == 200
        assert status.json()["baseUrl"] == "https://proxy.example.com/v1"
        assert "proxy-key" not in status.text


class TestListAgents:
    async def test_list_has_default_seed(self, test_client):
        """lifespan 创建三个默认 CLI Agent。"""
        res = await test_client.get("/api/agents")
        assert res.status_code == 200
        agents = res.json()
        names = {agent["name"] for agent in agents}
        assert {"Claude Code", "Codex", "OpenCode"}.issubset(names)
        assert "Orchestrator 调度器" in names
        assert {
            "产品经理",
            "UX/UI设计师",
            "测试工程师",
            "前端工程师",
            "后端工程师",
            "数据库工程师",
            "系统架构师",
            "需求分析师",
            "文档专家",
        }.isdisjoint(names)
        claude = next(agent for agent in agents if agent["name"] == "Claude Code")
        assert "--verbose" in claude["initArgs"]
        assert claude["envVars"] == {}
        assert claude["toolset"] == []
        orchestrator = next(agent for agent in agents if agent["name"] == "Orchestrator 调度器")
        assert orchestrator["primarySkill"] == "orchestrator_planner"
        codex = next(agent for agent in agents if agent["name"] == "Codex")
        assert "--ignore-user-config" not in codex["initArgs"]
        assert "--dangerously-bypass-approvals-and-sandbox" in codex["initArgs"]
        assert codex["envVars"] == {}

    async def test_seed_default_agents_endpoint_is_idempotent(self, test_client):
        first = await test_client.post("/api/agents/seed-defaults")
        assert first.status_code == 200
        second = await test_client.post("/api/agents/seed-defaults")
        assert second.status_code == 200

        agents = second.json()
        names = [agent["name"] for agent in agents]
        assert names.count("Orchestrator 调度器") == 1
        assert names.count("产品经理") == 0
        assert names.count("UX/UI设计师") == 0
        orchestrator = next(agent for agent in agents if agent["name"] == "Orchestrator 调度器")
        assert orchestrator["primarySkill"] == "orchestrator_planner"
        assert orchestrator["contextPolicy"] == "planning_only"

    async def test_seed_archives_old_template_agents_without_hiding_user_agent(self, test_client, db_session):
        old_template = AgentConfig(
            id=str(uuid.uuid4()),
            name="前端工程师",
            description="旧版本自动 seed 模板",
            system_prompt="template",
            rules="",
            agent_type="cli_wrapper",
            cli_tool="codex",
            executable="codex",
            init_args="[]",
            env_vars="{}",
            primary_skill="frontend_engineer",
            auxiliary_skills="[]",
            toolset=json.dumps(["react_typescript"], ensure_ascii=False),
            context_policy="workspace_coding",
            avatar="preset:blue",
            is_active=True,
        )
        user_agent = AgentConfig(
            id=str(uuid.uuid4()),
            name="前端工程师",
            description="用户手动创建的同名 Agent",
            system_prompt="custom",
            rules="",
            agent_type="cli_wrapper",
            cli_tool="custom",
            executable="echo",
            init_args="[]",
            env_vars="{}",
            primary_skill="general_coding",
            auxiliary_skills="[]",
            toolset="[]",
            context_policy="workspace_coding",
            avatar="preset:blue",
            is_active=True,
        )
        db_session.add_all([old_template, user_agent])
        await db_session.commit()

        res = await test_client.post("/api/agents/seed-defaults")
        assert res.status_code == 200
        agents = res.json()
        frontend_agents = [agent for agent in agents if agent["name"] == "前端工程师"]
        assert [agent["id"] for agent in frontend_agents] == [user_agent.id]

        await db_session.refresh(old_template)
        assert old_template.is_active is False

    async def test_configure_builtin_agents_codex_keeps_orchestrator_only(self, test_client):
        res = await test_client.post("/api/agents/configure-builtins-codex")
        assert res.status_code == 200

        agents = res.json()
        role_names = {"Orchestrator 调度器"}
        role_agents = [agent for agent in agents if agent["name"] in role_names]

        assert {agent["name"] for agent in role_agents} == role_names
        assert all(agent["cliTool"] == "codex" for agent in role_agents)
        assert all(agent["executable"] == "codex" for agent in role_agents)
        assert all(agent["initArgs"][:2] == ["exec", "--skip-git-repo-check"] for agent in role_agents)

        orchestrator = next(agent for agent in role_agents if agent["name"] == "Orchestrator 调度器")
        assert orchestrator["primarySkill"] == "orchestrator_planner"
        assert orchestrator["contextPolicy"] == "planning_only"
        names = {agent["name"] for agent in agents}
        assert "前端工程师" not in names

    async def test_list_after_create(self, test_client):
        res_before = await test_client.get("/api/agents")
        count_before = len(res_before.json())
        await test_client.post("/api/agents", json={"name": "A1"})
        await test_client.post("/api/agents", json={"name": "A2"})
        res = await test_client.get("/api/agents")
        assert len(res.json()) == count_before + 2


class TestUpdateAgent:
    async def test_update_name(self, test_client, test_agent):
        res = await test_client.patch(f"/api/agents/{test_agent.id}", json={
            "name": "新名称", "initArgs": ["--verbose"]
        })
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "新名称"
        assert data["initArgs"] == ["--verbose"]

    async def test_update_toolset_and_avatar(self, test_client, test_agent):
        res = await test_client.patch(f"/api/agents/{test_agent.id}", json={
            "toolset": ["local-review", "local-review", "local-security"],
            "avatar": "preset:green",
            "contextPolicy": "review_only",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["toolset"] == ["local-review", "local-security"]
        assert data["avatar"] == "preset:green"
        assert data["contextPolicy"] == "review_only"

    async def test_update_identity_and_rules(self, test_client, test_agent):
        res = await test_client.patch(f"/api/agents/{test_agent.id}", json={
            "systemPrompt": "你是家庭资产管理项目的后端专家。",
            "rules": "所有说明使用中文；不要扩大 MVP 范围。",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["systemPrompt"] == "你是家庭资产管理项目的后端专家。"
        assert data["rules"] == "所有说明使用中文；不要扩大 MVP 范围。"

    async def test_update_nonexistent(self, test_client):
        res = await test_client.patch("/api/agents/nonexistent", json={"name": "X"})
        assert res.status_code == 404


class TestDeleteAgent:
    async def test_soft_delete(self, test_client, test_agent):
        before = (await test_client.get("/api/agents")).json()
        res = await test_client.delete(f"/api/agents/{test_agent.id}")
        assert res.status_code == 200
        r2 = await test_client.get("/api/agents")
        assert len(r2.json()) == len(before) - 1  # 软删除后少一个


class TestSkillsApi:
    async def test_list_skills_exposes_filesystem_only(self, test_client):
        res = await test_client.get("/api/skills")
        assert res.status_code == 200
        assert all(skill["source"] == "filesystem" for skill in res.json())
        skill_ids = {skill["id"] for skill in res.json()}
        assert "api_designer" not in skill_ids
        assert "ux_designer" not in skill_ids

    async def test_list_filesystem_skills(self, test_client, monkeypatch):
        monkeypatch.setenv("AGENTHUB_SKILL_ROOTS", "test_fixtures/skills")

        res = await test_client.get("/api/skills")

        assert res.status_code == 200
        skill = next(item for item in res.json() if item["id"] == "local-fixture-skill")
        assert skill["name"] == "local-fixture-skill"
        assert skill["description"] == "Local fixture skill for registry tests."
        assert skill["source"] == "filesystem"
        assert skill["path"].endswith("SKILL.md")
        assert "fixture" in skill["tags"]
