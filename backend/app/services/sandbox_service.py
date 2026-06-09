"""Phase 10 Sandbox 生命周期服务。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.timezone import china_now
from ..event_bus.event_types import EventType
from ..models import Project, Sandbox, User, Workspace
from .cloud_storage import ensure_cloud_workspace
from .phase10_schemas import SandboxCreate, SandboxRead
from .quota_service import (
    ACTIVE_SANDBOX_STATUSES,
    QuotaExceededError,
    QuotaService,
    parse_resource_limits,
    resource_limits_json,
)
from .team_service import TeamService


class SandboxNotFoundError(LookupError):
    pass


class SandboxValidationError(ValueError):
    pass


class SandboxService:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus
        self.team_service = TeamService(db, event_bus=event_bus)
        self.quota = QuotaService(db, event_bus=event_bus)

    async def create_sandbox(self, data: SandboxCreate, actor: User) -> SandboxRead:
        workspace, project = await self._workspace_project(data.workspace_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        active = await self.quota.active_sandbox_count(actor)
        if active >= self.quota.concurrent_runs_limit:
            await self._publish(EventType.QUOTA_EXCEEDED, {
                "subjectType": "user",
                "subjectId": actor.id,
                "quotaType": "concurrent_sandboxes",
                "used": active,
                "limit": self.quota.concurrent_runs_limit,
            })
            raise QuotaExceededError("cloud sandbox concurrent quota exceeded")

        ensure_cloud_workspace(workspace.id, {"projectId": project.id})
        sandbox = Sandbox(
            id=str(uuid.uuid4()),
            workspace_id=workspace.id,
            status="ready",
            image=(data.image or "agenthub/default-cli:phase10").strip(),
            runner_node_id=settings.agenthub_cloud_runner_node_id,
            resource_limits_json=resource_limits_json(self.quota.resource_limits()),
        )
        self.db.add(sandbox)
        await self.db.commit()
        await self.db.refresh(sandbox)
        await self._publish(EventType.SANDBOX_CREATED, {
            "sandboxId": sandbox.id,
            "workspaceId": workspace.id,
            "projectId": project.id,
            "image": sandbox.image,
        })
        await self._publish(EventType.SANDBOX_READY, {
            "sandboxId": sandbox.id,
            "workspaceId": workspace.id,
            "projectId": project.id,
        })
        return sandbox_to_read(sandbox)

    async def get_sandbox(self, sandbox_id: str, actor: User) -> SandboxRead:
        sandbox, _workspace, project = await self._sandbox_workspace_project(sandbox_id)
        await self.team_service.assert_workspace_read_allowed(project, actor)
        return sandbox_to_read(sandbox)

    async def stop_sandbox(self, sandbox_id: str, actor: User, reason: str | None = None) -> SandboxRead:
        sandbox, _workspace, project = await self._sandbox_workspace_project(sandbox_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        await self.mark_stopped(sandbox, reason=reason)
        return sandbox_to_read(sandbox)

    async def reuse_or_create(
        self,
        *,
        workspace_id: str,
        actor: User,
        image: str = "agenthub/default-cli:phase10",
    ) -> Sandbox:
        workspace, project = await self._workspace_project(workspace_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        result = await self.db.execute(
            select(Sandbox)
            .where(
                Sandbox.workspace_id == workspace.id,
                Sandbox.status.in_(ACTIVE_SANDBOX_STATUSES),
            )
            .order_by(Sandbox.created_at.desc())
            .limit(1)
        )
        existing = result.scalars().first()
        if existing:
            return existing
        read = await self.create_sandbox(SandboxCreate(workspace_id=workspace_id, image=image), actor)
        sandbox = await self.db.get(Sandbox, read.id)
        if not sandbox:
            raise SandboxNotFoundError(read.id)
        return sandbox

    async def mark_stopped(self, sandbox: Sandbox, *, reason: str | None = None) -> None:
        if sandbox.status == "stopped":
            return
        sandbox.status = "stopped"
        sandbox.updated_at = china_now()
        sandbox.stopped_at = sandbox.stopped_at or china_now()
        await self.db.commit()
        await self.db.refresh(sandbox)
        await self._publish(EventType.SANDBOX_STOPPED, {
            "sandboxId": sandbox.id,
            "workspaceId": sandbox.workspace_id,
            "reason": reason,
        })

    async def _workspace_project(self, workspace_id: str) -> tuple[Workspace, Project]:
        workspace = await self.db.get(Workspace, workspace_id)
        if not workspace or workspace.status in {"archived", "deleted"}:
            raise SandboxNotFoundError("workspace not found")
        if workspace.provider != "cloud":
            raise SandboxValidationError("sandbox requires cloud workspace")
        project = await self.db.get(Project, workspace.project_id)
        if not project or project.status == "archived":
            raise SandboxNotFoundError("workspace project not found")
        return workspace, project

    async def _sandbox_workspace_project(self, sandbox_id: str) -> tuple[Sandbox, Workspace, Project]:
        sandbox = await self.db.get(Sandbox, sandbox_id)
        if not sandbox:
            raise SandboxNotFoundError("sandbox not found")
        workspace, project = await self._workspace_project(sandbox.workspace_id)
        return sandbox, workspace, project

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if not self.event_bus:
            return
        await self.event_bus.publish(event_type, payload)


def sandbox_to_read(sandbox: Sandbox) -> SandboxRead:
    return SandboxRead(
        id=sandbox.id,
        workspace_id=sandbox.workspace_id,
        status=sandbox.status,
        image=sandbox.image,
        runner_node_id=sandbox.runner_node_id,
        resource_limits=parse_resource_limits(sandbox.resource_limits_json),
        created_at=sandbox.created_at,
        updated_at=sandbox.updated_at,
        stopped_at=sandbox.stopped_at,
    )
