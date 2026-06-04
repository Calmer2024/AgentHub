"""Artifact lifecycle service for Phase 5 versioning and editing."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.registry import agent_registry
from ..domain.artifact_editor import ArtifactEditor, DiffResult
from ..event_bus.event_types import EventType
from ..models import AgentConfig, Artifact, Message, Session


class ArtifactNotFoundError(ValueError):
    """Raised when an artifact cannot be found."""


class ArtifactVersionNotFoundError(ValueError):
    """Raised when a requested artifact version is missing."""


class ArtifactEditError(ValueError):
    """Raised when an edit request cannot be applied."""


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


class ArtifactService:
    """Version chain, diff, and natural-language edit operations."""

    def __init__(self, db: AsyncSession, event_bus: Any = None, editor: ArtifactEditor | None = None):
        self.db = db
        self.event_bus = event_bus
        self.editor = editor or ArtifactEditor()

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
            "version": version.version,
            "parentArtifactId": version.parent_artifact_id,
        })
        return version

    async def list_current_artifacts(self, session_id: str) -> list[Artifact]:
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.session_id == session_id)
            .order_by(Artifact.created_at.desc())
        )
        artifacts = list(result.scalars().all())
        parent_ids = {a.parent_artifact_id for a in artifacts if a.parent_artifact_id}
        heads = [a for a in artifacts if a.id not in parent_ids]
        return sorted(heads, key=lambda a: a.created_at or datetime.min, reverse=True)

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

        agent = await self._agent_for_artifact(artifact)
        adapter = agent_registry.get_adapter(agent.provider) if agent else None
        can_use_tool = bool(
            adapter
            and agent
            and agent_registry.is_available(agent.provider)
            and adapter.capability.supports_tool_call
        )

        if can_use_tool:
            response = await adapter.chat(
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
                model=agent.model or None,
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
                    strategy="tool_call",
                    tool_call=tool_call,
                )

        proposed = await self._fallback_context_injection(
            artifact,
            normalized_selection,
            normalized_instruction,
            edit_type,
            agent,
            adapter,
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

    async def _agent_for_artifact(self, artifact: Artifact) -> AgentConfig | None:
        message = await self.db.get(Message, artifact.message_id)
        if message and message.source_id:
            agent = await self.db.get(AgentConfig, message.source_id)
            if agent:
                return agent
        session = await self.db.get(Session, artifact.session_id)
        if session and session.agent_config_id:
            agent = await self.db.get(AgentConfig, session.agent_config_id)
            if agent:
                return agent
        if message and message.agent_name:
            result = await self.db.execute(
                select(AgentConfig).where(AgentConfig.name == message.agent_name).limit(1)
            )
            return result.scalars().first()
        return None

    async def _fallback_context_injection(
        self,
        artifact: Artifact,
        selection: str,
        instruction: str,
        edit_type: str,
        agent: AgentConfig | None,
        adapter: Any,
    ) -> str:
        if adapter and agent and agent_registry.is_available(agent.provider):
            response = await adapter.chat(
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
                model=agent.model or None,
            )
            replacement = self.editor.extract_replacement(response.content)
        else:
            replacement = self.editor.deterministic_rewrite(selection, instruction, edit_type)
        try:
            return self.editor.apply_edit_operation(artifact.content, selection, replacement, edit_type)
        except ValueError as exc:
            raise ArtifactEditError(str(exc))

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)
