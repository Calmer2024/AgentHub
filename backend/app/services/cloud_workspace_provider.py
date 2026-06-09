"""Phase 9/10 CloudWorkspaceProvider。

Phase 10 起，云端 workspace 除元数据外还维护一份可挂载的隔离目录，
Sandbox Runner 通过该目录启动 CLI，快照和导入也同步落到物理存储。
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..event_bus.event_types import EventType
from ..models import (
    Project,
    User,
    Workspace,
    WorkspaceImport,
    WorkspaceRestore,
    WorkspaceSnapshot,
)
from .audit_service import AuditService
from .cloud_storage import (
    CloudStorageError,
    copy_workspace_snapshot,
    ensure_cloud_workspace,
    extract_zip_to_workspace,
    restore_workspace_snapshot,
)
from .phase9_schemas import (
    WorkspaceImportRead,
    WorkspaceRead,
    WorkspaceRestoreRead,
    WorkspaceSnapshotRead,
)
from .team_service import PermissionDeniedError, TeamService


MAX_ZIP_IMPORT_BYTES = 25 * 1024 * 1024


class WorkspaceNotFoundCloudError(ValueError):
    pass


class WorkspaceConflictError(ValueError):
    pass


class WorkspaceValidationError(ValueError):
    pass


class WorkspaceUnsupportedMediaError(ValueError):
    pass


class CloudWorkspaceProvider:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus
        self.audit = AuditService(db, event_bus=event_bus)
        self.team_service = TeamService(db, event_bus=event_bus)

    async def create_workspace(
        self,
        *,
        project_id: str,
        project_name: str,
        actor: User,
        team_id: str | None = None,
        template: str | None = None,
    ) -> Workspace:
        workspace_id = str(uuid.uuid4())
        workspace = Workspace(
            id=workspace_id,
            project_id=project_id,
            provider="cloud",
            status="ready",
            storage_uri=_cloud_uri(workspace_id),
            metadata_json=json.dumps({
                "name": project_name,
                "template": template or "blank",
                "phase": "phase10_mountable",
            }, ensure_ascii=False),
        )
        ensure_cloud_workspace(workspace_id, {"projectId": project_id, "name": project_name})
        self.db.add(workspace)
        await self.db.flush()
        await self.audit.record(
            actor_user_id=actor.id,
            team_id=team_id,
            project_id=project_id,
            action="workspace.created",
            resource_type="workspace",
            resource_id=workspace.id,
            metadata={"mode": "cloud", "template": template or "blank"},
        )
        await self._publish(EventType.WORKSPACE_CREATED, {
            "workspaceId": workspace.id,
            "projectId": project_id,
            "teamId": team_id,
            "mode": "cloud",
        })
        return workspace

    async def get_workspace(self, workspace_id: str, actor: User) -> WorkspaceRead:
        workspace, project = await self._get_workspace_and_project(workspace_id)
        await self.team_service.assert_workspace_read_allowed(project, actor)
        return await self._to_read(workspace)

    async def create_snapshot(
        self,
        workspace_id: str,
        label: str | None,
        actor: User,
    ) -> WorkspaceSnapshotRead:
        workspace, project = await self._get_workspace_and_project(workspace_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        await self._assert_not_busy(workspace.id)

        snapshot_id = str(uuid.uuid4())
        clean_label = (label or "").strip() or "手动快照"
        snapshot_path = copy_workspace_snapshot(workspace.id, snapshot_id)
        snapshot = WorkspaceSnapshot(
            id=snapshot_id,
            workspace_id=workspace.id,
            label=clean_label,
            storage_uri=f"{workspace.storage_uri}/snapshots/{snapshot_id}",
            created_by=actor.id,
        )
        self.db.add(snapshot)
        await self.audit.record(
            actor_user_id=actor.id,
            team_id=project.team_id,
            project_id=project.id,
            action="workspace.snapshot.created",
            resource_type="workspace_snapshot",
            resource_id=snapshot.id,
            metadata={"workspaceId": workspace.id, "label": clean_label, "storagePath": str(snapshot_path)},
        )
        await self.db.commit()
        await self.db.refresh(snapshot)
        await self._publish(EventType.WORKSPACE_SNAPSHOT_CREATED, {
            "workspaceId": workspace.id,
            "snapshotId": snapshot.id,
            "label": clean_label,
        })
        return self._snapshot_to_read(snapshot)

    async def restore_snapshot(
        self,
        workspace_id: str,
        snapshot_id: str,
        strategy: str,
        actor: User,
    ) -> str:
        if strategy not in {"replace", "branch"}:
            raise WorkspaceValidationError("unsupported restore strategy")
        workspace, project = await self._get_workspace_and_project(workspace_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        await self._assert_not_busy(workspace.id)
        snapshot = await self.db.get(WorkspaceSnapshot, snapshot_id)
        if not snapshot or snapshot.workspace_id != workspace.id:
            raise WorkspaceNotFoundCloudError("snapshot not found")
        try:
            restore_workspace_snapshot(workspace.id, snapshot.id)
        except CloudStorageError as exc:
            raise WorkspaceValidationError(str(exc)) from exc

        restore_id = str(uuid.uuid4())
        restore = WorkspaceRestore(
            id=restore_id,
            workspace_id=workspace.id,
            snapshot_id=snapshot.id,
            strategy=strategy,
            status="completed",
            created_by=actor.id,
        )
        self.db.add(restore)
        await self.db.flush()
        restore.completed_at = restore.created_at
        await self.audit.record(
            actor_user_id=actor.id,
            team_id=project.team_id,
            project_id=project.id,
            action="workspace.restore.completed",
            resource_type="workspace_restore",
            resource_id=restore.id,
            metadata={"workspaceId": workspace.id, "snapshotId": snapshot.id, "strategy": strategy},
        )
        await self.db.commit()
        await self._publish(EventType.WORKSPACE_RESTORE_COMPLETED, {
            "workspaceId": workspace.id,
            "snapshotId": snapshot.id,
            "strategy": strategy,
        })
        return restore_id

    async def import_zip(
        self,
        workspace_id: str,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
        actor: User,
    ) -> tuple[str, str]:
        workspace, project = await self._get_workspace_and_project(workspace_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        await self._assert_not_busy(workspace.id)
        if len(data) > MAX_ZIP_IMPORT_BYTES:
            raise WorkspaceValidationError("zip file is too large")
        if not filename.lower().endswith(".zip") and content_type not in {
            "application/zip",
            "application/x-zip-compressed",
        }:
            raise WorkspaceUnsupportedMediaError("unsupported import type")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = [name for name in archive.namelist() if not name.endswith("/")]
        except zipfile.BadZipFile as exc:
            raise WorkspaceValidationError("invalid zip file") from exc
        try:
            extracted_names = extract_zip_to_workspace(workspace.id, data)
        except CloudStorageError as exc:
            raise WorkspaceValidationError(str(exc)) from exc

        import_id = str(uuid.uuid4())
        metadata = {
            "filename": filename,
            "fileCount": len(extracted_names),
            "files": extracted_names[:50],
        }
        item = WorkspaceImport(
            id=import_id,
            workspace_id=workspace.id,
            source="zip",
            status="completed",
            detail=f"已导入 {len(extracted_names)} 个文件",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            created_by=actor.id,
        )
        self.db.add(item)
        await self.db.flush()
        item.completed_at = item.created_at
        await self.audit.record(
            actor_user_id=actor.id,
            team_id=project.team_id,
            project_id=project.id,
            action="workspace.import.completed",
            resource_type="workspace_import",
            resource_id=item.id,
            metadata={"workspaceId": workspace.id, "source": "zip", "fileCount": len(extracted_names)},
        )
        await self.db.commit()
        await self._publish(EventType.WORKSPACE_IMPORT_COMPLETED, {
            "workspaceId": workspace.id,
            "importId": item.id,
            "source": "zip",
        })
        return item.id, item.status

    async def import_github(
        self,
        workspace_id: str,
        *,
        repo_url: str,
        branch: str | None,
        actor: User,
    ) -> tuple[str, str]:
        workspace, project = await self._get_workspace_and_project(workspace_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        clean_repo = repo_url.strip()
        if not _looks_like_github_repo(clean_repo):
            raise WorkspaceValidationError("invalid GitHub repo URL")

        import_id = str(uuid.uuid4())
        item = WorkspaceImport(
            id=import_id,
            workspace_id=workspace.id,
            source="github",
            status="queued",
            detail="已创建 GitHub 导入占位任务，Phase 10 接入真实 runner 后执行",
            metadata_json=json.dumps({
                "repoUrl": clean_repo,
                "branch": (branch or "").strip() or None,
                "phase": "phase9_placeholder",
            }, ensure_ascii=False),
            created_by=actor.id,
        )
        self.db.add(item)
        await self.audit.record(
            actor_user_id=actor.id,
            team_id=project.team_id,
            project_id=project.id,
            action="workspace.import.queued",
            resource_type="workspace_import",
            resource_id=item.id,
            metadata={"workspaceId": workspace.id, "source": "github", "repoUrl": clean_repo},
        )
        await self.db.commit()
        return item.id, item.status

    async def mark_workspace_archived(self, workspace_id: str) -> None:
        workspace = await self.db.get(Workspace, workspace_id)
        if workspace:
            workspace.status = "archived"

    async def mark_workspace_deleted(self, workspace_id: str) -> None:
        workspace = await self.db.get(Workspace, workspace_id)
        if workspace:
            workspace.status = "deleted"

    async def _get_workspace_and_project(self, workspace_id: str) -> tuple[Workspace, Project]:
        workspace = await self.db.get(Workspace, workspace_id)
        if not workspace:
            raise WorkspaceNotFoundCloudError("workspace not found")
        project = await self.db.get(Project, workspace.project_id)
        if not project or project.status == "archived":
            raise WorkspaceNotFoundCloudError("workspace project not found")
        return workspace, project

    async def _assert_not_busy(self, workspace_id: str) -> None:
        result = await self.db.execute(
            select(WorkspaceImport).where(
                WorkspaceImport.workspace_id == workspace_id,
                WorkspaceImport.status == "running",
            )
        )
        if result.scalars().first():
            raise WorkspaceConflictError("workspace is busy")
        result = await self.db.execute(
            select(WorkspaceRestore).where(
                WorkspaceRestore.workspace_id == workspace_id,
                WorkspaceRestore.status == "running",
            )
        )
        if result.scalars().first():
            raise WorkspaceConflictError("workspace is busy")

    async def _to_read(self, workspace: Workspace) -> WorkspaceRead:
        snapshots = await self.db.execute(
            select(WorkspaceSnapshot)
            .where(WorkspaceSnapshot.workspace_id == workspace.id)
            .order_by(WorkspaceSnapshot.created_at.desc())
        )
        imports = await self.db.execute(
            select(WorkspaceImport)
            .where(WorkspaceImport.workspace_id == workspace.id)
            .order_by(WorkspaceImport.created_at.desc())
        )
        restores = await self.db.execute(
            select(WorkspaceRestore)
            .where(WorkspaceRestore.workspace_id == workspace.id)
            .order_by(WorkspaceRestore.created_at.desc())
        )
        return WorkspaceRead(
            id=workspace.id,
            project_id=workspace.project_id,
            provider=workspace.provider,
            status=workspace.status,
            storage_uri=workspace.storage_uri,
            snapshots=[self._snapshot_to_read(item) for item in snapshots.scalars().all()],
            imports=[self._import_to_read(item) for item in imports.scalars().all()],
            restores=[self._restore_to_read(item) for item in restores.scalars().all()],
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )

    def _snapshot_to_read(self, snapshot: WorkspaceSnapshot) -> WorkspaceSnapshotRead:
        return WorkspaceSnapshotRead(
            id=snapshot.id,
            workspace_id=snapshot.workspace_id,
            label=snapshot.label,
            storage_uri=snapshot.storage_uri,
            created_by=snapshot.created_by,
            created_at=snapshot.created_at,
        )

    def _import_to_read(self, item: WorkspaceImport) -> WorkspaceImportRead:
        return WorkspaceImportRead(
            id=item.id,
            workspace_id=item.workspace_id,
            source=item.source,
            status=item.status,
            detail=item.detail,
            metadata=_json_dict(item.metadata_json),
            created_by=item.created_by,
            created_at=item.created_at,
            completed_at=item.completed_at,
        )

    def _restore_to_read(self, item: WorkspaceRestore) -> WorkspaceRestoreRead:
        return WorkspaceRestoreRead(
            id=item.id,
            workspace_id=item.workspace_id,
            snapshot_id=item.snapshot_id,
            strategy=item.strategy,
            status=item.status,
            created_at=item.created_at,
            completed_at=item.completed_at,
        )

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)


def _cloud_uri(workspace_id: str) -> str:
    return f"cloud://agenthub/workspaces/{workspace_id}"


def _looks_like_github_repo(repo_url: str) -> bool:
    return repo_url.startswith("https://github.com/") or repo_url.startswith("git@github.com:")


def _json_dict(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
