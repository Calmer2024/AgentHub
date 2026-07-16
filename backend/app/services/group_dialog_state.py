"""群聊直接对话焦点状态。

第一版把状态沉淀在消息 metadata 中，避免过早引入持久化表。
后续 direct dialog 体验稳定后，可迁移为 session_dialog_states 表。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..models import AgentConfig, Message as DBMessage, Session as DBSession


ACTIVE_DIALOG_STATUSES = {"active", "awaiting_user_input", "agent_responding", "ready_for_handoff"}


@dataclass(frozen=True)
class GroupDialogState:
    session_id: str
    agent_id: str
    agent_name: str
    status: str
    goal: str = ""
    source: str = "direct_dialog"
    execution_id: str | None = None
    task_id: str | None = None
    message_id: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "mode": "direct_dialog",
            "status": self.status,
            "activeAgentId": self.agent_id,
            "activeAgentName": self.agent_name,
            "goal": self.goal,
            "source": self.source,
        }
        if self.execution_id:
            data["executionId"] = self.execution_id
        if self.task_id:
            data["taskId"] = self.task_id
        return data


class GroupDialogStateService:
    """从最近消息 metadata 中恢复当前群聊焦点。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def latest_active(self, session_id: str) -> GroupDialogState | None:
        rows = await self.db.execute(
            select(DBMessage)
            .where(DBMessage.session_id == session_id)
            .order_by(DBMessage.created_at.desc(), DBMessage.id.desc())
            .limit(40)
        )
        for message in rows.scalars().all():
            metadata = _loads_metadata(message.metadata_json)
            dialog = metadata.get("groupDialog")
            if not isinstance(dialog, dict):
                continue
            status = str(dialog.get("status") or "")
            if status in {"closed", "handoff_confirmed", "cancelled"}:
                return None
            if status not in ACTIVE_DIALOG_STATUSES:
                continue
            agent_id = str(dialog.get("activeAgentId") or "")
            agent_name = str(dialog.get("activeAgentName") or "")
            if not agent_id or not agent_name:
                continue
            return GroupDialogState(
                session_id=session_id,
                agent_id=agent_id,
                agent_name=agent_name,
                status=status,
                goal=str(dialog.get("goal") or ""),
                source=str(dialog.get("source") or "direct_dialog"),
                execution_id=_optional_str(dialog.get("executionId")),
                task_id=_optional_str(dialog.get("taskId")),
                message_id=message.id,
            )
        return None

    async def active_agent(self, session_id: str) -> AgentConfig | None:
        state = await self.latest_active(session_id)
        if not state:
            return None
        agent = await self.db.get(AgentConfig, state.agent_id)
        if not agent or not agent.is_active:
            return None
        return agent

    async def close_active(
        self,
        session: DBSession,
        *,
        reason: str = "user_closed",
    ) -> GroupDialogState | None:
        """写入一条关闭状态消息，让后续无 @ 消息重新回到调度器。"""

        state = await self.latest_active(session.id)
        if state is None:
            return None
        metadata = {
            "groupDialog": {
                **state.to_metadata(),
                "status": "closed",
                "closedReason": reason.strip() or "user_closed",
            },
            "dialogMode": "direct",
            "awaitingUserInput": False,
        }
        self.db.add(DBMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role="system",
            content=f"已结束与 @{state.agent_name} 的直接对齐，后续无 @ 消息将回到项目Leader。",
            content_type="text",
            source_type="system",
            source_name="群聊控制",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ))
        session.updated_at = china_now()
        await self.db.commit()
        return state


def _loads_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
