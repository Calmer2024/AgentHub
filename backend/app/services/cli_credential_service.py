"""SaaS 云端 CLI 凭据配置、门禁与 Runtime 注入。"""

from __future__ import annotations

import json
import re
import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..models import AgentConfig, CliCredentialConfig, Project, User
from .audit_service import AuditService
from .cli_credential_schemas import (
    CliCredentialConfigRead,
    CliCredentialListRead,
    CliModelListRead,
    CliModelOptionRead,
    CliCredentialUpsert,
    CliTool,
)
from .phase10_schemas import SecretCreate
from .secret_service import SecretService
from .team_service import PermissionDeniedError, TeamService


NATIVE_CLI_TOOLS: set[str] = {"claude_code", "codex", "opencode"}
ENV_KEY_PATTERN = re.compile(r"[^A-Za-z0-9_]+")
ANSI_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
PLAIN_SGR_TOKEN_PATTERN = re.compile(r"\[[0-9;]+m\]")
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
MODELS_DEV_URL = "https://models.dev/api.json"
MODELS_DEV_PROVIDER_ALIASES = {
    "dashscope": "alibaba-cn",
    "qwen": "alibaba-cn",
    "tongyi": "alibaba-cn",
    "aliyun": "alibaba-cn",
}

OPENCODE_MODEL_FALLBACKS: dict[str, list[str]] = {
    "openai": ["gpt-5.5", "gpt-5.5-pro", "gpt-5.4", "gpt-5.1-codex", "gpt-4.1"],
    "deepseek": ["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"],
    "openrouter": ["openai/gpt-5.5", "openai/gpt-5.1-codex", "deepseek/deepseek-v4-pro", "anthropic/claude-sonnet-4.5"],
    "alibaba-cn": ["qwen-plus", "qwen-max", "qwen3-coder-plus", "qwen3-max"],
}


@dataclass(frozen=True)
class CliCredentialDefaults:
    provider_type: str
    provider_id: str
    provider_name: str
    base_url: str | None
    model: str | None
    auth_env_key: str


DEFAULTS: dict[str, CliCredentialDefaults] = {
    "claude_code": CliCredentialDefaults(
        provider_type="official",
        provider_id="anthropic",
        provider_name="Anthropic",
        base_url=None,
        model=None,
        auth_env_key="ANTHROPIC_API_KEY",
    ),
    "codex": CliCredentialDefaults(
        provider_type="official",
        provider_id="OpenAI",
        provider_name="OpenAI",
        base_url="https://api.openai.com/v1",
        model=None,
        auth_env_key="OPENAI_API_KEY",
    ),
    "opencode": CliCredentialDefaults(
        provider_type="official",
        provider_id="openai",
        provider_name="OpenAI",
        base_url="https://api.openai.com/v1",
        model=None,
        auth_env_key="OPENAI_API_KEY",
    ),
}

TOOL_LABELS = {
    "claude_code": "Claude Code",
    "codex": "Codex",
    "opencode": "OpenCode",
}


class CliCredentialError(ValueError):
    pass


class CliCredentialRequiredError(CliCredentialError):
    pass


class CliCredentialService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.secrets = SecretService(db)
        self.teams = TeamService(db)
        self.audit = AuditService(db)

    async def list_for_user(self, actor: User) -> CliCredentialListRead:
        items = []
        for cli_tool in ("claude_code", "codex", "opencode"):
            config = await self._find_config(scope="user", owner_id=actor.id, cli_tool=cli_tool)
            items.append(await self._read_for_tool(
                cli_tool,
                config,
                scope="user",
                owner_id=actor.id,
            ))
        return CliCredentialListRead(items=items)

    async def save(
        self,
        cli_tool: CliTool,
        data: CliCredentialUpsert,
        actor: User,
    ) -> CliCredentialConfigRead:
        if cli_tool not in NATIVE_CLI_TOOLS:
            raise CliCredentialError("unsupported CLI tool")
        scope, owner_id = await self._resolve_owner(data, actor)
        defaults = DEFAULTS[cli_tool]
        auth_env_key = _normalize_env_key(data.auth_env_key or defaults.auth_env_key)
        api_key = _normalize_api_key(data.api_key)
        model = _clean_model_name(data.model)
        secret_names: list[str] = []
        if api_key:
            await self.secrets.create_secret(SecretCreate(
                name=auth_env_key,
                value=api_key,
                scope=scope,
                owner_id=owner_id if scope != "user" else None,
            ), actor)
            secret_names = [auth_env_key]

        config = await self._find_config(scope=scope, owner_id=owner_id, cli_tool=cli_tool)
        now = china_now()
        if config and not secret_names:
            secret_names = _json_list(config.secret_names_json)
        if not secret_names:
            secret_names = [auth_env_key]

        provider_type = data.provider_type or defaults.provider_type
        provider_id = _provider_id(data.provider_id or defaults.provider_id)
        provider_name = data.provider_name or defaults.provider_name
        config_json = json.dumps(_credential_config(data.config, cli_tool), ensure_ascii=False)
        if config:
            config.provider_type = provider_type
            config.provider_id = provider_id
            config.provider_name = provider_name
            config.base_url = data.base_url if data.base_url is not None else defaults.base_url
            config.model = model
            config.auth_env_key = auth_env_key
            config.secret_names_json = json.dumps(secret_names, ensure_ascii=False)
            config.config_json = config_json
            config.updated_at = now
        else:
            config = CliCredentialConfig(
                id=str(uuid.uuid4()),
                scope=scope,
                owner_id=owner_id,
                cli_tool=cli_tool,
                provider_type=provider_type,
                provider_id=provider_id,
                provider_name=provider_name,
                base_url=data.base_url if data.base_url is not None else defaults.base_url,
                model=model,
                auth_env_key=auth_env_key,
                secret_names_json=json.dumps(secret_names, ensure_ascii=False),
                config_json=config_json,
                created_at=now,
                updated_at=now,
            )
            self.db.add(config)
        await self.audit.record(
            actor_user_id=actor.id,
            action="cli_credential.saved",
            resource_type="cli_credential",
            resource_id=config.id,
            metadata={
                "cliTool": cli_tool,
                "scope": scope,
                "providerType": provider_type,
                "providerId": provider_id,
                "hasApiKey": bool(api_key),
            },
        )
        await self.db.commit()
        await self.db.refresh(config)
        return await self._read_config(config)

    async def list_models(self, cli_tool: CliTool, provider_id: str) -> CliModelListRead:
        if cli_tool != "opencode":
            return CliModelListRead(
                cli_tool=cli_tool,
                provider_id=provider_id,
                source="unsupported",
                items=[],
            )
        normalized_provider = _model_provider_id(provider_id)
        try:
            items = await asyncio.to_thread(_models_dev_options, normalized_provider)
            source = "models.dev"
        except Exception:
            items = _fallback_model_options(normalized_provider)
            source = "fallback"
        if not items:
            items = _fallback_model_options(normalized_provider)
            source = "fallback"
        return CliModelListRead(
            cli_tool=cli_tool,
            provider_id=normalized_provider,
            source=source,
            items=items[:80],
        )

    async def read_effective_for_project(
        self,
        cli_tool: str,
        *,
        actor: User,
        project: Project,
    ) -> CliCredentialConfigRead:
        if cli_tool not in NATIVE_CLI_TOOLS:
            raise CliCredentialError("unsupported CLI tool")
        config = await self._effective_config(cli_tool, actor=actor, project=project)
        return await self._read_for_tool(
            cli_tool,
            config,
            scope=config.scope if config else "user",
            owner_id=config.owner_id if config else actor.id,
        )

    async def assert_ready_for_agent(self, agent: AgentConfig, *, actor: User, project: Project) -> None:
        cli_tool = str(agent.cli_tool or "")
        if cli_tool not in NATIVE_CLI_TOOLS:
            return
        config = await self._effective_config(cli_tool, actor=actor, project=project)
        env = await self.secrets.env_for_project(actor=actor, project=project)
        self._assert_configured(cli_tool, config, env)

    async def prepare_env_for_agent(
        self,
        agent: AgentConfig,
        *,
        actor: User,
        project: Project,
        workspace_path: str,
        env_vars: dict[str, str],
    ) -> dict[str, str]:
        cli_tool = str(agent.cli_tool or "")
        if cli_tool not in NATIVE_CLI_TOOLS:
            return env_vars
        config = await self._effective_config(cli_tool, actor=actor, project=project)
        self._assert_configured(cli_tool, config, env_vars)
        prepared = dict(env_vars)
        if cli_tool == "claude_code":
            return self._prepare_claude(config, prepared)
        if cli_tool == "codex":
            return self._prepare_codex(config, prepared, workspace_path=workspace_path)
        if cli_tool == "opencode":
            return self._prepare_opencode(config, prepared, workspace_path=workspace_path)
        return prepared

    async def _resolve_owner(self, data: CliCredentialUpsert, actor: User) -> tuple[str, str]:
        if data.scope == "user":
            return "user", actor.id
        owner_id = (data.owner_id or "").strip()
        if not owner_id:
            raise CliCredentialError("ownerId is required for team/project credential")
        if data.scope == "team":
            await self.teams.assert_team_admin(owner_id, actor.id)
            return "team", owner_id
        if data.scope == "project":
            project = await self.db.get(Project, owner_id)
            if not project:
                raise CliCredentialError("project not found")
            await self.teams.assert_workspace_write_allowed(project, actor)
            return "project", owner_id
        raise CliCredentialError("invalid credential scope")

    async def _effective_config(
        self,
        cli_tool: str,
        *,
        actor: User,
        project: Project,
    ) -> CliCredentialConfig | None:
        candidates: list[tuple[str, str]] = [("project", project.id)]
        if project.team_id:
            try:
                await self.teams.role_for_user(project.team_id, actor.id)
                candidates.append(("team", project.team_id))
            except PermissionDeniedError:
                pass
        candidates.append(("user", actor.id))
        for scope, owner_id in candidates:
            config = await self._find_config(scope=scope, owner_id=owner_id, cli_tool=cli_tool)
            if config:
                return config
        return None

    async def _find_config(
        self,
        *,
        scope: str,
        owner_id: str,
        cli_tool: str,
    ) -> CliCredentialConfig | None:
        result = await self.db.execute(
            select(CliCredentialConfig).where(
                CliCredentialConfig.scope == scope,
                CliCredentialConfig.owner_id == owner_id,
                CliCredentialConfig.cli_tool == cli_tool,
            )
        )
        return result.scalars().first()

    async def _read_for_tool(
        self,
        cli_tool: str,
        config: CliCredentialConfig | None,
        *,
        scope: str,
        owner_id: str,
    ) -> CliCredentialConfigRead:
        if config:
            return await self._read_config(config)
        defaults = DEFAULTS[cli_tool]
        return CliCredentialConfigRead(
            cli_tool=cli_tool,  # type: ignore[arg-type]
            scope=scope,
            owner_id=owner_id,
            provider_type=defaults.provider_type,
            provider_id=defaults.provider_id,
            provider_name=defaults.provider_name,
            base_url=defaults.base_url,
            model=defaults.model,
            auth_env_key=defaults.auth_env_key,
            configured=False,
            secret_names=[defaults.auth_env_key],
            config={},
            updated_at=None,
        )

    async def _read_config(self, config: CliCredentialConfig) -> CliCredentialConfigRead:
        secret_names = _json_list(config.secret_names_json)
        configured = await self._secrets_exist(config.scope, config.owner_id, secret_names)
        return CliCredentialConfigRead(
            cli_tool=config.cli_tool,  # type: ignore[arg-type]
            scope=config.scope,
            owner_id=config.owner_id,
            provider_type=config.provider_type,
            provider_id=config.provider_id,
            provider_name=config.provider_name,
            base_url=config.base_url,
            model=config.model,
            auth_env_key=config.auth_env_key,
            configured=configured,
            secret_names=secret_names,
            config=_config_dict(config.config_json),
            updated_at=config.updated_at,
        )

    async def _secrets_exist(self, scope: str, owner_id: str, names: list[str]) -> bool:
        if not names:
            return False
        from ..models import Secret

        result = await self.db.execute(
            select(Secret.name).where(
                Secret.scope == scope,
                Secret.owner_id == owner_id,
                Secret.name.in_(names),
            )
        )
        found = {str(item) for item in result.scalars().all()}
        return all(name in found for name in names)

    def _assert_configured(
        self,
        cli_tool: str,
        config: CliCredentialConfig | None,
        env_vars: dict[str, str],
    ) -> None:
        label = TOOL_LABELS.get(cli_tool, cli_tool)
        if not config:
            raise CliCredentialRequiredError(f"请先配置 {label} API Key")
        missing = [name for name in _json_list(config.secret_names_json) if not env_vars.get(name)]
        if missing:
            raise CliCredentialRequiredError(f"请先配置 {label} API Key")

    def _prepare_claude(self, config: CliCredentialConfig, env_vars: dict[str, str]) -> dict[str, str]:
        if config.base_url:
            env_vars["ANTHROPIC_BASE_URL"] = config.base_url
        if config.model:
            env_vars["ANTHROPIC_MODEL"] = config.model
        env_vars["AGENTHUB_CLI_PROVIDER_TYPE"] = config.provider_type
        return env_vars

    def _prepare_codex(
        self,
        config: CliCredentialConfig,
        env_vars: dict[str, str],
        *,
        workspace_path: str,
    ) -> dict[str, str]:
        config_dir = Path(workspace_path) / ".agenthub" / "runtime-config" / "codex"
        config_dir.mkdir(parents=True, exist_ok=True)
        provider_id = _provider_id(config.provider_id)
        extra = _config_dict(config.config_json)
        review_model = _clean_model_name(str(extra.get("reviewModel") or extra.get("review_model") or "")) or config.model
        reasoning_effort = _clean_codex_reasoning_effort(extra.get("modelReasoningEffort") or extra.get("model_reasoning_effort"))
        wire_api = _clean_codex_wire_api(extra.get("wireApi") or extra.get("wire_api"))
        network_access = _clean_codex_network_access(extra.get("networkAccess") or extra.get("network_access"))
        disable_response_storage = _config_bool(
            _first_config_value(extra, "disableResponseStorage", "disable_response_storage"),
            True,
        )
        requires_openai_auth = _config_bool(
            _first_config_value(extra, "requiresOpenaiAuth", "requires_openai_auth"),
            False,
        )
        lines = []
        if config.model:
            lines.append(f'model = "{_toml(config.model)}"')
        if review_model:
            lines.append(f'review_model = "{_toml(review_model)}"')
        lines.append(f'model_provider = "{_toml(provider_id)}"')
        lines.append(f'model_reasoning_effort = "{_toml(reasoning_effort)}"')
        lines.append(f"disable_response_storage = {_toml_bool(disable_response_storage)}")
        lines.append(f'network_access = "{_toml(network_access)}"')
        lines.append("windows_wsl_setup_acknowledged = true")
        lines.append("")
        lines.append(f"[model_providers.{provider_id}]")
        lines.append(f'name = "{_toml(config.provider_name)}"')
        if config.base_url:
            lines.append(f'base_url = "{_toml(config.base_url)}"')
        lines.append(f'env_key = "{_toml(config.auth_env_key)}"')
        lines.append(f'wire_api = "{_toml(wire_api)}"')
        if requires_openai_auth:
            lines.append("requires_openai_auth = true")
        lines.append("")
        lines.append("[features]")
        lines.append("goals = true")
        (config_dir / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        env_vars["CODEX_HOME"] = "/workspace/.agenthub/runtime-config/codex"
        env_vars["AGENTHUB_CLI_PROVIDER_TYPE"] = config.provider_type
        return env_vars

    def _prepare_opencode(
        self,
        config: CliCredentialConfig,
        env_vars: dict[str, str],
        *,
        workspace_path: str,
    ) -> dict[str, str]:
        config_dir = Path(workspace_path) / ".agenthub" / "runtime-config" / "opencode"
        config_dir.mkdir(parents=True, exist_ok=True)
        provider_id = _provider_id(config.provider_id)
        model = config.model or "default"
        provider: dict[str, Any] = {
            "npm": "@ai-sdk/openai-compatible",
            "name": config.provider_name,
            "options": {
                "apiKey": f"{{env:{config.auth_env_key}}}",
            },
            "models": {
                model: {
                    "name": model,
                },
            },
        }
        if config.base_url:
            provider["options"]["baseURL"] = config.base_url
        payload = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                provider_id: provider,
            },
            "model": f"{provider_id}/{model}",
        }
        file_text = json.dumps(payload, ensure_ascii=False, indent=2)
        config_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        (config_dir / "opencode.json").write_text(file_text, encoding="utf-8")
        env_vars["OPENCODE_CONFIG"] = "/workspace/.agenthub/runtime-config/opencode/opencode.json"
        env_vars["OPENCODE_CONFIG_CONTENT"] = config_text
        env_vars["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
        env_vars["CI"] = "1"
        env_vars["AGENTHUB_CLI_PROVIDER_TYPE"] = config.provider_type
        return env_vars


def _normalize_env_key(value: str) -> str:
    clean = ENV_KEY_PATTERN.sub("_", value.strip()).strip("_").upper()
    if not clean:
        raise CliCredentialError("authEnvKey is required")
    if clean[0].isdigit():
        clean = f"SECRET_{clean}"
    return clean


def _normalize_api_key(value: str | None) -> str | None:
    clean = (value or "").strip()
    if not clean:
        return None
    if URL_PATTERN.match(clean):
        raise CliCredentialError("API Key 不能填写 URL，请填写供应商控制台生成的密钥")
    return clean


def _clean_model_name(value: str | None) -> str | None:
    clean = ANSI_SGR_PATTERN.sub("", (value or "").strip())
    clean = PLAIN_SGR_TOKEN_PATTERN.sub("", clean).strip()
    return clean or None


def _provider_id(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    return clean or "agenthub"


def _credential_config(value: dict[str, Any], cli_tool: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if cli_tool == "codex":
        result: dict[str, Any] = {
            "wireApi": _clean_codex_wire_api(value.get("wireApi") or value.get("wire_api")),
            "modelReasoningEffort": _clean_codex_reasoning_effort(
                value.get("modelReasoningEffort") or value.get("model_reasoning_effort"),
            ),
            "networkAccess": _clean_codex_network_access(value.get("networkAccess") or value.get("network_access")),
            "disableResponseStorage": _config_bool(
                _first_config_value(value, "disableResponseStorage", "disable_response_storage"),
                True,
            ),
            "requiresOpenaiAuth": _config_bool(
                _first_config_value(value, "requiresOpenaiAuth", "requires_openai_auth"),
                False,
            ),
        }
        review_model = _clean_model_name(str(value.get("reviewModel") or value.get("review_model") or ""))
        if review_model:
            result["reviewModel"] = review_model
        return result
    return {}


def _config_dict(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _config_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        clean = value.strip().lower()
        if clean in {"true", "1", "yes", "on"}:
            return True
        if clean in {"false", "0", "no", "off"}:
            return False
    return default


def _first_config_value(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value:
            return value[key]
    return None


def _clean_codex_wire_api(value: Any) -> str:
    clean = str(value or "").strip().lower()
    return "responses" if clean != "responses" else clean


def _clean_codex_reasoning_effort(value: Any) -> str:
    clean = str(value or "").strip().lower()
    return clean if clean in {"minimal", "low", "medium", "high", "xhigh"} else "xhigh"


def _clean_codex_network_access(value: Any) -> str:
    clean = str(value or "").strip().lower()
    return clean if clean in {"enabled", "disabled"} else "enabled"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _model_provider_id(value: str) -> str:
    clean = (value or "").strip().lower()
    return MODELS_DEV_PROVIDER_ALIASES.get(clean, clean or "openai")


def _models_dev_options(provider_id: str) -> list[CliModelOptionRead]:
    request = Request(MODELS_DEV_URL, headers={"User-Agent": "AgentHub/0.1"})
    with urlopen(request, timeout=8) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        return []
    provider = data.get(provider_id)
    if not isinstance(provider, dict):
        for item in data.values():
            if not isinstance(item, dict):
                continue
            if _model_provider_id(str(item.get("id") or "")) == provider_id:
                provider = item
                break
    if not isinstance(provider, dict):
        return []
    models = provider.get("models")
    if not isinstance(models, dict):
        return []
    rows: list[tuple[tuple[int, str, str], CliModelOptionRead]] = []
    for model_id, payload in models.items():
        if not isinstance(payload, dict):
            continue
        status = str(payload.get("status") or "").lower()
        last_updated = str(payload.get("last_updated") or payload.get("release_date") or "")
        limit = payload.get("limit") if isinstance(payload.get("limit"), dict) else {}
        name = str(payload.get("name") or model_id)
        model = CliModelOptionRead(
            id=str(payload.get("id") or model_id),
            name=name,
            label=name if name == str(model_id) else f"{name} ({model_id})",
            provider_id=provider_id,
            reasoning=bool(payload.get("reasoning")),
            tool_call=bool(payload.get("tool_call")),
            context=_int_or_none(limit.get("context")),
            output=_int_or_none(limit.get("output")),
            last_updated=last_updated or None,
        )
        rows.append(((1 if status == "deprecated" else 0, _reverse_date_key(last_updated), str(model.id)), model))
    rows.sort(key=lambda item: item[0])
    return [item for _sort, item in rows]


def _fallback_model_options(provider_id: str) -> list[CliModelOptionRead]:
    models = OPENCODE_MODEL_FALLBACKS.get(provider_id) or OPENCODE_MODEL_FALLBACKS.get("openai", [])
    return [
        CliModelOptionRead(
            id=model,
            name=model,
            label=model,
            provider_id=provider_id,
            reasoning=False,
            tool_call=True,
            context=None,
            output=None,
            last_updated=None,
        )
        for model in models
    ]


def _reverse_date_key(value: str) -> str:
    clean = value.strip()
    if not clean:
        return "9999-99-99"
    parts = [int(part) if part.isdigit() else 0 for part in clean.split("-")[:3]]
    while len(parts) < 3:
        parts.append(0)
    return f"{9999 - parts[0]:04d}-{99 - parts[1]:02d}-{99 - parts[2]:02d}"


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
