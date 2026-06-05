"""Read and repair the host Codex CLI connection config.

The API key belongs to the user's local Codex installation, not to an
AgentHub Agent row. AgentHub stores stable proxy credentials in CODEX_HOME/.env
and points the selected Codex provider at a command-backed auth helper. That
keeps native Codex sessions working without requiring a global OS environment
variable, and avoids relying on auth.json entries that Codex may later rotate
into ChatGPT tokens.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

from ..agents.codex_config import resolve_codex_connection_settings


PROXY_ENV_KEY = "CODEX_API_KEY"
OFFICIAL_ENV_KEY = "OPENAI_API_KEY"
AUTH_HELPER_DIR = "agenthub"
AUTH_HELPER_PS1 = "codex-auth-helper.ps1"
AUTH_HELPER_SH = "codex-auth-helper.sh"


class CodexLocalConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CodexLocalConfigStatus:
    codex_home: str
    config_exists: bool
    env_exists: bool
    connection: str
    provider_id: str
    provider_name: str
    base_url: str
    model: str
    wire_api: str
    auth_mode: str
    env_key: str
    api_key_set: bool
    api_key_source: str
    has_chatgpt_auth: bool
    needs_api_key: bool
    repair_applied: bool
    ready: bool
    message: str

    def to_api(self) -> dict:
        return {
            "codexHome": self.codex_home,
            "configExists": self.config_exists,
            "envExists": self.env_exists,
            "connection": self.connection,
            "providerId": self.provider_id,
            "providerName": self.provider_name,
            "baseUrl": self.base_url,
            "model": self.model,
            "wireApi": self.wire_api,
            "authMode": self.auth_mode,
            "envKey": self.env_key,
            "apiKeySet": self.api_key_set,
            "apiKeySource": self.api_key_source,
            "hasChatgptAuth": self.has_chatgpt_auth,
            "needsApiKey": self.needs_api_key,
            "repairApplied": self.repair_applied,
            "ready": self.ready,
            "message": self.message,
        }


class CodexLocalConfigService:
    def __init__(self, environ: Mapping[str, str] | None = None):
        self.environ = environ or os.environ

    @property
    def codex_home(self) -> Path:
        configured = self.environ.get("CODEX_HOME")
        if configured:
            return Path(configured).expanduser()
        return Path.home() / ".codex"

    def status(self) -> CodexLocalConfigStatus:
        home = self.codex_home
        settings = resolve_codex_connection_settings({}, environ=self.environ)
        repair_applied = self._repair_proxy_key_if_possible(settings)
        if repair_applied:
            settings = resolve_codex_connection_settings({}, environ=self.environ)
        env_key = _env_key_for_current_config(home, settings.provider_id)
        api_key_set = bool(settings.api_key)
        needs_api_key = settings.connection == "proxy" and not api_key_set
        ready = _is_ready(settings.connection, settings.auth_mode, api_key_set)
        return CodexLocalConfigStatus(
            codex_home=str(home),
            config_exists=(home / "config.toml").exists(),
            env_exists=(home / ".env").exists(),
            connection=settings.connection,
            provider_id=settings.provider_id,
            provider_name=settings.provider_name,
            base_url=settings.base_url,
            model=settings.model,
            wire_api=settings.wire_api,
            auth_mode=settings.auth_mode,
            env_key=env_key,
            api_key_set=api_key_set,
            api_key_source=settings.api_key_source,
            has_chatgpt_auth=settings.has_chatgpt_auth,
            needs_api_key=needs_api_key,
            repair_applied=repair_applied,
            ready=ready,
            message=_status_message(
                settings.connection,
                settings.auth_mode,
                api_key_set,
                repair_applied=repair_applied,
                has_chatgpt_auth=settings.has_chatgpt_auth,
            ),
        )

    def configure(
        self,
        *,
        connection: str,
        base_url: str,
        model: str = "",
        api_key: str = "",
        provider_id: str = "",
        provider_name: str = "",
        use_chatgpt_auth: bool = False,
    ) -> CodexLocalConfigStatus:
        connection = connection.strip().lower()
        if connection not in {"official", "proxy"}:
            raise CodexLocalConfigError("Codex connection must be official or proxy")

        home = self.codex_home
        home.mkdir(parents=True, exist_ok=True)

        if connection == "proxy":
            provider_id = _safe_provider_id(provider_id or "agenthub_proxy")
            provider_name = provider_name.strip() or "AgentHub Codex Proxy"
            base_url = _normalize_base_url(base_url, append_v1=True)
            env_key = PROXY_ENV_KEY
            if api_key.strip():
                _set_dotenv_value(home / ".env", env_key, api_key.strip())
            elif not _lookup_secret(env_key, home, self.environ):
                raise CodexLocalConfigError("中转模式需要填写 API Key")
            provider_fields = {
                "name": provider_name,
                "base_url": base_url,
                "wire_api": "responses",
            }
            auth_fields = _auth_helper_fields(home, env_key)
        else:
            provider_id = _safe_provider_id(provider_id or "openai")
            provider_name = provider_name.strip() or "OpenAI"
            base_url = _normalize_base_url(base_url or "https://api.openai.com/v1", append_v1=True)
            env_key = OFFICIAL_ENV_KEY
            auth_fields = None
            provider_fields = {
                "name": provider_name,
                "base_url": base_url,
                "wire_api": "responses",
            }
            if api_key.strip():
                _set_dotenv_value(home / ".env", env_key, api_key.strip())
                provider_fields["env_key"] = env_key
            elif use_chatgpt_auth:
                provider_fields["requires_openai_auth"] = True
            else:
                provider_fields["requires_openai_auth"] = True

        config_path = home / "config.toml"
        raw = _read_text(config_path)
        raw = _update_config_toml(
            raw,
            provider_id=provider_id,
            top_level={
                "model_provider": provider_id,
                **({"model": model.strip()} if model.strip() else {}),
            },
            provider_fields=provider_fields,
            auth_fields=auth_fields,
        )
        config_path.write_text(raw, encoding="utf-8")
        return self.status()

    def _repair_proxy_key_if_possible(self, settings) -> bool:
        if settings.connection != "proxy" or not settings.api_key:
            return False
        if _provider_has_auth_command(self.codex_home, settings.provider_id):
            return False
        env_key = _env_key_for_current_config(self.codex_home, settings.provider_id)
        if settings.api_key_source not in {"auth_json", "provider_inline", f"dotenv:{PROXY_ENV_KEY}"} and not env_key:
            return False
        home = self.codex_home
        _set_dotenv_value(home / ".env", PROXY_ENV_KEY, settings.api_key)
        config_path = home / "config.toml"
        raw = _read_text(config_path)
        if not raw:
            return False
        provider_id = settings.provider_id or _provider_id_from_config(raw)
        if not provider_id:
            return False
        raw = _update_config_toml(
            raw,
            provider_id=provider_id,
            top_level={"model_provider": provider_id},
            provider_fields={
                "name": settings.provider_name or "AgentHub Codex Proxy",
                "base_url": _normalize_base_url(settings.base_url, append_v1=True),
                "wire_api": settings.wire_api or "responses",
            },
            auth_fields=_auth_helper_fields(home, PROXY_ENV_KEY),
        )
        config_path.write_text(raw, encoding="utf-8")
        return True


def _is_ready(connection: str, auth_mode: str, api_key_set: bool) -> bool:
    if connection == "official":
        return api_key_set or auth_mode == "openai_auth"
    if connection == "proxy":
        return api_key_set and auth_mode in {"env_key", "inline_key", "command"}
    return False


def _status_message(
    connection: str,
    auth_mode: str,
    api_key_set: bool,
    *,
    repair_applied: bool,
    has_chatgpt_auth: bool,
) -> str:
    if repair_applied:
        return "已将 Codex 中转 API Key 迁移到本机 Codex .env，并改为命令式凭据读取配置。"
    if connection == "proxy" and not api_key_set:
        if has_chatgpt_auth:
            return "检测到 Codex 使用中转 URL，但当前只有 Codex 登录 token；请在 AgentHub 中填写中转 API Key。"
        return "检测到 Codex 使用中转 URL，但还没有可用的中转 API Key。"
    if connection == "proxy":
        return "Codex 中转配置可用。"
    if connection == "official" and (api_key_set or auth_mode == "openai_auth"):
        return "Codex 官方 OpenAI 配置可用。"
    return "尚未检测到可用的 Codex 连接配置。"


def _env_key_for_current_config(home: Path, provider_id: str) -> str:
    config = _read_text(home / "config.toml")
    if not provider_id:
        return ""
    pattern = re.compile(
        rf"^\s*\[model_providers\.{re.escape(provider_id)}]\s*$",
        re.MULTILINE,
    )
    match = pattern.search(config)
    if not match:
        return ""
    section = config[match.end():]
    next_section = re.search(r"^\s*\[", section, re.MULTILINE)
    if next_section:
        section = section[:next_section.start()]
    env_match = re.search(r'^\s*env_key\s*=\s*["\']([^"\']+)["\']\s*$', section, re.MULTILINE)
    return env_match.group(1) if env_match else ""


def _provider_has_auth_command(home: Path, provider_id: str) -> bool:
    config = _read_text(home / "config.toml")
    if not provider_id:
        return False
    pattern = re.compile(
        rf"^\s*\[model_providers\.{re.escape(provider_id)}\.auth]\s*$",
        re.MULTILINE,
    )
    match = pattern.search(config)
    if not match:
        return False
    section = config[match.end():]
    next_section = re.search(r"^\s*\[", section, re.MULTILINE)
    if next_section:
        section = section[:next_section.start()]
    return bool(re.search(r'^\s*command\s*=', section, re.MULTILINE))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _update_config_toml(
    raw: str,
    *,
    provider_id: str,
    top_level: dict[str, str],
    provider_fields: dict[str, object],
    auth_fields: dict[str, object] | None = None,
) -> str:
    lines = raw.splitlines()
    lines = _set_top_level_values(lines, top_level)
    lines = _set_provider_section(lines, provider_id, provider_fields)
    lines = _set_auth_section(lines, provider_id, auth_fields)
    return "\n".join(lines).rstrip() + "\n"


def _set_top_level_values(lines: list[str], values: dict[str, str]) -> list[str]:
    result = list(lines)
    first_section = next(
        (index for index, line in enumerate(result) if line.strip().startswith("[")),
        len(result),
    )
    for key, value in values.items():
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        for index in range(first_section):
            if pattern.match(result[index]):
                result[index] = f"{key} = {_toml_value(value)}"
                break
        else:
            result.insert(first_section, f"{key} = {_toml_value(value)}")
            first_section += 1
    return result


def _set_provider_section(
    lines: list[str],
    provider_id: str,
    fields: dict[str, object],
) -> list[str]:
    header = f"[model_providers.{provider_id}]"
    start = next((index for index, line in enumerate(lines) if line.strip() == header), -1)
    if start < 0:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(header)
        lines.extend(f"{key} = {_toml_value(value)}" for key, value in fields.items())
        return lines

    end = next(
        (
            index for index in range(start + 1, len(lines))
            if lines[index].strip().startswith("[")
        ),
        len(lines),
    )
    managed = {
        "name",
        "base_url",
        "wire_api",
        "env_key",
        "requires_openai_auth",
        "api_key",
        "apiKey",
        "token",
        "bearer_token",
    }
    section = lines[start + 1:end]
    next_section: list[str] = []
    remaining = dict(fields)
    for line in section:
        key = _toml_key(line)
        if key in managed:
            if key in fields:
                next_section.append(f"{key} = {_toml_value(fields[key])}")
                remaining.pop(key, None)
            continue
        next_section.append(line)
    for key, value in remaining.items():
        next_section.append(f"{key} = {_toml_value(value)}")
    return [*lines[:start + 1], *next_section, *lines[end:]]


def _set_auth_section(
    lines: list[str],
    provider_id: str,
    fields: dict[str, object] | None,
) -> list[str]:
    header = f"[model_providers.{provider_id}.auth]"
    start = next((index for index, line in enumerate(lines) if line.strip() == header), -1)
    if fields is None:
        if start < 0:
            return lines
        end = next(
            (
                index for index in range(start + 1, len(lines))
                if lines[index].strip().startswith("[")
            ),
            len(lines),
        )
        return [*lines[:start], *lines[end:]]

    rendered = [header, *(f"{key} = {_toml_value(value)}" for key, value in fields.items())]
    if start < 0:
        if lines and lines[-1].strip():
            lines.append("")
        return [*lines, *rendered]

    end = next(
        (
            index for index in range(start + 1, len(lines))
            if lines[index].strip().startswith("[")
        ),
        len(lines),
    )
    return [*lines[:start], *rendered, *lines[end:]]


def _toml_key(line: str) -> str:
    match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
    return match.group(1) if match else ""


def _provider_id_from_config(raw: str) -> str:
    match = re.search(r'^\s*model_provider\s*=\s*["\']([^"\']+)["\']\s*$', raw, re.MULTILINE)
    return match.group(1) if match else ""


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return json.dumps([str(item) for item in value], ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


def _safe_provider_id(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    clean = clean.strip("_-")
    return clean or "agenthub_proxy"


def _normalize_base_url(value: str, *, append_v1: bool) -> str:
    clean = value.strip().rstrip("/")
    parsed = urlsplit(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CodexLocalConfigError("Base URL 必须是完整的 http(s) URL")
    if not append_v1 or parsed.path.rstrip("/").endswith("/v1"):
        return clean
    path = f"{parsed.path.rstrip('/')}/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def _auth_helper_fields(home: Path, env_key: str) -> dict[str, object]:
    helper = _ensure_auth_helper(home)
    if os.name == "nt":
        return {
            "command": "powershell.exe",
            "args": [
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(helper),
                env_key,
            ],
            "timeout_ms": 5000,
            "refresh_interval_ms": 300000,
        }
    return {
        "command": "sh",
        "args": [str(helper), env_key],
        "timeout_ms": 5000,
        "refresh_interval_ms": 300000,
    }


def _ensure_auth_helper(home: Path) -> Path:
    helper_dir = home / AUTH_HELPER_DIR
    helper_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = helper_dir / AUTH_HELPER_PS1
        content = _powershell_auth_helper()
    else:
        path = helper_dir / AUTH_HELPER_SH
        content = _sh_auth_helper()
    path.write_text(content, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o700)
    return path


def _powershell_auth_helper() -> str:
    return """param([string]$Name = "CODEX_API_KEY")
$ErrorActionPreference = "Stop"
$envPath = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
if (-not (Test-Path -LiteralPath $envPath)) { exit 1 }
foreach ($line in Get-Content -LiteralPath $envPath) {
    $clean = $line.Trim()
    if (-not $clean -or $clean.StartsWith("#")) { continue }
    if ($clean.StartsWith("export ")) {
        $clean = $clean.Substring(7).Trim()
    }
    $index = $clean.IndexOf("=")
    if ($index -lt 1) { continue }
    $key = $clean.Substring(0, $index).Trim()
    if ($key -ne $Name) { continue }
    $value = $clean.Substring($index + 1).Trim()
    if ($value.Length -ge 2) {
        $first = $value[0]
        $last = $value[$value.Length - 1]
        if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }
    [Console]::Out.Write($value)
    exit 0
}
exit 1
"""


def _sh_auth_helper() -> str:
    return """#!/bin/sh
name="${1:-CODEX_API_KEY}"
env_path="$(dirname "$(dirname "$0")")/.env"
[ -f "$env_path" ] || exit 1
while IFS= read -r line; do
  clean="$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [ -n "$clean" ] || continue
  case "$clean" in \\#*) continue ;; esac
  case "$clean" in export\\ *) clean="$(printf '%s' "$clean" | sed 's/^export[[:space:]]*//')" ;; esac
  key="${clean%%=*}"
  [ "$key" = "$name" ] || continue
  value="${clean#*=}"
  value="$(printf '%s' "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  case "$value" in
    \\"*\\") value="${value#\\"}"; value="${value%\\"}" ;;
    \\'*\\') value="${value#\\'}"; value="${value%\\'}" ;;
  esac
  printf '%s' "$value"
  exit 0
done < "$env_path"
exit 1
"""


def _set_dotenv_value(path: Path, key: str, value: str) -> None:
    lines = _read_text(path).splitlines()
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=")
    rendered = f"{key}={_dotenv_value(value)}"
    for index, line in enumerate(lines):
        if pattern.match(line):
            lines[index] = rendered
            break
    else:
        lines.append(rendered)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _dotenv_value(value: str) -> str:
    if re.search(r"\s|#|['\"]", value):
        return json.dumps(value, ensure_ascii=False)
    return value


def _lookup_secret(name: str, codex_home: Path, environ: Mapping[str, str]) -> str:
    value = environ.get(name, "").strip()
    if value:
        return value
    for line in _read_text(codex_home / ".env").splitlines():
        clean = line.strip()
        if clean.startswith("export "):
            clean = clean[len("export "):].strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, raw = clean.split("=", 1)
        if key.strip() == name:
            return _unquote(raw.strip())
    return ""


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
