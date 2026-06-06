"""Phase 7C 统一环境体检聚合。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.cli_runtime import cli_process_manager
from ..core.timezone import china_now_iso
from ..models import AgentConfig, Project, Session as DBSession, SessionMember
from .cli_agent_registry import CliAgentRegistry
from .codex_local_config_service import CodexLocalConfigService
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
    ) -> SystemHealthRead:
        session = await self.db.get(DBSession, session_id) if session_id else None
        effective_project_id = project_id or (session.project_id if session else None)
        effective_agent_ids = await self._effective_agent_ids(session, agent_id)

        items: list[SystemHealthItem] = []
        items.extend(await self._agent_items(effective_agent_ids))
        items.append(self._codex_item())
        items.append(self._runtime_item("node", ["node", "--version"], warning_if_missing=True))
        items.append(self._python_item())
        items.append(await self._workspace_item(effective_project_id))
        items.append(self._system_model_item())
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

    async def _agent_items(self, agent_ids: list[str]) -> list[SystemHealthItem]:
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

    def _runtime_item(
        self,
        name: str,
        command: list[str],
        *,
        warning_if_missing: bool,
    ) -> SystemHealthItem:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            output = (result.stdout or result.stderr or "").strip().splitlines()
            if result.returncode == 0 and output:
                return SystemHealthItem(
                    key=f"runtime.{name}",
                    label=f"{name} runtime",
                    status="ok",
                    severity="info",
                    detail=output[0][:100],
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

    def _system_model_item(self) -> SystemHealthItem:
        status = system_model_status()
        configured = status.get("isConfigured") is True
        return SystemHealthItem(
            key="system.deepseek",
            label="DeepSeek 系统模型",
            status="ok" if configured else "warning",
            severity="info" if configured else "warning",
            detail="系统模型可用" if configured else "标题、总结、编辑辅助能力将降级",
            metadata={
                "provider": str(status.get("systemModelProvider") or "deepseek"),
                "model": str(status.get("systemModel") or ""),
                "configured": configured,
            },
        )

    def _process_item(self, session_id: str | None) -> SystemHealthItem:
        snapshots = cli_process_manager.active_snapshots(session_id)
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
