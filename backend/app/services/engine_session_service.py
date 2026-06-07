"""CLI 适配器底层 Engine 会话持久化服务。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..models import EngineSession


@dataclass(frozen=True)
class EngineSessionInvocation:
    """一次 CLI 调用要使用的底层 Engine 会话模式。"""

    mode: str = "stateless"
    engine_session_id: str | None = None
    row: EngineSession | None = None
    assigned_by_agenthub: bool = False

    @property
    def is_resume(self) -> bool:
        return self.mode == "resume" and bool(self.engine_session_id)


class EngineSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_invocation(
        self,
        *,
        session_id: str,
        agent_config_id: str,
        cli_tool: str,
        workspace_path: str,
        supported: bool,
        caller_assigned_id: bool,
    ) -> EngineSessionInvocation:
        if not supported:
            return EngineSessionInvocation()

        active = await self.get_active(
            session_id=session_id,
            agent_config_id=agent_config_id,
            cli_tool=cli_tool,
            workspace_path=workspace_path,
        )
        if active:
            return EngineSessionInvocation(
                mode="resume",
                engine_session_id=active.engine_session_id,
                row=active,
            )

        if caller_assigned_id:
            return EngineSessionInvocation(
                mode="start",
                engine_session_id=str(uuid.uuid4()),
                assigned_by_agenthub=True,
            )

        return EngineSessionInvocation(mode="start")

    async def get_active(
        self,
        *,
        session_id: str,
        agent_config_id: str,
        cli_tool: str,
        workspace_path: str,
    ) -> EngineSession | None:
        result = await self.db.execute(
            select(EngineSession)
            .where(
                EngineSession.session_id == session_id,
                EngineSession.agent_config_id == agent_config_id,
                EngineSession.cli_tool == cli_tool,
                EngineSession.workspace_path == workspace_path,
                EngineSession.status == "active",
            )
            .order_by(EngineSession.updated_at.desc(), EngineSession.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def remember(
        self,
        *,
        session_id: str,
        agent_config_id: str,
        cli_tool: str,
        workspace_path: str,
        engine_session_id: str,
        metadata: dict | None = None,
    ) -> EngineSession:
        existing = await self.get_active(
            session_id=session_id,
            agent_config_id=agent_config_id,
            cli_tool=cli_tool,
            workspace_path=workspace_path,
        )
        now = china_now()
        if existing:
            existing.engine_session_id = engine_session_id
            existing.updated_at = now
            existing.metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
            await self.db.commit()
            return existing

        row = EngineSession(
            id=str(uuid.uuid4()),
            session_id=session_id,
            agent_config_id=agent_config_id,
            cli_tool=cli_tool,
            workspace_path=workspace_path,
            engine_session_id=engine_session_id,
            status="active",
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        await self.db.commit()
        return row

    async def touch(self, row: EngineSession, metadata: dict | None = None) -> EngineSession:
        row.updated_at = china_now()
        if metadata is not None:
            row.metadata_json = json.dumps(metadata, ensure_ascii=False)
        await self.db.commit()
        return row
