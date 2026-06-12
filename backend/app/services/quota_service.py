"""Phase 10 云端 runtime 配额服务。"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.timezone import china_now
from ..event_bus.event_types import EventType
from ..models import QuotaUsage, RuntimeLog, RuntimeRun, Sandbox, Session as DBSession, User, Workspace
from .phase10_schemas import QuotaSummaryRead


ACTIVE_RUNTIME_STATUSES = {"queued", "running", "waiting_input", "syncing", "cancelling"}
ACTIVE_SANDBOX_STATUSES = {"creating", "provisioning", "ready", "running", "syncing", "stopping"}


class QuotaExceededError(RuntimeError):
    pass


class QuotaService:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus

    async def assert_can_start(self, actor: User) -> None:
        await self.reap_stale_active_runs(actor)
        used = await self.active_runtime_count(actor)
        limit = self.concurrent_runs_limit
        if used >= limit:
            await self._publish(EventType.QUOTA_EXCEEDED, {
                "subjectType": "user",
                "subjectId": actor.id,
                "quotaType": "concurrent_runs",
                "used": used,
                "limit": limit,
            })
            raise QuotaExceededError("cloud runtime concurrent quota exceeded")

    async def active_runtime_count(self, actor: User) -> int:
        result = await self.db.execute(
            select(func.count(RuntimeRun.id))
            .join(DBSession, DBSession.id == RuntimeRun.session_id)
            .where(RuntimeRun.runtime_mode == "cloud")
            .where(RuntimeRun.status.in_(ACTIVE_RUNTIME_STATUSES))
            .where(RuntimeRun.actor_user_id == actor.id)
        )
        return int(result.scalar_one() or 0)

    async def active_sandbox_count(self, actor: User) -> int:
        result = await self.db.execute(
            select(func.count(Sandbox.id))
            .join(Workspace, Workspace.id == Sandbox.workspace_id)
            .where(Sandbox.status.in_(ACTIVE_SANDBOX_STATUSES))
            .where(Sandbox.actor_user_id == actor.id)
        )
        return int(result.scalar_one() or 0)

    async def reap_stale_active_runs(self, actor: User) -> int:
        """释放已经失去请求上下文的 active run，避免僵尸状态占用配额。"""
        now = china_now()
        cutoff = now - timedelta(seconds=self.runtime_seconds_limit + 30)
        prestart_cutoff = now - timedelta(seconds=self.prestart_seconds_limit)
        orphan_result = await self.db.execute(
            select(RuntimeRun)
            .outerjoin(DBSession, DBSession.id == RuntimeRun.session_id)
            .where(RuntimeRun.runtime_mode == "cloud")
            .where(RuntimeRun.status.in_(ACTIVE_RUNTIME_STATUSES))
            .where(DBSession.id.is_(None))
        )
        stale_result = await self.db.execute(
            select(RuntimeRun)
            .join(DBSession, DBSession.id == RuntimeRun.session_id)
            .where(RuntimeRun.runtime_mode == "cloud")
            .where(RuntimeRun.status.in_(ACTIVE_RUNTIME_STATUSES))
            .where(RuntimeRun.actor_user_id == actor.id)
            .where(
                or_(
                    RuntimeRun.started_at.is_not(None) & (RuntimeRun.started_at < cutoff),
                    RuntimeRun.started_at.is_(None) & (RuntimeRun.queued_at < cutoff),
                )
            )
        )
        process_started_exists = (
            select(RuntimeLog.id)
            .where(RuntimeLog.run_id == RuntimeRun.id)
            .where(RuntimeLog.stream == "system")
            .where(RuntimeLog.text.like("process % started"))
            .exists()
        )
        prestart_result = await self.db.execute(
            select(RuntimeRun)
            .join(DBSession, DBSession.id == RuntimeRun.session_id)
            .where(RuntimeRun.runtime_mode == "cloud")
            .where(RuntimeRun.status.in_(ACTIVE_RUNTIME_STATUSES))
            .where(RuntimeRun.actor_user_id == actor.id)
            .where(RuntimeRun.started_at.is_not(None))
            .where(RuntimeRun.started_at < prestart_cutoff)
            .where(~process_started_exists)
        )
        prestart_runs = prestart_result.scalars().all()
        prestart_ids = {runtime_run.id for runtime_run in prestart_runs}
        runs_by_id = {
            runtime_run.id: runtime_run
            for runtime_run in [
                *orphan_result.scalars().all(),
                *stale_result.scalars().all(),
                *prestart_runs,
            ]
        }
        runs = list(runs_by_id.values())
        if not runs:
            return 0
        changed = 0
        for runtime_run in runs:
            runtime_run.status = "timed_out"
            runtime_run.finished_at = runtime_run.finished_at or now
            runtime_run.error_summary = runtime_run.error_summary or (
                "云端运行在 CLI 进程启动前断开或长时间无进展，系统自动释放并发配额。"
                if runtime_run.id in prestart_ids
                else "云端运行状态已过期，系统自动释放并发配额。"
            )
            if runtime_run.sandbox_id:
                sandbox = await self.db.get(Sandbox, runtime_run.sandbox_id)
                if sandbox and sandbox.status in ACTIVE_SANDBOX_STATUSES:
                    sandbox.status = "disposed"
                    sandbox.updated_at = now
                    sandbox.stopped_at = sandbox.stopped_at or now
                    sandbox.disposed_at = sandbox.disposed_at or now
            changed += 1
        await self.db.commit()
        return changed

    async def summary(self, actor: User) -> QuotaSummaryRead:
        return QuotaSummaryRead(
            subject_type="user",
            subject_id=actor.id,
            concurrent_runs_limit=self.concurrent_runs_limit,
            concurrent_runs_used=await self.active_runtime_count(actor),
            runtime_seconds_limit=self.runtime_seconds_limit,
            memory_mb_limit=self.memory_mb_limit,
            disk_mb_limit=self.disk_mb_limit,
            network=_network_policy_label(),
        )

    async def record_runtime_seconds(self, actor: User, seconds: int) -> None:
        await self._record_usage(
            subject_type="user",
            subject_id=actor.id,
            quota_type="runtime_seconds",
            used=max(0, int(seconds)),
            limit_value=self.runtime_seconds_limit,
        )

    def resource_limits(self) -> dict[str, int | str]:
        return {
            "cpuSeconds": self.runtime_seconds_limit,
            "memoryMb": self.memory_mb_limit,
            "diskMb": self.disk_mb_limit,
            "network": _network_policy_label(),
        }

    @property
    def concurrent_runs_limit(self) -> int:
        return max(1, int(settings.agenthub_cloud_concurrent_runs or 1))

    @property
    def runtime_seconds_limit(self) -> int:
        return max(5, int(settings.agenthub_cloud_runtime_seconds or 180))

    @property
    def prestart_seconds_limit(self) -> int:
        return max(30, min(120, self.runtime_seconds_limit // 6))

    @property
    def memory_mb_limit(self) -> int:
        return max(128, int(settings.agenthub_cloud_memory_mb or 1024))

    @property
    def disk_mb_limit(self) -> int:
        return max(64, int(settings.agenthub_cloud_disk_mb or 512))

    async def _record_usage(
        self,
        *,
        subject_type: str,
        subject_id: str,
        quota_type: str,
        used: int,
        limit_value: int,
    ) -> None:
        usage = QuotaUsage(
            id=str(uuid.uuid4()),
            subject_type=subject_type,
            subject_id=subject_id,
            quota_type=quota_type,
            used=used,
            limit_value=limit_value,
            window_started_at=china_now(),
        )
        self.db.add(usage)
        await self.db.commit()

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if not self.event_bus:
            return
        await self.event_bus.publish(event_type, payload)

def resource_limits_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)


def parse_resource_limits(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _network_policy_label() -> str:
    value = (settings.agenthub_runner_network_policy or "").strip().lower()
    return "bridge" if value == "bridge" else "none"
