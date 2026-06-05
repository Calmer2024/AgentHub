import pytest


class TestCreateAgent:
    async def test_create_with_name(self, test_client):
        res = await test_client.post("/api/agents", json={
            "name": "代码审查员",
            "systemPrompt": "你是代码审查专家。",
            "cliTool": "claude_code",
            "executable": "claude",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "代码审查员"
        assert data["systemPrompt"] == "你是代码审查专家。"
        assert data["agentType"] == "cli_wrapper"
        assert data["cliTool"] == "claude_code"
        assert data["executable"] == "claude"
        assert data["primarySkill"] == "general_coding"
        assert data["auxiliarySkills"] == []
        assert data["contextPolicy"] == "workspace_coding"
        assert "id" in data

    async def test_create_with_skill_profile(self, test_client):
        res = await test_client.post("/api/agents", json={
            "name": "前端专家",
            "cliTool": "claude_code",
            "executable": "claude",
            "primarySkill": "frontend_engineer",
            "auxiliarySkills": ["react", "workspace_editing", "react"],
            "contextPolicy": "workspace_coding",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["primarySkill"] == "frontend_engineer"
        assert data["auxiliarySkills"] == ["react", "workspace_editing"]
        assert data["contextPolicy"] == "workspace_coding"

    async def test_create_defaults(self, test_client):
        res = await test_client.post("/api/agents", json={"name": "Test"})
        assert res.status_code == 201
        data = res.json()
        assert data["agentType"] == "cli_wrapper"
        assert data["cliTool"] == "custom"
        assert data["initArgs"] == []

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
        claude = next(agent for agent in agents if agent["name"] == "Claude Code")
        assert "--verbose" in claude["initArgs"]
        assert claude["envVars"] == {}
        assert claude["primarySkill"] == "general_coding"
        assert "workspace_editing" in claude["auxiliarySkills"]
        codex = next(agent for agent in agents if agent["name"] == "Codex")
        assert "--ignore-user-config" not in codex["initArgs"]
        assert "--dangerously-bypass-approvals-and-sandbox" in codex["initArgs"]
        assert codex["envVars"] == {}

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

    async def test_update_skill_profile(self, test_client, test_agent):
        res = await test_client.patch(f"/api/agents/{test_agent.id}", json={
            "primarySkill": "code_reviewer",
            "auxiliarySkills": ["security", "workspace_editing"],
            "contextPolicy": "review_only",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["primarySkill"] == "code_reviewer"
        assert data["auxiliarySkills"] == ["security", "workspace_editing"]
        assert data["contextPolicy"] == "review_only"

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
    async def test_list_builtin_skills(self, test_client):
        res = await test_client.get("/api/skills")
        assert res.status_code == 200
        skill_ids = {skill["id"] for skill in res.json()}
        assert {"general_coding", "frontend_engineer", "orchestrator_planner"}.issubset(skill_ids)
        general = next(skill for skill in res.json() if skill["id"] == "general_coding")
        assert general["source"] == "builtin"

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
