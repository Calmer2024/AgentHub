"""Phase 7B 人工审批 checkpoint 服务。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..models import ApprovalCheckpoint, Artifact, Message, RunTask
from .context_pack_service import ContextPackService
from .run_service import RunService
from .runtime_schemas import ApprovalCheckpointRead


class ApprovalNotFoundError(LookupError):
    pass


class InvalidApprovalStateError(ValueError):
    pass


class ApprovalService:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus

    async def create_checkpoint(
        self,
        *,
        run_id: str,
        task_id: str,
        session_id: str,
        message_id: str | None,
        artifact_id: str | None = None,
        artifact_version: int | None = None,
        title: str = "等待确认",
        summary: str = "",
        metadata: dict | None = None,
    ) -> ApprovalCheckpoint:
        existing = await self._pending_for_task(task_id)
        if existing:
            return existing
        checkpoint = ApprovalCheckpoint(
            id=str(uuid.uuid4()),
            run_id=run_id,
            task_id=task_id,
            session_id=session_id,
            message_id=message_id,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            title=title.strip() or "等待确认",
            summary=summary.strip() or "请确认本轮产出是否可以继续。",
            status="pending_review",
            created_at=_utcnow(),
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        self.db.add(checkpoint)
        task = await self.db.get(RunTask, task_id)
        if task:
            task.status = "paused"
            task.message_id = message_id or task.message_id
            metadata_obj = _loads(task.metadata_json)
            metadata_obj["requiresHumanApproval"] = True
            task.metadata_json = json.dumps(metadata_obj, ensure_ascii=False)
        await self._merge_message_metadata(
            message_id,
            {
                "approvalCheckpointId": checkpoint.id,
                "approvalStatus": "pending_review",
            },
        )
        await self.db.commit()
        await self.db.refresh(checkpoint)
        return checkpoint

    async def list_session(self, session_id: str) -> list[ApprovalCheckpointRead]:
        result = await self.db.execute(
            select(ApprovalCheckpoint)
            .where(ApprovalCheckpoint.session_id == session_id)
            .order_by(ApprovalCheckpoint.created_at.asc(), ApprovalCheckpoint.id.asc())
        )
        return [approval_to_read(item) for item in result.scalars().all()]

    async def get(self, checkpoint_id: str) -> ApprovalCheckpoint:
        checkpoint = await self.db.get(ApprovalCheckpoint, checkpoint_id)
        if not checkpoint:
            raise ApprovalNotFoundError(checkpoint_id)
        return checkpoint

    async def approve(
        self,
        checkpoint_id: str,
        *,
        artifact_id: str | None = None,
        artifact_version: int | None = None,
        comment: str | None = None,
    ) -> ApprovalCheckpoint:
        checkpoint = await self.get(checkpoint_id)
        self._ensure_pending(checkpoint)
        checkpoint.status = "approved"
        checkpoint.decided_at = _utcnow()
        if artifact_id:
            checkpoint.artifact_id = artifact_id
        if artifact_version:
            checkpoint.artifact_version = artifact_version
        if comment:
            metadata = _loads(checkpoint.metadata_json)
            metadata["comment"] = comment
            checkpoint.metadata_json = json.dumps(metadata, ensure_ascii=False)
        run_service = RunService(self.db, event_bus=self.event_bus)
        await run_service.mark_task_status(
            checkpoint.task_id,
            "completed",
            metadata_patch={"approvalStatus": "approved", "approvalCheckpointId": checkpoint.id},
        )
        await run_service.complete_run_from_tasks(checkpoint.run_id)
        await self._merge_message_metadata(
            checkpoint.message_id,
            {
                "approvalCheckpointId": checkpoint.id,
                "approvalStatus": "approved",
            },
        )
        await ContextPackService(self.db, event_bus=self.event_bus).build(
            checkpoint.session_id,
            purpose="approval_resume",
            persist=True,
        )
        await self.db.commit()
        await self.db.refresh(checkpoint)
        return checkpoint

    async def reject(
        self,
        checkpoint_id: str,
        *,
        reason: str,
        artifact_id: str | None = None,
        artifact_version: int | None = None,
        code_reference: dict | None = None,
    ) -> ApprovalCheckpoint:
        if not reason.strip():
            raise ValueError("reason required")
        checkpoint = await self.get(checkpoint_id)
        self._ensure_pending(checkpoint)
        checkpoint.status = "rejected"
        checkpoint.reason = reason.strip()
        checkpoint.decided_at = _utcnow()
        if artifact_id:
            checkpoint.artifact_id = artifact_id
        if artifact_version:
            checkpoint.artifact_version = artifact_version
        metadata = _loads(checkpoint.metadata_json)
        if code_reference:
            metadata["codeReference"] = code_reference
        checkpoint.metadata_json = json.dumps(metadata, ensure_ascii=False)
        run_service = RunService(self.db, event_bus=self.event_bus)
        await run_service.mark_task_status(
            checkpoint.task_id,
            "rejected",
            metadata_patch={
                "approvalStatus": "rejected",
                "approvalCheckpointId": checkpoint.id,
                "rejectReason": reason.strip(),
            },
        )
        await run_service.complete_run_from_tasks(checkpoint.run_id)
        await self._merge_message_metadata(
            checkpoint.message_id,
            {
                "approvalCheckpointId": checkpoint.id,
                "approvalStatus": "rejected",
                "approvalRejectReason": reason.strip(),
            },
        )
        await ContextPackService(self.db, event_bus=self.event_bus).build(
            checkpoint.session_id,
            purpose="approval_resume",
            persist=True,
        )
        await self.db.commit()
        await self.db.refresh(checkpoint)
        return checkpoint

    async def create_for_completed_task_if_needed(
        self,
        *,
        task_id: str,
        message_id: str | None,
        summary: str,
    ) -> ApprovalCheckpoint | None:
        task = await self.db.get(RunTask, task_id)
        if not task:
            return None
        metadata = _loads(task.metadata_json)
        if metadata.get("requiresHumanApproval") is not True:
            return None
        artifact_id = await self._latest_artifact_id(message_id)
        return await self.create_checkpoint(
            run_id=task.run_id,
            task_id=task.id,
            session_id=task.session_id,
            message_id=message_id or task.message_id,
            artifact_id=artifact_id,
            title=str(metadata.get("approvalTitle") or f"确认 {task.name}"),
            summary=summary or "请确认本轮产出是否可以继续。",
            metadata={"source": "runtime"},
        )

    async def _pending_for_task(self, task_id: str) -> ApprovalCheckpoint | None:
        result = await self.db.execute(
            select(ApprovalCheckpoint)
            .where(
                ApprovalCheckpoint.task_id == task_id,
                ApprovalCheckpoint.status == "pending_review",
            )
            .limit(1)
        )
        return result.scalars().first()

    async def _latest_artifact_id(self, message_id: str | None) -> str | None:
        if not message_id:
            return None
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.message_id == message_id)
            .order_by(Artifact.created_at.desc(), Artifact.id.desc())
            .limit(1)
        )
        artifact = result.scalars().first()
        return artifact.id if artifact else None

    async def _merge_message_metadata(self, message_id: str | None, patch: dict) -> None:
        if not message_id:
            return
        message = await self.db.get(Message, message_id)
        if not message:
            return
        metadata = _loads(message.metadata_json)
        metadata.update(patch)
        message.metadata_json = json.dumps(metadata, ensure_ascii=False)

    @staticmethod
    def _ensure_pending(checkpoint: ApprovalCheckpoint) -> None:
        if checkpoint.status != "pending_review":
            raise InvalidApprovalStateError("approval already decided")


def approval_to_read(checkpoint: ApprovalCheckpoint) -> ApprovalCheckpointRead:
    return ApprovalCheckpointRead(
        id=checkpoint.id,
        run_id=checkpoint.run_id,
        task_id=checkpoint.task_id,
        session_id=checkpoint.session_id,
        message_id=checkpoint.message_id,
        artifact_id=checkpoint.artifact_id,
        artifact_version=checkpoint.artifact_version,
        title=checkpoint.title,
        summary=checkpoint.summary,
        status=checkpoint.status,
        reason=checkpoint.reason,
        created_at=checkpoint.created_at,
        decided_at=checkpoint.decided_at,
        metadata=_loads(checkpoint.metadata_json) or None,
    )


def _loads(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _utcnow():
    return china_now()
