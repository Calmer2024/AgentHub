"""Read local Codex configuration for AgentHub's Codex CLI adapter."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


AGENTHUB_CODEX_KEYS = {
    "connection": "AGENTHUB_CODEX_CONNECTION",
    "base_url": "AGENTHUB_CODEX_BASE_URL",
    "api_key": "AGENTHUB_CODEX_API_KEY",
    "model": "AGENTHUB_CODEX_MODEL",
    "auth_mode": "AGENTHUB_CODEX_AUTH_MODE",
    "wire_api": "AGENTHUB_CODEX_WIRE_API",
    "home": "AGENTHUB_CODEX_HOME",
}


@dataclass(frozen=True)
class CodexConnectionSettings:
    connection: str = "inherit"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    auth_mode: str = ""
    wire_api: str = "responses"
    provider_name: str = "AgentHub Codex Provider"
    provider_id: str = ""
    source: str = "agenthub"
    api_key_source: str = ""
    missing_env_key: str = ""
    has_chatgpt_auth: bool = False


@dataclass(frozen=True)
class CodexAuthSettings:
    api_key: str = ""
    auth_mode: str = "none"
    api_key_source: str = ""
    missing_env_key: str = ""
    has_chatgpt_auth: bool = False


@dataclass(frozen=True)
class SecretLookup:
    value: str = ""
    source: str = ""


def resolve_codex_connection_settings(
    agent_env: Mapping[str, str],
    *,
    environ: Mapping[str, str] | None = None,
) -> CodexConnectionSettings:
    environ = environ or os.environ
    explicit = _settings_from_agent_env(agent_env)
    if explicit.connection == "inherit":
        return explicit
    if explicit.connection in {"official", "proxy"}:
        return explicit

    detected = _settings_from_codex_home(
        _codex_home(agent_env, environ),
        environ=environ,
    )
    if detected is None:
        return CodexConnectionSettings(model=explicit.model)
    if explicit.model:
        return _replace(detected, model=explicit.model)
    return detected


def _settings_from_agent_env(agent_env: Mapping[str, str]) -> CodexConnectionSettings:
    connection = agent_env.get(AGENTHUB_CODEX_KEYS["connection"], "").strip().lower()
    base_url = agent_env.get(AGENTHUB_CODEX_KEYS["base_url"], "").strip()
    api_key = agent_env.get(AGENTHUB_CODEX_KEYS["api_key"], "").strip()
    model = agent_env.get(AGENTHUB_CODEX_KEYS["model"], "").strip()
    auth_mode = agent_env.get(AGENTHUB_CODEX_KEYS["auth_mode"], "").strip().lower()
    wire_api = agent_env.get(AGENTHUB_CODEX_KEYS["wire_api"], "responses").strip() or "responses"

    if connection == "auto":
        return CodexConnectionSettings(connection="auto", model=model)
    if connection == "inherit":
        return CodexConnectionSettings(connection="inherit", model=model)
    if not connection:
        if base_url or api_key:
            connection = "proxy"
        else:
            return CodexConnectionSettings(connection="auto", model=model)
    if connection == "official" and not base_url:
        base_url = "https://api.openai.com/v1"
    if connection == "proxy":
        auth_mode = "env_key"

    return CodexConnectionSettings(
        connection=connection,
        base_url=base_url,
        api_key=api_key,
        model=model,
        auth_mode=auth_mode,
        wire_api=wire_api,
        source="agenthub",
    )


def _settings_from_codex_home(
    codex_home: Path,
    *,
    environ: Mapping[str, str],
) -> CodexConnectionSettings | None:
    config = _read_toml(codex_home / "config.toml")
    if not config:
        return None

    model = _string(config.get("model"))
    provider_id = _string(config.get("model_provider")) or "openai"
    provider = _provider_config(config, provider_id)
    base_url = _string(provider.get("base_url"))
    if not base_url and provider_id.lower() == "openai":
        base_url = _string(config.get("openai_base_url"))
    if not base_url:
        return CodexConnectionSettings(connection="inherit", model=model, source="codex_config")

    connection = "official" if _is_official_openai_url(base_url) else "proxy"
    auth = _detect_auth_for_provider(
        connection,
        provider,
        codex_home,
        environ,
    )

    return CodexConnectionSettings(
        connection=connection,
        base_url=base_url,
        api_key=auth.api_key,
        model=model,
        auth_mode=auth.auth_mode,
        wire_api=_string(provider.get("wire_api")) or "responses",
        provider_name=_string(provider.get("name")) or "AgentHub Codex Provider",
        provider_id=provider_id,
        source="codex_config",
        api_key_source=auth.api_key_source,
        missing_env_key=auth.missing_env_key,
        has_chatgpt_auth=auth.has_chatgpt_auth,
    )


def _codex_home(agent_env: Mapping[str, str], environ: Mapping[str, str]) -> Path:
    configured = agent_env.get(AGENTHUB_CODEX_KEYS["home"]) or environ.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex"


def _provider_config(config: dict, provider_id: str) -> dict:
    providers = config.get("model_providers")
    if not isinstance(providers, dict):
        return {}
    provider = providers.get(provider_id)
    if not isinstance(provider, dict):
        provider = providers.get(provider_id.lower())
    return provider if isinstance(provider, dict) else {}


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _detect_auth_for_provider(
    connection: str,
    provider: dict,
    codex_home: Path,
    environ: Mapping[str, str],
) -> CodexAuthSettings:
    env_key_name = _string(provider.get("env_key"))
    auth_command = _auth_command(provider)
    requires_openai_auth = provider.get("requires_openai_auth") is True
    has_chatgpt_auth = _auth_json_has_chatgpt_tokens(codex_home)

    if auth_command:
        fallback = _lookup_proxy_api_key(codex_home, environ) if connection == "proxy" else _lookup_secret("OPENAI_API_KEY", codex_home, environ)
        if fallback.value:
            return CodexAuthSettings(
                api_key=fallback.value,
                auth_mode="command",
                api_key_source=fallback.source,
                has_chatgpt_auth=has_chatgpt_auth,
            )
        return CodexAuthSettings(
            auth_mode="command_missing",
            has_chatgpt_auth=has_chatgpt_auth,
        )

    if env_key_name:
        secret = _lookup_secret(env_key_name, codex_home, environ)
        if secret.value:
            return CodexAuthSettings(
                api_key=secret.value,
                auth_mode="env_key",
                api_key_source=secret.source,
                has_chatgpt_auth=has_chatgpt_auth,
            )
        if connection == "proxy":
            fallback = _lookup_proxy_api_key(codex_home, environ)
            if fallback.value:
                return CodexAuthSettings(
                    api_key=fallback.value,
                    auth_mode="env_key",
                    api_key_source=fallback.source,
                    has_chatgpt_auth=has_chatgpt_auth,
                )
        return CodexAuthSettings(
            auth_mode="env_key_missing",
            missing_env_key=env_key_name,
            has_chatgpt_auth=has_chatgpt_auth,
        )

    inline_api_key = _provider_api_key(provider)
    if inline_api_key:
        return CodexAuthSettings(
            api_key=inline_api_key,
            auth_mode="inline_key",
            api_key_source="provider_inline",
            has_chatgpt_auth=has_chatgpt_auth,
        )

    if connection == "proxy":
        secret = _lookup_proxy_api_key(codex_home, environ)
        return CodexAuthSettings(
            api_key=secret.value,
            auth_mode="env_key" if secret.value else (
                "openai_auth" if requires_openai_auth or has_chatgpt_auth else "none"
            ),
            api_key_source=secret.source,
            has_chatgpt_auth=has_chatgpt_auth,
        )

    secret = _lookup_secret("OPENAI_API_KEY", codex_home, environ)
    if not secret.value:
        secret = _auth_json_api_key(codex_home)
    if secret.value:
        auth_mode = "env_key"
    elif requires_openai_auth or has_chatgpt_auth:
        auth_mode = "openai_auth"
    else:
        auth_mode = "none"
    return CodexAuthSettings(
        api_key=secret.value,
        auth_mode=auth_mode,
        api_key_source=secret.source,
        has_chatgpt_auth=has_chatgpt_auth,
    )


def _lookup_proxy_api_key(codex_home: Path, environ: Mapping[str, str]) -> SecretLookup:
    for name in ("CODEX_API_KEY", "OPENAI_API_KEY"):
        secret = _lookup_secret(name, codex_home, environ)
        if secret.value:
            return secret
    return _auth_json_api_key(codex_home)


def _lookup_secret(name: str, codex_home: Path, environ: Mapping[str, str]) -> SecretLookup:
    if not name:
        return SecretLookup()
    value = environ.get(name, "").strip()
    if value:
        return SecretLookup(value=value, source=f"environment:{name}")
    env_file = _read_dotenv(codex_home / ".env")
    value = env_file.get(name, "").strip()
    if value:
        return SecretLookup(value=value, source=f"dotenv:{name}")
    return SecretLookup()


def _read_dotenv(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    result: dict[str, str] = {}
    for line in lines:
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        if clean.startswith("export "):
            clean = clean[len("export "):].strip()
        if "=" not in clean:
            continue
        key, value = clean.split("=", 1)
        result[key.strip()] = _unquote(value.strip())
    return result


def _auth_json_api_key(codex_home: Path) -> SecretLookup:
    data = _read_auth_json(codex_home)
    value = _string(data.get("OPENAI_API_KEY"))
    return SecretLookup(value=value, source="auth_json") if value else SecretLookup()


def _auth_json_has_chatgpt_tokens(codex_home: Path) -> bool:
    data = _read_auth_json(codex_home)
    tokens = data.get("tokens")
    if isinstance(tokens, dict) and any(
        _string(tokens.get(key))
        for key in ("access_token", "id_token", "refresh_token")
    ):
        return True
    return _string(data.get("auth_mode")).lower() == "chatgpt"


def _read_auth_json(codex_home: Path) -> dict:
    try:
        data = json.loads((codex_home / "auth.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _provider_api_key(provider: dict) -> str:
    for key in ("api_key", "apiKey", "token", "bearer_token"):
        value = _string(provider.get(key))
        if value:
            return value
    return ""


def _auth_command(provider: dict) -> str:
    auth = provider.get("auth")
    if not isinstance(auth, dict):
        return ""
    return _string(auth.get("command"))


def _is_official_openai_url(base_url: str) -> bool:
    host = urlsplit(base_url.strip()).hostname or ""
    return host == "api.openai.com" or host.endswith(".api.openai.com")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _replace(settings: CodexConnectionSettings, **updates) -> CodexConnectionSettings:
    values = settings.__dict__.copy()
    values.update(updates)
    return CodexConnectionSettings(**values)
