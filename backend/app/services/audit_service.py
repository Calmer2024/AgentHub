"""Phase 9 审计日志服务。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..event_bus.event_types import EventType
from ..models import AuditLog, Project
from .phase9_schemas import AuditLogRead


class AuditService:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus

    async def record(
        self,
        *,
        actor_user_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str,
        team_id: str | None = None,
        project_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        log = AuditLog(
            id=str(uuid.uuid4()),
            actor_user_id=actor_user_id,
            team_id=team_id,
            project_id=project_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        self.db.add(log)
        await self.db.flush()
        await self._publish(EventType.AUDIT_RECORDED, {
            "actorId": actor_user_id,
            "action": action,
            "resourceType": resource_type,
            "resourceId": resource_id,
        })
        return log

    async def list_logs(
        self,
        *,
        project_id: str | None = None,
        team_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditLogRead]:
        stmt = select(AuditLog)
        if project_id:
            stmt = stmt.where(AuditLog.project_id == project_id)
        if team_id:
            stmt = stmt.where(AuditLog.team_id == team_id)
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(max(1, min(limit, 200)))
        result = await self.db.execute(stmt)
        return [self._to_read(log) for log in result.scalars().all()]

    async def list_logs_for_scope(
        self,
        scope,
        *,
        limit: int = 100,
    ) -> list[AuditLogRead]:
        project_result = await self.db.execute(
            select(Project.id).where(Project.status != "archived", _visible_project_filter(scope))
        )
        project_ids = [str(item) for item in project_result.scalars().all()]
        filters = [
            (AuditLog.actor_user_id == scope.actor_user_id)
            & AuditLog.project_id.is_(None)
            & AuditLog.team_id.is_(None)
        ]
        if scope.team_ids:
            filters.append(AuditLog.team_id.in_(scope.team_ids))
        if project_ids:
            filters.append(AuditLog.project_id.in_(project_ids))
        stmt = (
            select(AuditLog)
            .where(or_(*filters))
            .order_by(AuditLog.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        result = await self.db.execute(stmt)
        return [self._to_read(log) for log in result.scalars().all()]

    def _to_read(self, log: AuditLog) -> AuditLogRead:
        try:
            metadata = json.loads(log.metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        return AuditLogRead(
            id=log.id,
            actor_user_id=log.actor_user_id,
            team_id=log.team_id,
            project_id=log.project_id,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            metadata=metadata,
            created_at=log.created_at,
        )

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)


def _visible_project_filter(scope):
    filters = [
        (Project.workspace_mode == "cloud")
        & (Project.owner_user_id == scope.personal_project_owner_id)
        & Project.team_id.is_(None),
    ]
    if scope.team_ids:
        filters.append((Project.workspace_mode == "cloud") & Project.team_id.in_(scope.team_ids))
    return or_(*filters)
