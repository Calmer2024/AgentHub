"""Phase 7C 统一环境体检聚合。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.cli_runtime_registry import cli_runtime_registry
from ..core.timezone import china_now_iso
from ..models import AgentConfig, Project, Session as DBSession, SessionMember, User
from .cli_agent_registry import CliAgentRegistry
from .cli_credential_service import NATIVE_CLI_TOOLS, TOOL_LABELS, CliCredentialService
from .codex_local_config_service import CodexLocalConfigService
from .runner_provider import list_runtime_images
from .system_llm import system_model_status


HealthStatus = Literal["ok", "warning", "error", "missing"]
HealthSeverity = Literal["info", "warning", "blocking"]


class SystemHealthAction(BaseModel):
    label: str
    target: Literal["agent_panel", "project_settings", "docs", "retry"]


class SystemHealthItem(BaseModel):
    key: str
    label: str
    status: HealthStatus
    severity: HealthSeverity
    detail: str
    action: SystemHealthAction | None = None
    metadata: dict[str, str | int | bool | None] | None = None


class SystemHealthRead(BaseModel):
    overall: Literal["ok", "warning", "error"]
    checked_at: str = Field(alias="checkedAt")
    project_id: str | None = Field(default=None, alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    items: list[SystemHealthItem]

    model_config = {"populate_by_name": True}


class SystemHealthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check(
        self,
        *,
        project_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        actor: User | None = None,
    ) -> SystemHealthRead:
        session = await self.db.get(DBSession, session_id) if session_id else None
        effective_project_id = project_id or (session.project_id if session else None)
        project = await self.db.get(Project, effective_project_id) if effective_project_id else None
        cloud_mode = bool(project and project.workspace_mode == "cloud")
        effective_agent_ids = await self._effective_agent_ids(session, agent_id)

        items: list[SystemHealthItem] = []
        items.extend(await self._agent_items(effective_agent_ids, cloud_mode=cloud_mode))
        if cloud_mode:
            items.extend(await self._cloud_cli_credential_items(effective_agent_ids, actor=actor, project=project))
            items.append(self._cloud_runtime_image_item())
        else:
            items.append(self._codex_item())
            items.append(self._runtime_item("node", "node", warning_if_missing=True))
        items.append(self._python_item())
        items.append(await self._workspace_item(effective_project_id))
        items.append(self._system_model_item(warning_if_unconfigured=not cloud_mode))
        items.append(self._process_item(session_id))

        blocking = [item.detail for item in items if item.severity == "blocking"]
        overall: Literal["ok", "warning", "error"] = "ok"
        if blocking:
            overall = "error"
        elif any(item.status in {"warning", "missing"} or item.severity == "warning" for item in items):
            overall = "warning"

        return SystemHealthRead(
            overall=overall,
            checked_at=_utc_iso(),
            project_id=effective_project_id,
            session_id=session_id,
            blocking_reasons=blocking,
            items=items,
        )

    async def _effective_agent_ids(
        self,
        session: DBSession | None,
        explicit_agent_id: str | None,
    ) -> list[str]:
        if explicit_agent_id:
            return [explicit_agent_id]
        if not session:
            return []
        if session.mode == "group":
            result = await self.db.execute(
                select(SessionMember.agent_config_id).where(SessionMember.session_id == session.id)
            )
            return [str(item) for item in result.scalars().all()]
        return [session.agent_config_id] if session.agent_config_id else []

    async def _agent_items(self, agent_ids: list[str], *, cloud_mode: bool = False) -> list[SystemHealthItem]:
        if not agent_ids:
            result = await self.db.execute(
                select(AgentConfig)
                .where(AgentConfig.is_active == True)
                .order_by(AgentConfig.updated_at.desc())
                .limit(5)
            )
            agents = list(result.scalars().all())
            severity: HealthSeverity = "warning"
        else:
            agents = []
            for agent_id in agent_ids:
                agent = await self.db.get(AgentConfig, agent_id)
                if agent and agent.is_active:
                    agents.append(agent)
            severity = "blocking"

        if not agents:
            return [SystemHealthItem(
                key="agent.none",
                label="CLI Agent",
                status="missing",
                severity="blocking" if agent_ids else "warning",
                detail="当前会话没有可用 CLI Agent",
                action=SystemHealthAction(label="打开 Agent 配置", target="agent_panel"),
            )]

        items: list[SystemHealthItem] = []
        for agent in agents:
            if cloud_mode:
                items.append(SystemHealthItem(
                    key=f"agent.{agent.id}.cloud_runtime",
                    label=f"{agent.name} cloud runtime",
                    status="ok",
                    severity="info",
                    detail=f"云端 sandbox 将在隔离运行环境内校验 {agent.cli_tool or agent.executable or 'CLI'}",
                    metadata={
                        "agentId": agent.id,
                        "cliTool": agent.cli_tool,
                        "configured": bool(agent.executable),
                    },
                ))
                continue
            status = CliAgentRegistry.executable_status(agent.executable)
            ok = status.status == "ready"
            items.append(SystemHealthItem(
                key=f"agent.{agent.id}.executable",
                label=f"{agent.name} executable",
                status="ok" if ok else "missing",
                severity="info" if ok else severity,
                detail=(
                    f"已找到 {status.executable_path}"
                    if ok else f"未找到 {agent.executable or agent.cli_tool or 'CLI'} 可执行文件"
                ),
                action=None if ok else SystemHealthAction(label="打开 Agent 配置", target="agent_panel"),
                metadata={
                    "agentId": agent.id,
                    "cliTool": agent.cli_tool,
                    "version": status.version,
                    "configured": bool(agent.executable),
                },
            ))
        return items

    async def _cloud_cli_credential_items(
        self,
        agent_ids: list[str],
        *,
        actor: User | None,
        project: Project | None,
    ) -> list[SystemHealthItem]:
        if not project:
            return []
        cli_tools = await self._native_cli_tools_for_agents(agent_ids)
        if not cli_tools:
            return []
        if not actor:
            return [SystemHealthItem(
                key="cloud.credentials.auth",
                label="CLI 云端凭据",
                status="warning",
                severity="warning",
                detail="未识别当前登录用户，无法检查云端 CLI 凭据",
                action=SystemHealthAction(label="打开 Agent 配置", target="agent_panel"),
            )]

        service = CliCredentialService(self.db)
        items: list[SystemHealthItem] = []
        for cli_tool in cli_tools:
            credential = await service.read_effective_for_project(cli_tool, actor=actor, project=project)
            label = TOOL_LABELS.get(cli_tool, cli_tool)
            configured = credential.configured
            provider = credential.provider_name or credential.provider_id
            model_suffix = f" / {credential.model}" if credential.model else ""
            items.append(SystemHealthItem(
                key=f"cloud.credentials.{cli_tool}",
                label=f"{label} 云端凭据",
                status="ok" if configured else "warning",
                severity="info" if configured else "warning",
                detail=(
                    f"已配置 {provider}{model_suffix}，Runtime 启动时会注入隔离凭据"
                    if configured else f"请先配置 {label} API Key，否则云端 CLI 无法启动"
                ),
                action=None if configured else SystemHealthAction(label="打开 Agent 配置", target="agent_panel"),
                metadata={
                    "cliTool": credential.cli_tool,
                    "scope": credential.scope,
                    "providerId": credential.provider_id,
                    "providerName": credential.provider_name,
                    "model": credential.model,
                    "authEnvKey": credential.auth_env_key,
                    "configured": configured,
                },
            ))
        return items

    async def _native_cli_tools_for_agents(self, agent_ids: list[str]) -> list[str]:
        if not agent_ids:
            result = await self.db.execute(
                select(AgentConfig)
                .where(AgentConfig.is_active == True)
                .order_by(AgentConfig.updated_at.desc())
                .limit(5)
            )
            agents = list(result.scalars().all())
        else:
            agents = []
            for agent_id in agent_ids:
                agent = await self.db.get(AgentConfig, agent_id)
                if agent and agent.is_active:
                    agents.append(agent)

        ordered_tools: list[str] = []
        for agent in agents:
            cli_tool = str(agent.cli_tool or "")
            if cli_tool in NATIVE_CLI_TOOLS and cli_tool not in ordered_tools:
                ordered_tools.append(cli_tool)
        return ordered_tools

    def _codex_item(self) -> SystemHealthItem:
        status = CodexLocalConfigService().status()
        if status.ready:
            health_status: HealthStatus = "ok"
            severity: HealthSeverity = "info"
        elif status.needs_api_key:
            health_status = "warning"
            severity = "warning"
        else:
            health_status = "warning"
            severity = "warning"
        return SystemHealthItem(
            key="agent.codex.config",
            label="Codex 本机配置",
            status=health_status,
            severity=severity,
            detail=status.message,
            action=None if status.ready else SystemHealthAction(label="打开 Agent 配置", target="agent_panel"),
            metadata={
                "connection": status.connection,
                "providerId": status.provider_id,
                "apiKeySet": status.api_key_set,
                "hasChatgptAuth": status.has_chatgpt_auth,
            },
        )

    def _cloud_runtime_image_item(self) -> SystemHealthItem:
        images = list_runtime_images().items
        runtime = next((item for item in images if item.default), images[0] if images else None)
        if not runtime:
            return SystemHealthItem(
                key="cloud.runtime.image",
                label="云端 Runtime Image",
                status="missing",
                severity="blocking",
                detail="未配置云端 Runtime Image，CLI 无法在云端启动",
                action=SystemHealthAction(label="重试", target="retry"),
            )
        return SystemHealthItem(
            key="cloud.runtime.image",
            label="云端 Runtime Image",
            status="ok",
            severity="info",
            detail=f"{runtime.image} · {runtime.provider}",
            metadata={
                "image": runtime.image,
                "provider": runtime.provider,
                "tools": ", ".join(runtime.tools),
                "default": runtime.default,
            },
        )

    def _runtime_item(
        self,
        name: str,
        executable: str,
        *,
        warning_if_missing: bool,
    ) -> SystemHealthItem:
        try:
            resolved = shutil.which(executable)
            if resolved:
                return SystemHealthItem(
                    key=f"runtime.{name}",
                    label=f"{name} runtime",
                    status="ok",
                    severity="info",
                    detail=f"已找到 {resolved}",
                )
        except Exception:
            pass
        return SystemHealthItem(
            key=f"runtime.{name}",
            label=f"{name} runtime",
            status="missing",
            severity="warning" if warning_if_missing else "blocking",
            detail=f"未检测到 {name} runtime",
            action=SystemHealthAction(label="重试", target="retry"),
        )

    def _python_item(self) -> SystemHealthItem:
        return SystemHealthItem(
            key="runtime.python",
            label="Python runtime",
            status="ok",
            severity="info",
            detail=sys.version.split()[0],
            metadata={"executable": sys.executable},
        )

    async def _workspace_item(self, project_id: str | None) -> SystemHealthItem:
        if not project_id:
            return SystemHealthItem(
                key="workspace.path",
                label="项目工作区",
                status="missing",
                severity="blocking",
                detail="未选择项目，无法绑定 workspace",
                action=SystemHealthAction(label="打开项目设置", target="project_settings"),
            )
        project = await self.db.get(Project, project_id)
        if not project or project.status == "archived":
            return SystemHealthItem(
                key="workspace.path",
                label="项目工作区",
                status="missing",
                severity="blocking",
                detail="项目不存在或已归档",
                action=SystemHealthAction(label="打开项目设置", target="project_settings"),
            )
        if project.workspace_mode == "cloud":
            if not project.workspace_id:
                return SystemHealthItem(
                    key="workspace.cloud",
                    label="云端工作区",
                    status="missing",
                    severity="blocking",
                    detail="云端 Project 未绑定 workspace",
                    action=SystemHealthAction(label="打开项目设置", target="project_settings"),
                    metadata={"projectId": project.id},
                )
            return SystemHealthItem(
                key="workspace.cloud",
                label="云端工作区",
                status="ok",
                severity="info",
                detail="云端 workspace 已绑定，sandbox 会使用隔离挂载目录",
                metadata={"projectId": project.id, "workspaceId": project.workspace_id},
            )
        path = Path(project.workspace_path).expanduser()
        if not path.exists() or not path.is_dir():
            return SystemHealthItem(
                key="workspace.path",
                label="项目工作区",
                status="missing",
                severity="blocking",
                detail="项目目录不存在",
                action=SystemHealthAction(label="打开项目设置", target="project_settings"),
                metadata={"projectId": project.id},
            )
        if not os.access(path, os.R_OK | os.W_OK):
            return SystemHealthItem(
                key="workspace.path",
                label="项目工作区",
                status="error",
                severity="blocking",
                detail="项目目录不可读写，Agent 无法保存文件",
                action=SystemHealthAction(label="打开项目设置", target="project_settings"),
                metadata={"projectId": project.id},
            )
        return SystemHealthItem(
            key="workspace.path",
            label="项目工作区",
            status="ok",
            severity="info",
            detail="项目目录可读写",
            metadata={"projectId": project.id},
        )

    def _system_model_item(self, *, warning_if_unconfigured: bool = True) -> SystemHealthItem:
        status = system_model_status()
        configured = status.get("isConfigured") is True
        warning = not configured and warning_if_unconfigured
        return SystemHealthItem(
            key="system.deepseek",
            label="DeepSeek 系统模型",
            status="ok" if not warning else "warning",
            severity="info" if not warning else "warning",
            detail="系统模型可用" if configured else "标题、总结、编辑辅助能力将降级",
            metadata={
                "provider": str(status.get("systemModelProvider") or "deepseek"),
                "model": str(status.get("systemModel") or ""),
                "configured": configured,
            },
        )

    def _process_item(self, session_id: str | None) -> SystemHealthItem:
        snapshots = cli_runtime_registry.active_snapshots(session_id)
        count = len(snapshots)
        return SystemHealthItem(
            key="process.active",
            label="活跃 CLI 进程",
            status="ok",
            severity="info",
            detail=f"当前有 {count} 个活跃 CLI 进程",
            metadata={"activeCount": count},
        )


def _utc_iso() -> str:
    return china_now_iso()
