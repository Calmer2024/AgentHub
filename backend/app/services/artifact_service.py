"""Artifact lifecycle service for Phase 5 versioning and editing."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.artifact_editor import ArtifactEditor, DiffResult
from ..event_bus.event_types import EventType
from ..models import Artifact, Message, Project, Session
from .system_llm import SystemLLMUnavailableError, system_llm
from .workspace_provider import LocalWorkspaceProvider, WorkspaceSecurityError


class ArtifactNotFoundError(ValueError):
    """Raised when an artifact cannot be found."""


class ArtifactVersionNotFoundError(ValueError):
    """Raised when a requested artifact version is missing."""


class ArtifactEditError(ValueError):
    """Raised when an edit request cannot be applied."""


class ArtifactWorkspaceWriteError(ValueError):
    """Raised when an artifact file cannot be written back to workspace."""


EDIT_ARTIFACT_TOOL = {
    "name": "edit_artifact",
    "description": "对产物进行局部修改",
    "parameters": {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string"},
            "selection": {"type": "string", "description": "选中的原始代码片段"},
            "instruction": {"type": "string", "description": "修改意图描述"},
            "edit_type": {
                "type": "string",
                "enum": ["replace", "insert_after", "insert_before", "delete"],
            },
            "replacement": {
                "type": "string",
                "description": "replace/insert 操作使用的新内容",
            },
        },
        "required": ["artifact_id", "selection", "instruction", "edit_type"],
    },
}


@dataclass
class EditPreview:
    artifact: Artifact | None
    diff: DiffResult
    proposed_content: str
    strategy: str
    tool_call: dict[str, Any] | None = None


@dataclass
class ArtifactDetection:
    session_id: str
    message_id: str
    artifact_type: str
    title: str
    content: str
    source: str
    confidence: float
    content_hash: str
    project_id: str | None = None
    file_path: str | None = None
    preview_id: str | None = None
    task_id: str | None = None
    status: str = "ready"
    reason: str = ""


class ArtifactService:
    """Version chain, diff, and natural-language edit operations."""

    def __init__(self, db: AsyncSession, event_bus: Any = None, editor: ArtifactEditor | None = None):
        self.db = db
        self.event_bus = event_bus
        self.editor = editor or ArtifactEditor()
        self.workspace = LocalWorkspaceProvider()

    async def create_version(
        self,
        artifact_id: str,
        content: str,
        *,
        title: str | None = None,
        status: str | None = None,
    ) -> Artifact:
        current = await self._get_artifact(artifact_id)
        version = Artifact(
            id=str(uuid.uuid4()),
            session_id=current.session_id,
            message_id=current.message_id,
            project_id=current.project_id,
            type=current.type,
            title=title if title is not None else current.title,
            content=content,
            status=status if status is not None else current.status,
            version=(current.version or 1) + 1,
            parent_artifact_id=current.id,
            file_path=current.file_path,
            preview_id=current.preview_id,
            source=current.source,
            confidence=current.confidence,
            task_id=current.task_id,
        )
        self.db.add(version)
        await self.db.commit()
        await self.db.refresh(version)
        await self._publish(EventType.ARTIFACT_CREATED, {
            "artifactId": version.id,
            "sessionId": version.session_id,
            "messageId": version.message_id,
            "projectId": version.project_id,
            "artifactType": version.type,
            "title": version.title,
            "version": version.version,
            "parentArtifactId": version.parent_artifact_id,
            "filePath": version.file_path,
            "source": version.source,
        })
        return version

    async def save_content(
        self,
        artifact_id: str,
        content: str,
        *,
        title: str | None = None,
        write_workspace: bool = True,
    ) -> Artifact:
        current = await self._get_artifact(artifact_id)
        if write_workspace:
            await self._write_workspace_file(current, content)
        return await self.create_version(
            artifact_id,
            content,
            title=title,
            status="ready",
        )

    async def restore_version(
        self,
        artifact_id: str,
        version: int,
        *,
        write_workspace: bool = True,
    ) -> Artifact:
        versions = await self.get_versions(artifact_id)
        target = next((item for item in versions if (item.version or 1) == version), None)
        if not target:
            raise ArtifactVersionNotFoundError("artifact version not found")
        current = await self._get_artifact(artifact_id)
        if target.id == current.id:
            return current
        if write_workspace:
            await self._write_workspace_file(current, target.content)
        return await self.create_version(
            current.id,
            target.content,
            title=current.title,
            status="ready",
        )

    async def create_from_detection(self, detection: ArtifactDetection) -> tuple[Artifact, bool]:
        """Create or version an artifact from bridge detection.

        Workspace-backed artifacts are identified by project/session/type/file_path. A later
        detection for the same file becomes the next version instead of a duplicate asset card.
        """
        existing = await self._find_detection_duplicate(detection)
        if existing:
            return existing, False

        head = await self._find_detection_identity_head(detection)
        if head:
            if (head.task_id or "") == detection.content_hash:
                return head, False
            version = Artifact(
                id=str(uuid.uuid4()),
                session_id=detection.session_id,
                message_id=detection.message_id,
                project_id=detection.project_id,
                type=detection.artifact_type,
                title=detection.title or head.title,
                content=detection.content,
                status=detection.status,
                version=(head.version or 1) + 1,
                parent_artifact_id=head.id,
                file_path=detection.file_path,
                preview_id=detection.preview_id or head.preview_id,
                source=detection.source,
                confidence=f"{detection.confidence:.2f}",
                task_id=detection.task_id or detection.content_hash,
            )
            self.db.add(version)
            await self.db.commit()
            await self.db.refresh(version)
            await self._publish(EventType.ARTIFACT_CREATED, {
                "artifactId": version.id,
                "id": version.id,
                "sessionId": version.session_id,
                "messageId": version.message_id,
                "projectId": version.project_id,
                "artifactType": version.type,
                "type": version.type,
                "title": version.title,
                "content": version.content,
                "status": version.status,
                "version": version.version,
                "parentArtifactId": version.parent_artifact_id,
                "filePath": version.file_path,
                "previewId": version.preview_id,
                "source": version.source,
                "createdAt": version.created_at.isoformat() if version.created_at else "",
            })
            return version, True

        artifact = Artifact(
            id=str(uuid.uuid4()),
            session_id=detection.session_id,
            message_id=detection.message_id,
            project_id=detection.project_id,
            type=detection.artifact_type,
            title=detection.title,
            content=detection.content,
            status=detection.status,
            version=1,
            file_path=detection.file_path,
            preview_id=detection.preview_id,
            source=detection.source,
            confidence=f"{detection.confidence:.2f}",
            task_id=detection.task_id or detection.content_hash,
        )
        self.db.add(artifact)
        await self.db.commit()
        await self.db.refresh(artifact)
        await self._publish(EventType.ARTIFACT_CREATED, {
            "artifactId": artifact.id,
            "sessionId": artifact.session_id,
            "messageId": artifact.message_id,
            "projectId": artifact.project_id,
            "artifactType": artifact.type,
            "type": artifact.type,
            "title": artifact.title,
            "version": artifact.version,
            "filePath": artifact.file_path,
            "source": artifact.source,
        })
        return artifact, True

    async def list_current_artifacts(self, session_id: str) -> list[Artifact]:
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.session_id == session_id)
            .order_by(Artifact.created_at.desc())
        )
        artifacts = list(result.scalars().all())
        parent_ids = {a.parent_artifact_id for a in artifacts if a.parent_artifact_id}
        heads = [a for a in artifacts if a.id not in parent_ids]
        grouped: dict[tuple[str, ...], Artifact] = {}
        for artifact in heads:
            key = self._artifact_identity_key(artifact)
            current = grouped.get(key)
            if not current or self._is_newer_head(artifact, current):
                grouped[key] = artifact
        return sorted(grouped.values(), key=lambda a: a.created_at or datetime.min, reverse=True)

    async def get_versions(self, artifact_id: str) -> list[Artifact]:
        start = await self._get_artifact(artifact_id)
        chain: list[Artifact] = []
        seen: set[str] = set()
        current: Artifact | None = start

        while current and current.id not in seen:
            chain.append(current)
            seen.add(current.id)
            parent_id = current.parent_artifact_id
            current = await self.db.get(Artifact, parent_id) if parent_id else None

        latest_version = max((a.version or 1 for a in chain), default=start.version or 1)
        cursor_ids = {a.id for a in chain}
        while True:
            child = await self._find_child(cursor_ids, latest_version + 1)
            if not child:
                break
            chain.append(child)
            cursor_ids.add(child.id)
            latest_version = child.version or latest_version + 1

        return sorted(chain, key=lambda a: (a.version or 1, a.created_at or datetime.min))

    async def get_diff(self, artifact_id: str, v1: int, v2: int) -> DiffResult:
        versions = await self.get_versions(artifact_id)
        by_version = {a.version or 1: a for a in versions}
        left = by_version.get(v1)
        right = by_version.get(v2)
        if not left or not right:
            raise ArtifactVersionNotFoundError("artifact version not found")
        return self.editor.build_diff(left.content, right.content, v1, v2)

    async def preview_edit(
        self,
        artifact_id: str,
        selection: str,
        instruction: str,
        edit_type: str = "replace",
    ) -> EditPreview:
        artifact = await self._get_artifact(artifact_id)
        normalized_selection = selection.strip("\n")
        normalized_instruction = instruction.strip()
        if not normalized_selection:
            raise ArtifactEditError("selection must not be empty")
        if not normalized_instruction:
            raise ArtifactEditError("instruction must not be empty")
        if normalized_selection not in artifact.content:
            raise ArtifactEditError("selection not found in artifact content")

        can_use_tool = system_llm.is_configured() and system_llm.capability.supports_tool_call

        if can_use_tool:
            try:
                response = await system_llm.chat(
                    messages=[{
                        "role": "user",
                        "content": (
                            f"修改产物 {artifact.id}。\n"
                            f"选中内容:\n{normalized_selection}\n"
                            f"修改意图:\n{normalized_instruction}"
                        ),
                    }],
                    system_prompt=(
                        "你是代码编辑器。请使用 edit_artifact tool 返回 edit_type、selection "
                        "和 replacement，不要直接改数据库。"
                    ),
                    tools=[EDIT_ARTIFACT_TOOL],
                )
                tool_call = self.editor.parse_tool_call(response.tool_calls)
                if tool_call:
                    try:
                        proposed = self.editor.apply_tool_payload(artifact.content, normalized_selection, tool_call)
                    except ValueError as exc:
                        raise ArtifactEditError(str(exc))
                    return EditPreview(
                        artifact=None,
                        diff=self.editor.build_diff(
                            artifact.content,
                            proposed,
                            artifact.version or 1,
                            (artifact.version or 1) + 1,
                        ),
                        proposed_content=proposed,
                        strategy="system_tool_call",
                        tool_call=tool_call,
                    )
            except (SystemLLMUnavailableError, Exception):
                pass

        proposed = await self._fallback_context_injection(
            artifact,
            normalized_selection,
            normalized_instruction,
            edit_type,
        )
        return EditPreview(
            artifact=None,
            diff=self.editor.build_diff(
                artifact.content,
                proposed,
                artifact.version or 1,
                (artifact.version or 1) + 1,
            ),
            proposed_content=proposed,
            strategy="fallback_context",
        )

    async def apply_edit(
        self,
        artifact_id: str,
        selection: str,
        instruction: str,
        edit_type: str = "replace",
        proposed_content: str | None = None,
        apply: bool = False,
    ) -> EditPreview:
        artifact = await self._get_artifact(artifact_id)
        if proposed_content is None:
            preview = await self.preview_edit(artifact_id, selection, instruction, edit_type)
        else:
            preview = EditPreview(
                artifact=None,
                diff=self.editor.build_diff(
                    artifact.content,
                    proposed_content,
                    artifact.version or 1,
                    (artifact.version or 1) + 1,
                ),
                proposed_content=proposed_content,
                strategy="confirmed_preview",
            )

        if not apply:
            return preview

        created = await self.create_version(artifact_id, preview.proposed_content)
        await self._publish(EventType.ARTIFACT_UPDATED, {
            "artifactId": created.id,
            "previousArtifactId": artifact.id,
            "sessionId": created.session_id,
            "messageId": created.message_id,
            "version": created.version,
        })
        preview.artifact = created
        preview.diff = self.editor.build_diff(
            artifact.content,
            created.content,
            artifact.version or 1,
            created.version or (artifact.version or 1) + 1,
        )
        return preview

    async def _get_artifact(self, artifact_id: str) -> Artifact:
        artifact = await self.db.get(Artifact, artifact_id)
        if not artifact:
            raise ArtifactNotFoundError("artifact not found")
        return artifact

    async def _find_child(self, parent_ids: set[str], next_version: int) -> Artifact | None:
        result = await self.db.execute(
            select(Artifact)
            .where(
                Artifact.parent_artifact_id.in_(parent_ids),
                Artifact.version == next_version,
            )
            .order_by(Artifact.created_at.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def _find_detection_duplicate(self, detection: ArtifactDetection) -> Artifact | None:
        filters = [
            Artifact.message_id == detection.message_id,
            Artifact.type == detection.artifact_type,
            Artifact.source == detection.source,
            Artifact.task_id == detection.content_hash,
        ]
        if detection.file_path:
            filters.append(Artifact.file_path == detection.file_path)
        else:
            filters.append(Artifact.file_path.is_(None))
        result = await self.db.execute(
            select(Artifact)
            .where(*filters)
            .order_by(Artifact.created_at.asc())
            .limit(1)
        )
        existing = result.scalars().first()
        if existing or detection.source != "manual_rescan":
            return existing

        fallback_filters = [
            Artifact.message_id == detection.message_id,
            Artifact.type == detection.artifact_type,
            Artifact.task_id == detection.content_hash,
        ]
        if detection.file_path:
            fallback_filters.append(Artifact.file_path == detection.file_path)
        else:
            fallback_filters.append(Artifact.file_path.is_(None))
        result = await self.db.execute(
            select(Artifact)
            .where(*fallback_filters)
            .order_by(Artifact.created_at.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def _find_detection_identity_head(self, detection: ArtifactDetection) -> Artifact | None:
        if not detection.file_path:
            return None
        filters = [
            Artifact.session_id == detection.session_id,
            Artifact.type == detection.artifact_type,
            Artifact.file_path == detection.file_path,
        ]
        if detection.project_id:
            filters.append(Artifact.project_id == detection.project_id)
        else:
            filters.append(Artifact.project_id.is_(None))

        result = await self.db.execute(
            select(Artifact)
            .where(*filters)
            .order_by(Artifact.created_at.desc())
        )
        candidates = list(result.scalars().all())
        if not candidates:
            return None
        parent_ids = {artifact.parent_artifact_id for artifact in candidates if artifact.parent_artifact_id}
        heads = [artifact for artifact in candidates if artifact.id not in parent_ids]
        if not heads:
            heads = candidates
        head = sorted(
            heads,
            key=lambda artifact: (
                artifact.version or 1,
                artifact.created_at or datetime.min,
            ),
            reverse=True,
        )[0]
        return head

    @staticmethod
    def _artifact_identity_key(artifact: Artifact) -> tuple[str, ...]:
        if artifact.file_path:
            return (
                "file",
                artifact.session_id,
                artifact.project_id or "",
                artifact.type,
                artifact.file_path,
            )
        return ("id", artifact.id)

    @staticmethod
    def _is_newer_head(candidate: Artifact, current: Artifact) -> bool:
        candidate_key = (candidate.version or 1, candidate.created_at or datetime.min)
        current_key = (current.version or 1, current.created_at or datetime.min)
        return candidate_key > current_key

    async def _write_workspace_file(self, artifact: Artifact, content: str) -> None:
        if not artifact.project_id or not artifact.file_path:
            return
        project = await self.db.get(Project, artifact.project_id)
        if not project:
            raise ArtifactWorkspaceWriteError("artifact project not found")
        try:
            target = self.workspace.safe_resolve(project.workspace_path, artifact.file_path)
        except WorkspaceSecurityError as exc:
            raise ArtifactWorkspaceWriteError("artifact file path is outside workspace") from exc
        root = Path(project.workspace_path).expanduser().resolve()
        if target == root or target.exists() and target.is_dir():
            raise ArtifactWorkspaceWriteError("artifact file path is not a file")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    async def _fallback_context_injection(
        self,
        artifact: Artifact,
        selection: str,
        instruction: str,
        edit_type: str,
    ) -> str:
        replacement = self.editor.deterministic_rewrite(selection, instruction, edit_type)
        if system_llm.is_configured():
            try:
                response = await system_llm.chat(
                    messages=[{
                        "role": "user",
                        "content": (
                            "请对代码执行修改，只返回修改后的选中片段，不要解释。\n"
                            f"修改类型: {edit_type}\n"
                            f"修改意图: {instruction}\n"
                            f"选中内容:\n{selection}"
                        ),
                    }],
                    system_prompt="你是代码编辑器。输出应该可以直接替换用户选中的原文。",
                )
                replacement = self.editor.extract_replacement(response.content)
            except (SystemLLMUnavailableError, Exception):
                pass
        try:
            return self.editor.apply_edit_operation(artifact.content, selection, replacement, edit_type)
        except ValueError as exc:
            raise ArtifactEditError(str(exc))

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)
