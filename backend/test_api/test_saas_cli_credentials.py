import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AgentConfig, Project, RuntimeRun, Sandbox, Secret, User
from app.services import cli_credential_service as credential_module
from app.services.cli_credential_schemas import CliModelOptionRead
from app.services.cli_credential_service import CliCredentialService
from app.services.cloud_agent_runtime import CloudAgentRuntimeService


OWNER = {
    "X-AgentHub-User-Email": "cli-owner@example.com",
    "X-AgentHub-User-Name": "CLI Owner",
}


def _events(text: str) -> list[dict]:
    items: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            items.append(json.loads(block[6:]))
    return items


async def _create_codex_cloud_session(test_client):
    agent = await test_client.post(
        "/api/agents",
        json={
            "name": "Codex 凭据门禁 Agent",
            "description": "SaaS credential gate fixture",
            "cliTool": "codex",
            "executable": "codex",
            "initArgs": ["exec", "--json", "-"],
        },
    )
    assert agent.status_code == 201, agent.text
    project = await test_client.post(
        "/api/projects",
        json={"name": "CLI 凭据云端项目", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "CLI 凭据会话",
            "projectId": project.json()["id"],
            "agentConfigId": agent.json()["id"],
        },
        headers=OWNER,
    )
    assert session.status_code == 201, session.text
    return agent.json(), project.json(), session.json()


@pytest.mark.asyncio
async def test_cli_credentials_save_status_and_runtime_config(test_client, db_session, tmp_path):
    agent, project, _session = await _create_codex_cloud_session(test_client)

    initial = await test_client.get("/api/cli-credentials", headers=OWNER)
    assert initial.status_code == 200, initial.text
    assert {item["cliTool"] for item in initial.json()["items"]} == {"claude_code", "codex", "opencode"}
    assert next(item for item in initial.json()["items"] if item["cliTool"] == "codex")["configured"] is False
    assert next(item for item in initial.json()["items"] if item["cliTool"] == "opencode")["authEnvKey"] == "OPENAI_API_KEY"

    saved = await test_client.put(
        "/api/cli-credentials/codex",
        json={
            "providerType": "proxy",
            "providerId": "relay",
            "providerName": "Relay",
            "baseUrl": "https://relay.example/v1",
            "model": "relay-codex[1m]",
            "authEnvKey": "AGENTHUB_CODEX_API_KEY",
            "apiKey": "codex-secret-value",
            "config": {
                "wireApi": "responses",
                "reviewModel": "relay-review",
                "modelReasoningEffort": "high",
                "networkAccess": "enabled",
                "disableResponseStorage": True,
                "requiresOpenaiAuth": True,
            },
        },
        headers=OWNER,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["configured"] is True
    assert body["providerType"] == "proxy"
    assert body["model"] == "relay-codex"
    assert body["config"]["reviewModel"] == "relay-review"
    assert body["config"]["modelReasoningEffort"] == "high"
    assert body["config"]["requiresOpenaiAuth"] is True
    assert "codex-secret-value" not in saved.text

    secret = await db_session.execute(
        select(Secret).where(Secret.name == "AGENTHUB_CODEX_API_KEY")
    )
    assert secret.scalars().first() is not None

    user = await test_client.get("/api/auth/me", headers=OWNER)
    actor_id = user.json()["id"]
    actor = await db_session.get(User, actor_id)
    db_project = await db_session.get(Project, project["id"])
    db_agent = await db_session.get(AgentConfig, agent["id"])
    env = await CliCredentialService(db_session).prepare_env_for_agent(
        db_agent,
        actor=actor,
        project=db_project,
        workspace_path=str(tmp_path),
        env_vars={"AGENTHUB_CODEX_API_KEY": "codex-secret-value"},
    )
    config_path = Path(tmp_path) / ".agenthub" / "runtime-config" / "codex" / "config.toml"
    assert config_path.exists()
    config_text = config_path.read_text(encoding="utf-8")
    assert 'model = "relay-codex"' in config_text
    assert 'review_model = "relay-review"' in config_text
    assert 'model_reasoning_effort = "high"' in config_text
    assert 'base_url = "https://relay.example/v1"' in config_text
    assert 'env_key = "AGENTHUB_CODEX_API_KEY"' in config_text
    assert 'wire_api = "responses"' in config_text
    assert "requires_openai_auth = true" in config_text
    assert "codex-secret-value" not in config_text
    assert env["CODEX_HOME"] == "/workspace/.agenthub/runtime-config/codex"


@pytest.mark.asyncio
async def test_opencode_model_catalog_uses_models_dev_source(test_client, monkeypatch):
    def fake_models(provider_id: str):
        assert provider_id == "deepseek"
        return [
            CliModelOptionRead(
                id="deepseek-v4-pro",
                name="DeepSeek V4 Pro",
                label="DeepSeek V4 Pro",
                provider_id="deepseek",
                reasoning=True,
                tool_call=True,
                context=1048576,
                output=1048576,
                last_updated="2026-04-24",
            )
        ]

    monkeypatch.setattr(credential_module, "_models_dev_options", fake_models)

    response = await test_client.get(
        "/api/cli-credentials/opencode/models?providerId=deepseek",
        headers=OWNER,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "models.dev"
    assert body["providerId"] == "deepseek"
    assert body["items"][0]["id"] == "deepseek-v4-pro"
    assert body["items"][0]["toolCall"] is True


@pytest.mark.asyncio
async def test_opencode_runtime_config_disables_tui_update_prompt(test_client, db_session, tmp_path):
    agent = await test_client.post(
        "/api/agents",
        json={
            "name": "OpenCode Agent",
            "description": "OpenCode credential fixture",
            "cliTool": "opencode",
            "executable": "opencode",
            "initArgs": ["run", "--pure", "--format", "json", "--dangerously-skip-permissions"],
        },
    )
    assert agent.status_code == 201, agent.text
    project = await test_client.post(
        "/api/projects",
        json={"name": "OpenCode 云端项目", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    saved = await test_client.put(
        "/api/cli-credentials/opencode",
        json={
            "providerType": "proxy",
            "providerId": "deepseek",
            "providerName": "DeepSeek",
            "baseUrl": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-pro",
            "authEnvKey": "DEEPSEEK_API_KEY",
            "apiKey": "opencode-secret-value",
        },
        headers=OWNER,
    )
    assert saved.status_code == 200, saved.text

    user = await test_client.get("/api/auth/me", headers=OWNER)
    actor = await db_session.get(User, user.json()["id"])
    db_project = await db_session.get(Project, project.json()["id"])
    db_agent = await db_session.get(AgentConfig, agent.json()["id"])
    env = await CliCredentialService(db_session).prepare_env_for_agent(
        db_agent,
        actor=actor,
        project=db_project,
        workspace_path=str(tmp_path),
        env_vars={"DEEPSEEK_API_KEY": "opencode-secret-value"},
    )

    assert env["OPENCODE_DISABLE_AUTOUPDATE"] == "1"
    assert env["CI"] == "1"
    assert env["OPENCODE_CONFIG"] == "/workspace/.agenthub/runtime-config/opencode/opencode.json"
    assert "opencode-secret-value" not in (Path(tmp_path) / ".agenthub" / "runtime-config" / "opencode" / "opencode.json").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_native_cli_requires_config_before_cloud_runtime_starts(test_client, db_session):
    _agent, _project, session = await _create_codex_cloud_session(test_client)

    response = await test_client.post(
        f"/api/sessions/{session['id']}/chat",
        json={"content": "需要 Codex 执行"},
        headers=OWNER,
    )
    assert response.status_code == 200, response.text
    events = _events(response.text)
    assert events[-1]["type"] == "error"
    assert "请先配置 Codex API Key" in events[-1]["error"]

    runs = await db_session.execute(select(RuntimeRun))
    sandboxes = await db_session.execute(select(Sandbox))
    assert runs.scalars().all() == []
    assert sandboxes.scalars().all() == []


@pytest.mark.asyncio
async def test_codex_proxy_preserves_openai_provider_id_for_cloud_runtime(test_client, db_session, tmp_path):
    agent, project, _session = await _create_codex_cloud_session(test_client)

    saved = await test_client.put(
        "/api/cli-credentials/codex",
        json={
            "providerType": "proxy",
            "providerId": "OpenAI",
            "providerName": "OpenAI",
            "baseUrl": "https://sub2.congmingai.com",
            "model": "gpt-5.5",
            "authEnvKey": "OPENAI_API_KEY",
            "apiKey": "codex-secret-value",
        },
        headers=OWNER,
    )
    assert saved.status_code == 200, saved.text

    user = await test_client.get("/api/auth/me", headers=OWNER)
    actor = await db_session.get(User, user.json()["id"])
    db_project = await db_session.get(Project, project["id"])
    db_agent = await db_session.get(AgentConfig, agent["id"])
    await CliCredentialService(db_session).prepare_env_for_agent(
        db_agent,
        actor=actor,
        project=db_project,
        workspace_path=str(tmp_path),
        env_vars={"OPENAI_API_KEY": "codex-secret-value"},
    )

    config_text = (Path(tmp_path) / ".agenthub" / "runtime-config" / "codex" / "config.toml").read_text(encoding="utf-8")
    assert 'model = "gpt-5.5"' in config_text
    assert 'review_model = "gpt-5.5"' in config_text
    assert 'model_provider = "OpenAI"' in config_text
    assert '[model_providers.OpenAI]' in config_text
    assert 'base_url = "https://sub2.congmingai.com"' in config_text
    assert 'env_key = "OPENAI_API_KEY"' in config_text
    assert 'wire_api = "responses"' in config_text
    assert "codex-secret-value" not in config_text


@pytest.mark.asyncio
async def test_cloud_runtime_restores_default_args_for_empty_builtin_cli(test_client, db_session, tmp_path):
    agent_response = await test_client.post(
        "/api/agents",
        json={
            "name": "Codex",
            "description": "历史空参数内置 Agent",
            "cliTool": "codex",
            "executable": "",
            "initArgs": [],
        },
        headers=OWNER,
    )
    assert agent_response.status_code == 201, agent_response.text
    project_response = await test_client.post(
        "/api/projects",
        json={"name": "空参数云端项目", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project_response.status_code == 201, project_response.text
    saved = await test_client.put(
        "/api/cli-credentials/codex",
        json={
            "providerType": "proxy",
            "providerId": "OpenAI",
            "providerName": "OpenAI",
            "baseUrl": "https://sub2.congmingai.com",
            "model": "gpt-5.5",
            "authEnvKey": "OPENAI_API_KEY",
            "apiKey": "codex-secret-value",
        },
        headers=OWNER,
    )
    assert saved.status_code == 200, saved.text

    user = await test_client.get("/api/auth/me", headers=OWNER)
    actor = await db_session.get(User, user.json()["id"])
    db_project = await db_session.get(Project, project_response.json()["id"])
    db_agent = await db_session.get(AgentConfig, agent_response.json()["id"])
    runtime_agent = await CloudAgentRuntimeService(db_session)._runtime_agent(
        db_agent,
        actor=actor,
        project=db_project,
        workspace_path=str(tmp_path),
    )

    args = json.loads(runtime_agent.init_args)
    assert runtime_agent.executable == "codex"
    assert args[:2] == ["exec", "--skip-git-repo-check"]
    assert "--json" in args
    assert args[-1] == "-"


@pytest.mark.asyncio
async def test_cli_credentials_reject_url_api_key(test_client):
    response = await test_client.put(
        "/api/cli-credentials/claude_code",
        json={
            "providerType": "cc_switch",
            "providerId": "deepseek",
            "providerName": "DeepSeek",
            "baseUrl": "https://api.deepseek.com/anthropic",
            "model": "deepseek-v4-pro",
            "authEnvKey": "ANTHROPIC_API_KEY",
            "apiKey": "https://api.deepseek.com/anthropic",
        },
        headers=OWNER,
    )

    assert response.status_code == 400, response.text
    assert "API Key 不能填写 URL" in response.text


@pytest.mark.asyncio
async def test_claude_code_deepseek_anthropic_config_injects_runtime_env(test_client, db_session, tmp_path):
    agent_response = await test_client.post(
        "/api/agents",
        json={
            "name": "Claude Code DeepSeek Agent",
            "description": "DeepSeek Anthropic credential fixture",
            "cliTool": "claude_code",
            "executable": "claude",
            "initArgs": ["--print"],
        },
    )
    assert agent_response.status_code == 201, agent_response.text
    project_response = await test_client.post(
        "/api/projects",
        json={"name": "DeepSeek Anthropic 项目", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project_response.status_code == 201, project_response.text
    saved = await test_client.put(
        "/api/cli-credentials/claude_code",
        json={
            "providerType": "cc_switch",
            "providerId": "deepseek",
            "providerName": "DeepSeek",
            "baseUrl": "https://api.deepseek.com/anthropic",
            "model": "deepseek-v4-pro[1m]",
            "authEnvKey": "ANTHROPIC_AUTH_TOKEN",
            "apiKey": "sk-test-deepseek",
        },
        headers=OWNER,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["model"] == "deepseek-v4-pro"

    user = await test_client.get("/api/auth/me", headers=OWNER)
    actor = await db_session.get(User, user.json()["id"])
    db_project = await db_session.get(Project, project_response.json()["id"])
    db_agent = await db_session.get(AgentConfig, agent_response.json()["id"])
    env = await CliCredentialService(db_session).prepare_env_for_agent(
        db_agent,
        actor=actor,
        project=db_project,
        workspace_path=str(tmp_path),
        env_vars={"ANTHROPIC_AUTH_TOKEN": "sk-test-deepseek"},
    )

    assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert env["ANTHROPIC_MODEL"] == "deepseek-v4-pro"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-test-deepseek"
    assert env["AGENTHUB_CLI_PROVIDER_TYPE"] == "cc_switch"
