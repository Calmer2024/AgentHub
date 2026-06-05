"""Catalog service for AgentHub CLI friends.

User-visible Agents are local CLI tools. This module owns their persisted
configuration and executable health checks so API handlers stay thin.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.cli_defaults import DEFAULT_CLI_AGENTS
from ..agents.cli_runtime import resolve_cli_command
from ..core.agent_env import (
    allowed_sensitive_env_keys_for_cli,
    clean_cli_agent_env,
    encode_cli_agent_env,
)
from ..models import AgentConfig


DEFAULT_PRIMARY_SKILL = "general_coding"
DEFAULT_CONTEXT_POLICY = "workspace_coding"


class CliAgentNotFoundError(LookupError):
    pass


class InvalidCliAgentError(ValueError):
    pass


@dataclass(frozen=True)
class ExecutableStatus:
    status: str
    version: str | None = None
    executable_path: str | None = None

    @property
    def found(self) -> bool:
        return self.status == "ready"

    def to_api(self) -> dict:
        return {
            "found": self.found,
            "status": self.status,
            "version": self.version,
            "path": self.executable_path,
        }


class CliAgentRegistry:
    """Persistence and health checks for CLI wrapper Agents."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_active(self) -> list[AgentConfig]:
        result = await self.db.execute(
            select(AgentConfig)
            .where(AgentConfig.is_active == True)
            .order_by(AgentConfig.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, agent_id: str) -> AgentConfig:
        agent = await self.db.get(AgentConfig, agent_id)
        if not agent:
            raise CliAgentNotFoundError(agent_id)
        return agent

    async def create(self, data) -> AgentConfig:
        if data.agent_type != "cli_wrapper":
            raise InvalidCliAgentError("Agent 必须使用 cli_wrapper 类型")

        defaults = DEFAULT_CLI_AGENTS.get(data.cli_tool, {})
        agent = AgentConfig(
            id=str(uuid.uuid4()),
            name=data.name,
            description=data.description or "",
            system_prompt=data.system_prompt or "",
            agent_type="cli_wrapper",
            cli_tool=data.cli_tool or "custom",
            executable=data.executable or defaults.get("executable"),
            init_args=encode_json(data.init_args or defaults.get("init_args", [])),
            env_vars=encode_cli_agent_env(
                data.env_vars or defaults.get("env_vars", {}),
                allowed_sensitive_keys=allowed_sensitive_env_keys_for_cli(data.cli_tool),
            ),
            primary_skill=_normalize_skill_id(data.primary_skill) or DEFAULT_PRIMARY_SKILL,
            auxiliary_skills=encode_json(_normalize_skill_list(data.auxiliary_skills)),
            context_policy=_normalize_context_policy(data.context_policy),
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def update(self, agent_id: str, data) -> AgentConfig:
        agent = await self.get(agent_id)
        if data.agent_type is not None and data.agent_type != "cli_wrapper":
            raise InvalidCliAgentError("Agent 必须使用 cli_wrapper 类型")

        scalar_fields = (
            "name",
            "description",
            "system_prompt",
            "cli_tool",
            "executable",
            "is_active",
        )
        for field in scalar_fields:
            value = getattr(data, field)
            if value is not None:
                setattr(agent, field, value)
        agent.agent_type = "cli_wrapper"

        if data.init_args is not None:
            agent.init_args = encode_json(data.init_args)
        if data.env_vars is not None:
            agent.env_vars = encode_cli_agent_env(
                data.env_vars,
                allowed_sensitive_keys=allowed_sensitive_env_keys_for_cli(agent.cli_tool),
            )
        if data.primary_skill is not None:
            agent.primary_skill = _normalize_skill_id(data.primary_skill) or DEFAULT_PRIMARY_SKILL
        if data.auxiliary_skills is not None:
            agent.auxiliary_skills = encode_json(_normalize_skill_list(data.auxiliary_skills))
        if data.context_policy is not None:
            agent.context_policy = _normalize_context_policy(data.context_policy)

        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def soft_delete(self, agent_id: str) -> None:
        agent = await self.get(agent_id)
        agent.is_active = False
        await self.db.commit()

    @staticmethod
    def executable_status(executable: str | None) -> ExecutableStatus:
        if not executable:
            return ExecutableStatus("not_found")

        resolved = shutil.which(executable)
        if not resolved and any(sep in executable for sep in ("/", "\\")):
            resolved = executable if shutil.which(executable) else None
        if not resolved:
            return ExecutableStatus("not_found")

        return ExecutableStatus(
            status="ready",
            version=_detect_version(resolved),
            executable_path=resolved,
        )


def encode_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def decode_json_list(value: str | None) -> list[str]:
    data = _decode_json(value, [])
    return [str(item) for item in data] if isinstance(data, list) else []


def decode_json_dict(
    value: str | None,
    *,
    cli_tool: str | None = None,
) -> dict[str, str]:
    data = _decode_json(value, {})
    if not isinstance(data, dict):
        return {}
    return clean_cli_agent_env(
        {str(k): str(v) for k, v in data.items()},
        allowed_sensitive_keys=allowed_sensitive_env_keys_for_cli(cli_tool),
    )


def _normalize_skill_id(value: str | None) -> str:
    return str(value or "").strip()


def _normalize_skill_list(value: list[str] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in value or []:
        skill_id = _normalize_skill_id(item)
        if not skill_id or skill_id in seen:
            continue
        seen.add(skill_id)
        result.append(skill_id)
    return result


def _normalize_context_policy(value: str | None) -> str:
    return str(value or DEFAULT_CONTEXT_POLICY).strip() or DEFAULT_CONTEXT_POLICY


def _decode_json(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _detect_version(executable: str) -> str | None:
    for arg in ("--version", "-v"):
        try:
            result = subprocess.run(
                resolve_cli_command(executable, [arg]),
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except Exception:
            continue
        output = (result.stdout or result.stderr or "").strip()
        if output:
            return output.splitlines()[0][:80]
    return None
