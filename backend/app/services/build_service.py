"""Phase 8 本地构建、预览与导出服务。"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.process_utils import hidden_subprocess_kwargs
from ..core.timezone import china_now
from ..event_bus.event_types import EventType
from ..models import BuildLog, BuildRun, Project
from .phase8_schemas import BuildLogChunkRead, BuildRunRead
from .preview_service import PreviewService
from .workspace_provider import EXCLUDED_NAMES, LocalWorkspaceProvider, WorkspaceSecurityError


ACTIVE_BUILD_STATUSES = {"queued", "running"}
TERMINAL_BUILD_STATUSES = {"succeeded", "failed", "cancelled"}


class BuildNotFoundError(LookupError):
    pass


class BuildConflictError(ValueError):
    pass


class BuildValidationError(ValueError):
    pass


class BuildNotReadyError(ValueError):
    pass


class BuildService:
    def __init__(
        self,
        db: AsyncSession,
        event_bus: Any = None,
        provider: LocalWorkspaceProvider | None = None,
        preview: PreviewService | None = None,
    ):
        self.db = db
        self.event_bus = event_bus
        self.provider = provider or LocalWorkspaceProvider()
        self.preview = preview or PreviewService(self.provider)

    async def run_build(
        self,
        project_id: str,
        *,
        command: str | None,
        install_command: str | None = None,
        artifact_path: str | None = None,
    ) -> BuildRun:
        project = await self._get_project(project_id)
        self._ensure_local_project(project)
        workspace = self.provider.safe_resolve(project.workspace_path)
        if not workspace.is_dir():
            raise BuildValidationError("workspace not found")
        if not os.access(workspace, os.W_OK):
            raise BuildValidationError("workspace is not writable")
        await self._ensure_no_active_build(project.id)

        build_command = _clean_command(command) or self._detect_build_command(workspace)
        install = _clean_command(install_command)
        build = BuildRun(
            id=str(uuid.uuid4()),
            project_id=project.id,
            status="queued",
            command=build_command,
            install_command=install,
            artifact_path=_clean_path(artifact_path),
            created_at=china_now(),
        )
        self.db.add(build)
        project.status = "building"
        await self.db.commit()
        await self.db.refresh(build)
        await self._publish(EventType.BUILD_QUEUED, {
            "buildId": build.id,
            "projectId": project.id,
            "command": build.command,
        })

        build.status = "running"
        build.started_at = china_now()
        await self.db.commit()
        await self._publish(EventType.BUILD_STARTED, {
            "buildId": build.id,
            "projectId": project.id,
            "status": "running",
            "command": build.command,
        })

        exit_code = 0
        if install:
            exit_code = await self._run_command(build, workspace, install, phase="install")
        if exit_code == 0:
            exit_code = await self._run_command(build, workspace, build.command, phase="build")

        build.exit_code = exit_code
        build.finished_at = china_now()
        if exit_code == 0:
            try:
                build.artifact_path = self._resolve_artifact_path(workspace, build.artifact_path)
            except BuildValidationError as exc:
                build.status = "failed"
                build.error_summary = str(exc)
                project.status = "ready"
                await self._append_log(build.id, "stderr", f"{exc}\n", phase="artifact")
                await self._publish(EventType.BUILD_FAILED, {
                    "buildId": build.id,
                    "projectId": project.id,
                    "exitCode": 0,
                    "errorSummary": build.error_summary,
                })
            else:
                build.status = "succeeded"
                project.status = "ready"
                await self._publish(EventType.BUILD_COMPLETED, {
                    "buildId": build.id,
                    "projectId": project.id,
                    "artifactPath": build.artifact_path,
                    "durationMs": _duration_ms(build),
                })
        else:
            build.status = "failed"
            build.error_summary = await self._last_error_summary(build.id)
            project.status = "ready"
            await self._publish(EventType.BUILD_FAILED, {
                "buildId": build.id,
                "projectId": project.id,
                "exitCode": exit_code,
                "errorSummary": build.error_summary,
            })
        await self.db.commit()
        await self.db.refresh(build)
        return build

    async def list_builds(self, project_id: str) -> list[BuildRunRead]:
        await self._get_project(project_id)
        result = await self.db.execute(
            select(BuildRun)
            .where(BuildRun.project_id == project_id)
            .order_by(BuildRun.created_at.desc(), BuildRun.id.desc())
        )
        return [build_to_read(build) for build in result.scalars().all()]

    async def get_build(self, project_id: str, build_id: str) -> BuildRun:
        build = await self.db.get(BuildRun, build_id)
        if not build or build.project_id != project_id:
            raise BuildNotFoundError(build_id)
        return build

    async def get_logs(self, project_id: str, build_id: str) -> list[BuildLogChunkRead]:
        await self.get_build(project_id, build_id)
        result = await self.db.execute(
            select(BuildLog)
            .where(BuildLog.build_id == build_id)
            .order_by(BuildLog.sequence.asc(), BuildLog.id.asc())
        )
        return [log_to_read(log) for log in result.scalars().all()]

    async def export_source(self, project_id: str) -> tuple[bytes, str]:
        project = await self._get_project(project_id)
        self._ensure_local_project(project)
        await self._ensure_no_active_build(project.id)
        root = self.provider.safe_resolve(project.workspace_path)
        data = _zip_path(root, root, archive_root_name=Path(project.workspace_path).name or "workspace")
        return data, f"{_safe_filename(project.name)}-source.zip"

    async def export_build(self, project_id: str, build_id: str) -> tuple[bytes, str]:
        project = await self._get_project(project_id)
        self._ensure_local_project(project)
        build = await self.get_build(project.id, build_id)
        if build.status != "succeeded":
            raise BuildNotReadyError("build is not completed")
        if not build.artifact_path:
            raise BuildNotReadyError("build artifact path is empty")
        artifact_root = self.provider.safe_resolve(project.workspace_path, build.artifact_path)
        if not artifact_root.exists():
            raise BuildNotReadyError("build artifact path not found")
        workspace = self.provider.safe_resolve(project.workspace_path)
        data = _zip_path(workspace, artifact_root, archive_root_name=Path(build.artifact_path).name or "build")
        return data, f"{_safe_filename(project.name)}-{build.id[:8]}-build.zip"

    async def create_preview(
        self,
        project_id: str,
        *,
        source: str,
        path: str | None = None,
        build_id: str | None = None,
    ) -> dict:
        project = await self._get_project(project_id)
        self._ensure_local_project(project)
        if source not in {"workspace", "build"}:
            raise BuildValidationError("unsupported preview source")
        entry = _clean_path(path)
        if source == "build":
            if not build_id:
                raise BuildValidationError("buildId required")
            build = await self.get_build(project.id, build_id)
            if build.status != "succeeded":
                raise BuildNotReadyError("build is not completed")
            base = _join_posix(build.artifact_path or ".", entry or "index.html")
            result = self.preview.create_static_preview(project.id, project.workspace_path, base)
        else:
            result = self.preview.create_static_preview(project.id, project.workspace_path, entry)
        payload = {
            "previewId": result["previewId"],
            "url": result["previewUrl"],
            "source": source,
        }
        await self._publish(EventType.PREVIEW_CREATED, {
            "projectId": project.id,
            "previewId": payload["previewId"],
            "source": source,
            "url": payload["url"],
        })
        return payload

    async def _run_command(self, build: BuildRun, workspace: Path, command: str, *, phase: str) -> int:
        await self._append_log(build.id, "stdout", f"$ {command}\n", phase=phase)
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **hidden_subprocess_kwargs(),
        )
        sequence = await self._next_log_sequence(build.id)
        stdout_task = asyncio.create_task(
            self._read_stream(build.id, process.stdout, "stdout", sequence, phase=phase),
        )
        stderr_task = asyncio.create_task(
            self._read_stream(build.id, process.stderr, "stderr", sequence + 10_000, phase=phase),
        )
        exit_code = await process.wait()
        await asyncio.gather(stdout_task, stderr_task)
        await self._append_log(
            build.id,
            "stdout" if exit_code == 0 else "stderr",
            f"[{phase}] exit code: {exit_code}\n",
            phase=phase,
        )
        return int(exit_code or 0)

    async def _read_stream(
        self,
        build_id: str,
        stream: asyncio.StreamReader | None,
        stream_name: str,
        start_sequence: int,
        *,
        phase: str,
    ) -> None:
        if stream is None:
            return
        sequence = start_sequence
        while True:
            chunk = await stream.readline()
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            await self._append_log(build_id, stream_name, text, sequence=sequence, phase=phase)
            sequence += 1

    async def _append_log(
        self,
        build_id: str,
        stream: str,
        text: str,
        *,
        sequence: int | None = None,
        phase: str,
    ) -> None:
        log = BuildLog(
            id=str(uuid.uuid4()),
            build_id=build_id,
            sequence=sequence if sequence is not None else await self._next_log_sequence(build_id),
            stream=stream,
            text=text,
            created_at=china_now(),
        )
        self.db.add(log)
        await self.db.flush()
        await self._publish(EventType.BUILD_LOG, {
            "buildId": build_id,
            "sequence": log.sequence,
            "stream": stream,
            "text": text,
            "phase": phase,
        })

    async def _next_log_sequence(self, build_id: str) -> int:
        result = await self.db.execute(
            select(BuildLog.sequence)
            .where(BuildLog.build_id == build_id)
            .order_by(BuildLog.sequence.desc())
            .limit(1)
        )
        current = result.scalars().first()
        return int(current or 0) + 1

    async def _last_error_summary(self, build_id: str) -> str:
        result = await self.db.execute(
            select(BuildLog)
            .where(BuildLog.build_id == build_id, BuildLog.stream == "stderr")
            .order_by(BuildLog.sequence.desc())
            .limit(1)
        )
        log = result.scalars().first()
        if log and log.text.strip():
            return log.text.strip()[:500]
        return "构建命令异常退出"

    def _detect_build_command(self, workspace: Path) -> str:
        package_json = workspace / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                scripts = data.get("scripts") if isinstance(data, dict) else None
                if isinstance(scripts, dict) and isinstance(scripts.get("build"), str):
                    return "npm run build"
            except json.JSONDecodeError:
                pass
        return f"\"{sys.executable}\" -c \"print('AgentHub: no build script configured; using workspace snapshot')\""

    def _resolve_artifact_path(self, workspace: Path, requested: str | None) -> str:
        if requested:
            target = self.provider.safe_resolve(str(workspace), requested)
            if not target.exists():
                raise BuildValidationError("artifact path not found")
            return target.relative_to(workspace).as_posix() or "."
        for candidate in ("dist", "build", "out"):
            target = workspace / candidate
            if target.exists():
                return candidate
        return "."

    async def _ensure_no_active_build(self, project_id: str) -> None:
        result = await self.db.execute(
            select(BuildRun)
            .where(BuildRun.project_id == project_id, BuildRun.status.in_(list(ACTIVE_BUILD_STATUSES)))
            .limit(1)
        )
        if result.scalars().first():
            raise BuildConflictError("active build already exists")

    async def _get_project(self, project_id: str) -> Project:
        project = await self.db.get(Project, project_id)
        if not project or project.status == "archived":
            raise BuildNotFoundError(project_id)
        return project

    def _ensure_local_project(self, project: Project) -> None:
        if project.workspace_mode == "cloud":
            raise BuildValidationError("cloud workspace build/preview/export is available from Phase 11")

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)


def build_to_read(build: BuildRun) -> BuildRunRead:
    return BuildRunRead(
        id=build.id,
        project_id=build.project_id,
        status=build.status,
        command=build.command,
        install_command=build.install_command,
        artifact_path=build.artifact_path,
        exit_code=build.exit_code,
        error_summary=build.error_summary,
        created_at=build.created_at,
        started_at=build.started_at,
        finished_at=build.finished_at,
    )


def log_to_read(log: BuildLog) -> BuildLogChunkRead:
    return BuildLogChunkRead(
        sequence=log.sequence,
        stream=log.stream,
        text=log.text,
        created_at=log.created_at,
    )


def _zip_path(workspace_root: Path, target: Path, *, archive_root_name: str) -> bytes:
    workspace = workspace_root.resolve()
    target = target.resolve()
    if target != workspace and workspace not in target.parents:
        raise WorkspaceSecurityError("path outside workspace")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        files = [target] if target.is_file() else sorted(target.rglob("*"), key=lambda p: str(p))
        for path in files:
            if path.is_dir() or _is_excluded(path, workspace):
                continue
            rel = path.relative_to(target if target.is_dir() else target.parent)
            zip_file.write(path, f"{archive_root_name}/{rel.as_posix()}")
    return buffer.getvalue()


def _is_excluded(path: Path, workspace: Path) -> bool:
    try:
        parts = path.relative_to(workspace).parts
    except ValueError:
        return True
    return any(part in EXCLUDED_NAMES for part in parts)


def _duration_ms(build: BuildRun) -> int:
    if not build.started_at or not build.finished_at:
        return 0
    return int((build.finished_at - build.started_at).total_seconds() * 1000)


def _safe_filename(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in name).strip("-") or "project"


def _clean_command(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _clean_path(value: str | None) -> str | None:
    text = (value or "").replace("\\", "/").strip("/")
    return text or None


def _join_posix(left: str, right: str) -> str:
    left = _clean_path(left) or "."
    right = _clean_path(right) or "index.html"
    if left == ".":
        return right
    return f"{left}/{right}"
