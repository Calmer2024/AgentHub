from pathlib import Path

import pytest

from app.agents.cli_adapters import CodexAdapter
from app.services.codex_local_config_service import (
    CodexLocalConfigError,
    CodexLocalConfigService,
)


def test_configure_proxy_writes_codex_home_config_and_env(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    status = CodexLocalConfigService().configure(
        connection="proxy",
        base_url="https://proxy.example.com",
        model="gpt-5.5",
        api_key="proxy-key",
        provider_id="congmingai",
        provider_name="聪明AI",
    )

    assert status.ready is True
    assert status.api_key_set is True
    assert status.base_url == "https://proxy.example.com/v1"
    assert "proxy-key" not in status.to_api().values()

    config = (codex_home / "config.toml").read_text(encoding="utf-8")
    env = (codex_home / ".env").read_text(encoding="utf-8")
    assert 'model_provider = "congmingai"' in config
    assert 'model = "gpt-5.5"' in config
    assert "[model_providers.congmingai]" in config
    assert 'base_url = "https://proxy.example.com/v1"' in config
    assert 'env_key = "CODEX_API_KEY"' not in config
    assert "[model_providers.congmingai.auth]" in config
    assert "codex-auth-helper" in config
    assert "CODEX_API_KEY" in config
    assert "CODEX_API_KEY=proxy-key" in env

    args, runtime_env = CodexAdapter()._apply_connection_settings(["exec", "--json", "-"], {})
    joined = "\n".join(args)
    assert 'model_provider="agenthub_proxy"' in joined
    assert 'model_providers.agenthub_proxy.base_url="https://proxy.example.com/v1"' in joined
    assert runtime_env == {"AGENTHUB_CODEX_PROVIDER_TOKEN": "proxy-key"}


def test_configure_proxy_without_existing_key_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))

    with pytest.raises(CodexLocalConfigError, match="API Key"):
        CodexLocalConfigService().configure(
            connection="proxy",
            base_url="https://proxy.example.com",
            api_key="",
        )


def test_configure_official_can_use_chatgpt_auth(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"auth_mode":"chatgpt","tokens":{"access_token":"token"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    status = CodexLocalConfigService().configure(
        connection="official",
        base_url="https://api.openai.com/v1",
        model="gpt-5.5",
        use_chatgpt_auth=True,
    )

    assert status.ready is True
    assert status.auth_mode == "openai_auth"
    config = (Path(status.codex_home) / "config.toml").read_text(encoding="utf-8")
    assert 'model_provider = "openai"' in config
    assert "requires_openai_auth = true" in config


def test_status_repairs_proxy_key_from_legacy_auth_json(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'model_provider = "OpenAI"\n'
        'model = "gpt-5.5"\n'
        '[model_providers.OpenAI]\n'
        'name = "OpenAI"\n'
        'base_url = "https://proxy.example.com"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = true\n',
        encoding="utf-8",
    )
    (codex_home / "auth.json").write_text(
        '{"auth_mode":"apikey","OPENAI_API_KEY":"legacy-proxy-key"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    status = CodexLocalConfigService().status()

    assert status.ready is True
    assert status.repair_applied is True
    assert status.api_key_source == "dotenv:CODEX_API_KEY"
    assert "legacy-proxy-key" not in status.to_api().values()
    assert (codex_home / ".env").read_text(encoding="utf-8") == "CODEX_API_KEY=legacy-proxy-key\n"

    config = (codex_home / "config.toml").read_text(encoding="utf-8")
    assert 'env_key = "CODEX_API_KEY"' not in config
    assert "[model_providers.OpenAI.auth]" in config
    assert "codex-auth-helper" in config
    assert "requires_openai_auth" not in config

    second = CodexLocalConfigService().status()
    assert second.ready is True
    assert second.repair_applied is False


def test_status_reports_proxy_token_without_api_key_needs_product_input(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'model_provider = "OpenAI"\n'
        '[model_providers.OpenAI]\n'
        'name = "OpenAI"\n'
        'base_url = "https://proxy.example.com"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = true\n',
        encoding="utf-8",
    )
    (codex_home / "auth.json").write_text(
        '{"auth_mode":"chatgpt","OPENAI_API_KEY":null,"tokens":{"access_token":"token"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    status = CodexLocalConfigService().status()

    assert status.ready is False
    assert status.needs_api_key is True
    assert status.has_chatgpt_auth is True
    assert "填写中转 API Key" in status.message
