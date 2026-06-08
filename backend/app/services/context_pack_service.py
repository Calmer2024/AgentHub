"""Phase 8 统一上下文包构造服务。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.context_manager import ContextManager
from ..event_bus.event_types import EventType
from ..models import ApprovalCheckpoint, Artifact, ContextPackSnapshot, Session as DBSession
from .message_service_sqlalchemy import SqlAlchemyMessageService
from .phase8_schemas import ContextPackBlockRead, ContextPackPreviewRead


VALID_CONTEXT_PURPOSES = {"send", "approval_resume", "artifact_edit"}


class ContextPackNotFoundError(LookupError):
    pass


class ContextPackValidationError(ValueError):
    pass


class ContextPackService:
    def __init__(
        self,
        db: AsyncSession,
        event_bus: Any = None,
        context_manager: ContextManager | None = None,
    ):
        self.db = db
        self.event_bus = event_bus
        self.context_manager = context_manager or ContextManager()
        self.messages = SqlAlchemyMessageService(db, self.context_manager)

    async def build(
        self,
        session_id: str,
        *,
        purpose: str,
        persist: bool = True,
    ) -> dict[str, Any]:
        purpose = purpose.strip()
        if purpose not in VALID_CONTEXT_PURPOSES:
            raise ContextPackValidationError("unsupported context pack purpose")
        session = await self.db.get(DBSession, session_id)
        if not session:
            raise ContextPackNotFoundError(session_id)

        history, pinned_ids = await self.messages.history_for_session(session_id)
        artifact_count = await self._artifact_count(session_id)
        approval_count = await self._pending_approval_count(session_id)
        blocks = self._blocks(history, pinned_ids, artifact_count, approval_count, purpose)
        warnings = self._warnings(session, history, artifact_count, purpose)
        payload = {
            "sessionId": session_id,
            "purpose": purpose,
            "history": history,
            "pinnedMessageIds": pinned_ids,
            "artifactCount": artifact_count,
            "pendingApprovalCount": approval_count,
            "blocks": [block.model_dump(by_alias=True) for block in blocks],
            "warnings": warnings,
        }
        snapshot_id = str(uuid.uuid4())
        if persist:
            snapshot = ContextPackSnapshot(
                id=snapshot_id,
                session_id=session_id,
                purpose=purpose,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
            self.db.add(snapshot)
            await self.db.commit()
            await self._publish(EventType.CONTEXT_PACK_CREATED, {
                "contextPackId": snapshot.id,
                "sessionId": session_id,
                "purpose": purpose,
                "messageCount": len(history),
                "artifactCount": artifact_count,
            })
        return {
            "id": snapshot_id,
            "sessionId": session_id,
            "purpose": purpose,
            "blocks": blocks,
            "warnings": warnings,
            "history": history,
            "pinnedMessageIds": pinned_ids,
        }

    async def runtime_context(self, session_id: str, *, purpose: str = "send") -> tuple[list[dict], list[str]]:
        pack = await self.build(session_id, purpose=purpose, persist=True)
        return list(pack["history"]), [str(item) for item in pack["pinnedMessageIds"]]

    async def preview(self, session_id: str, *, purpose: str) -> ContextPackPreviewRead:
        pack = await self.build(session_id, purpose=purpose, persist=True)
        return ContextPackPreviewRead(
            id=pack["id"],
            session_id=session_id,
            purpose=purpose,
            blocks=pack["blocks"],
            warnings=pack["warnings"],
        )

    def _blocks(
        self,
        history: list[dict],
        pinned_ids: list[str],
        artifact_count: int,
        approval_count: int,
        purpose: str,
    ) -> list[ContextPackBlockRead]:
        message_tokens = self.context_manager.estimate_tokens(history)
        blocks = [
            ContextPackBlockRead(type="messages", title="最近对话上下文", token_estimate=message_tokens),
        ]
        if pinned_ids:
            blocks.append(ContextPackBlockRead(
                type="pinned_messages",
                title=f"{len(pinned_ids)} 条置顶消息",
                token_estimate=max(1, len(pinned_ids) * 80),
            ))
        if artifact_count:
            blocks.append(ContextPackBlockRead(
                type="artifacts",
                title=f"{artifact_count} 个会话产物",
                token_estimate=max(1, artifact_count * 120),
            ))
        if approval_count or purpose == "approval_resume":
            blocks.append(ContextPackBlockRead(
                type="approval",
                title="审批恢复上下文",
                token_estimate=max(80, approval_count * 80),
            ))
        if purpose == "artifact_edit":
            blocks.append(ContextPackBlockRead(
                type="artifact_edit",
                title="产物继续编辑上下文",
                token_estimate=120,
            ))
        return blocks

    @staticmethod
    def _warnings(
        session: DBSession,
        history: list[dict],
        artifact_count: int,
        purpose: str,
    ) -> list[str]:
        warnings: list[str] = []
        if not session.project_id:
            warnings.append("当前会话未绑定 Project，CLI Agent 无法获得 workspace cwd。")
        if not history:
            warnings.append("当前会话暂无历史消息。")
        if purpose == "artifact_edit" and artifact_count == 0:
            warnings.append("当前会话暂无可引用产物。")
        return warnings

    async def _artifact_count(self, session_id: str) -> int:
        result = await self.db.execute(
            select(func.count(Artifact.id)).where(Artifact.session_id == session_id)
        )
        return int(result.scalar_one() or 0)

    async def _pending_approval_count(self, session_id: str) -> int:
        result = await self.db.execute(
            select(func.count(ApprovalCheckpoint.id)).where(
                ApprovalCheckpoint.session_id == session_id,
                ApprovalCheckpoint.status == "pending_review",
            )
        )
        return int(result.scalar_one() or 0)

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)
