"""Project 与 workspace runtime 业务服务。"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..event_bus.event_types import EventType
from ..models import Artifact, Message, Project, Session as DBSession, SessionMember
from .file_change_detector import FileChangeDetector
from .preview_service import PreviewService
from .schemas import ProjectCreate, ProjectRead
from .workspace_provider import (
    LocalWorkspaceProvider,
    WorkspaceFileTooLargeError,
    WorkspaceNotFoundError,
    WorkspaceSecurityError,
    sanitize_dir_name,
    utc_iso,
)


DEFAULT_PROJECT_NAME = "默认项目"
_FOLDER_GRANTS: dict[str, str] = {}


class ProjectNotFoundError(ValueError):
    pass


class ProjectConflictError(ValueError):
    pass


class ProjectValidationError(ValueError):
    pass


class ProjectDeleteSafetyError(ValueError):
    pass


class ProjectService:
    def __init__(
        self,
        db: AsyncSession,
        event_bus: Any = None,
        provider: LocalWorkspaceProvider | None = None,
        detector: FileChangeDetector | None = None,
        preview: PreviewService | None = None,
    ):
        self.db = db
        self.event_bus = event_bus
        self.provider = provider or LocalWorkspaceProvider()
        self.detector = detector or FileChangeDetector()
        self.preview = preview or PreviewService(self.provider)

    async def create_project(self, data: ProjectCreate) -> ProjectRead:
        name = data.name.strip()
        if not name:
            raise ProjectValidationError("project name must not be empty")

        workspace_path = self._resolve_workspace_path(
            name,
            data.workspace_path,
            data.folder_token,
        )
        existing = await self._find_project_by_workspace(workspace_path)
        if existing and existing.status != "archived":
            raise ProjectConflictError(f"workspace is already used by {existing.name}")

        if existing:
            project = existing
            project.name = name
            project.workspace_path = str(workspace_path)
            project.project_type = "existing"
            project.status = "ready"
            project.metadata_json = json.dumps({}, ensure_ascii=False)
        else:
            project = Project(
                id=str(uuid.uuid4()),
                name=name,
                workspace_path=str(workspace_path),
                project_type="existing",
                status="ready",
                metadata_json=json.dumps({}, ensure_ascii=False),
            )
            self.db.add(project)

        await self.db.commit()
        await self.db.refresh(project)

        self.provider.ensure_workspace(project.workspace_path, self._metadata(project))
        await self._publish(EventType.PROJECT_CREATED, {
            "projectId": project.id,
            "name": project.name,
            "workspacePath": project.workspace_path,
        })
        return await self._to_read(project, include_stats=False)

    async def list_projects(self) -> list[ProjectRead]:
        result = await self.db.execute(
            select(Project)
            .where(Project.status != "archived")
            .order_by(Project.updated_at.desc())
        )
        return [await self._to_read(p, include_stats=False) for p in result.scalars().all()]

    async def get_project(self, project_id: str) -> ProjectRead:
        project = await self._get_project(project_id)
        return await self._to_read(project, include_stats=True)

    async def archive_project(self, project_id: str) -> dict:
        project = await self._get_project(project_id)
        project.status = "archived"
        await self.db.commit()
        return {"status": "archived"}

    async def rename_project(self, project_id: str, name: str) -> ProjectRead:
        project = await self._get_project(project_id)
        clean_name = name.strip()
        if not clean_name:
            raise ProjectValidationError("project name must not be empty")

        project.name = clean_name
        await self.db.commit()
        await self.db.refresh(project)

        self._write_project_metadata(project)
        return await self._to_read(project, include_stats=False)

    async def delete_project(self, project_id: str, delete_files: bool = False) -> dict:
        project = await self._get_project(project_id)
        workspace_path = Path(project.workspace_path).expanduser().resolve()

        if delete_files:
            self._ensure_workspace_can_be_deleted(project, workspace_path)

        session_ids = await self._project_session_ids(project.id)
        if session_ids:
            await self.db.execute(
                delete(SessionMember).where(SessionMember.session_id.in_(session_ids))
            )
            await self.db.execute(
                delete(Artifact).where(Artifact.session_id.in_(session_ids))
            )
            await self.db.execute(
                delete(Message).where(Message.session_id.in_(session_ids))
            )
            await self.db.execute(
                delete(DBSession).where(DBSession.id.in_(session_ids))
            )
        await self.db.execute(delete(Artifact).where(Artifact.project_id == project.id))
        await self.db.delete(project)
        await self.db.commit()

        if delete_files:
            shutil.rmtree(workspace_path)

        return {
            "status": "deleted",
            "filesDeleted": delete_files,
            "workspacePath": str(workspace_path),
        }

    async def get_tree(self, project_id: str, subpath: str | None = None) -> list[dict]:
        project = await self._get_project(project_id)
        entries = self.provider.list_tree(project.workspace_path, subpath)
        return [entry.__dict__ for entry in entries]

    async def read_file(self, project_id: str, path: str) -> dict:
        project = await self._get_project(project_id)
        content, size = self.provider.read_text_file(project.workspace_path, path)
        return {"path": path.replace("\\", "/"), "content": content, "size": size}

    async def create_snapshot(self, project_id: str, label: str) -> dict:
        project = await self._get_project(project_id)
        clean_label = label.strip()
        if not clean_label:
            raise ProjectValidationError("snapshot label must not be empty")
        snap = self.detector.create_snapshot(project.workspace_path, clean_label)
        return {
            "snapshotId": snap.snapshot_id,
            "label": snap.label,
            "createdAt": snap.created_at,
        }

    async def get_diff(self, project_id: str, base_ref: str) -> dict:
        project = await self._get_project(project_id)
        changes = self.detector.diff_from_snapshot(project.workspace_path, base_ref)
        await self._publish(EventType.WORKSPACE_FILE_CHANGED, {
            "projectId": project.id,
            "changes": [{"path": c["path"], "change": c["change"]} for c in changes],
        })
        await self._publish(EventType.WORKSPACE_DIFF_READY, {
            "projectId": project.id,
            "changedFiles": len(changes),
            "diffSummary": ", ".join(c["path"] for c in changes[:10]),
        })
        return {"changedFiles": changes}

    async def create_preview(
        self,
        project_id: str,
        preview_type: str,
        entry_path: str | None = None,
    ) -> dict:
        project = await self._get_project(project_id)
        if preview_type not in {"static", "vite-react"}:
            raise ProjectValidationError("unsupported preview type")
        result = self.preview.create_static_preview(project.id, project.workspace_path, entry_path)
        await self._publish(EventType.PREVIEW_READY, {
            "projectId": project.id,
            "previewId": result["previewId"],
            "previewUrl": result["previewUrl"],
        })
        return result

    async def start_build(self, project_id: str) -> dict:
        project = await self._get_project(project_id)
        build_id = str(uuid.uuid4())
        project.status = "building"
        await self.db.commit()
        await self._publish(EventType.BUILD_STARTED, {
            "projectId": project.id,
            "buildId": build_id,
            "status": "building",
        })
        return {"buildId": build_id, "status": "building"}

    async def get_workspace_path_for_session(self, session_id: str) -> str:
        session = await self.db.get(DBSession, session_id)
        if not session or not session.project_id:
            raise ProjectNotFoundError("session has no project")
        project = await self._get_project(session.project_id)
        return project.workspace_path

    async def ensure_default_project(self) -> Project:
        result = await self.db.execute(
            select(Project)
            .where(Project.status != "archived")
            .order_by(Project.created_at.asc())
            .limit(1)
        )
        project = result.scalars().first()
        if project:
            return project
        created = await self.create_project(ProjectCreate(name=DEFAULT_PROJECT_NAME))
        project = await self.db.get(Project, created.id)
        assert project is not None
        return project

    async def attach_legacy_sessions_to_default_project(self) -> None:
        project = await self.ensure_default_project()
        result = await self.db.execute(
            select(DBSession).where(DBSession.project_id.is_(None))
        )
        sessions = result.scalars().all()
        for session in sessions:
            session.project_id = project.id
        if sessions:
            await self.db.commit()

    async def _get_project(self, project_id: str) -> Project:
        project = await self.db.get(Project, project_id)
        if not project or project.status == "archived":
            raise ProjectNotFoundError(project_id)
        return project

    async def _find_project_by_workspace(self, workspace_path: Path) -> Project | None:
        result = await self.db.execute(
            select(Project).where(
                Project.workspace_path == str(workspace_path),
            )
        )
        return result.scalars().first()

    async def _project_session_ids(self, project_id: str) -> list[str]:
        result = await self.db.execute(
            select(DBSession.id).where(DBSession.project_id == project_id)
        )
        return [str(session_id) for session_id in result.scalars().all()]

    def _resolve_workspace_path(
        self,
        name: str,
        workspace_path: str | None,
        folder_token: str | None,
    ) -> Path:
        root = Path(settings.agenthub_workspace_root).expanduser().resolve()
        if workspace_path:
            candidate = Path(workspace_path).expanduser().resolve()
            if candidate != root and root not in candidate.parents:
                granted = consume_folder_grant(folder_token)
                if granted != candidate:
                    raise ProjectValidationError("workspace path is outside allowlist root")
            return candidate
        return _next_available_path(root / sanitize_dir_name(name))

    async def _to_read(self, project: Project, include_stats: bool) -> ProjectRead:
        file_count = 0
        total_size = 0
        if include_stats:
            try:
                entries = self.provider.list_tree(project.workspace_path)
                file_entries = [e for e in entries if e.type == "file"]
                file_count = len(file_entries)
                total_size = sum(e.size for e in file_entries)
            except (WorkspaceNotFoundError, WorkspaceSecurityError):
                pass
        return ProjectRead(
            id=project.id,
            name=project.name,
            workspace_path=project.workspace_path,
            status=project.status,
            file_count=file_count,
            total_size_bytes=total_size,
            created_at=project.created_at,
        )

    def _write_project_metadata(self, project: Project) -> None:
        target = Path(project.workspace_path) / ".agenthub" / "project.json"
        if not target.exists():
            return
        target.write_text(
            json.dumps(self._metadata(project), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _ensure_workspace_can_be_deleted(self, project: Project, workspace_path: Path) -> None:
        if not workspace_path.exists() or not workspace_path.is_dir():
            raise ProjectDeleteSafetyError("workspace folder not found")

        marker = workspace_path / ".agenthub" / "project.json"
        if not marker.exists():
            raise ProjectDeleteSafetyError("missing AgentHub workspace marker")

        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectDeleteSafetyError("invalid AgentHub workspace marker") from exc

        if metadata.get("projectId") != project.id:
            raise ProjectDeleteSafetyError("workspace marker does not match project")

        protected_roots = {
            Path.home().resolve(),
            Path(settings.agenthub_workspace_root).expanduser().resolve(),
            Path.cwd().resolve(),
        }
        if workspace_path in protected_roots or workspace_path.parent == workspace_path:
            raise ProjectDeleteSafetyError("refusing to delete protected workspace path")

    def _metadata(self, project: Project) -> dict:
        return {
            "projectId": project.id,
            "name": project.name,
            "workspacePath": project.workspace_path,
            "createdAt": utc_iso(),
            "createdBy": "agenthub",
        }

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)


def _next_available_path(base: Path) -> Path:
    if not base.exists():
        return base
    for i in range(2, 1000):
        candidate = base.with_name(f"{base.name}-{i}")
        if not candidate.exists():
            return candidate
    return base.with_name(f"{base.name}-{uuid.uuid4().hex[:8]}")


def register_folder_grant(workspace_path: str) -> str:
    token = str(uuid.uuid4())
    _FOLDER_GRANTS[token] = str(Path(workspace_path).expanduser().resolve())
    return token


def consume_folder_grant(folder_token: str | None) -> Path | None:
    if not folder_token:
        return None
    granted = _FOLDER_GRANTS.pop(folder_token, None)
    return Path(granted).resolve() if granted else None
