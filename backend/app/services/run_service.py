"""Phase 7A 运行状态与 CLI 进程绑定服务。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.cli_runtime_registry import cli_runtime_registry
from ..core.timezone import china_now
from ..models import Message, Run, RunProcess, RunTask, Session as DBSession
from .runtime_schemas import ProcessRead, RunRead, TaskRead


TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled", "rejected"}


class RunNotFoundError(LookupError):
    pass


class TaskNotFoundError(LookupError):
    pass


class RunService:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus

    async def create_run(
        self,
        session: DBSession,
        *,
        mode: str,
        metadata: dict | None = None,
    ) -> Run:
        now = _utcnow()
        run = Run(
            id=str(uuid.uuid4()),
            session_id=session.id,
            project_id=session.project_id,
            mode=mode,
            status="queued",
            started_at=now,
            updated_at=now,
            metadata_json=_json(metadata or {}),
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def create_task(
        self,
        run: Run,
        *,
        agent_id: str | None,
        name: str,
        role: str | None = None,
        phase: int | None = None,
        depends_on: list[str] | None = None,
        status: str = "pending",
        metadata: dict | None = None,
    ) -> RunTask:
        now = _utcnow()
        task = RunTask(
            id=str(uuid.uuid4()),
            run_id=run.id,
            session_id=run.session_id,
            agent_id=agent_id,
            name=name or "primary",
            role=role,
            phase=phase,
            status=status,
            depends_on_json=_json(depends_on or []),
            started_at=now if status == "running" else None,
            metadata_json=_json(metadata or {}),
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_run(self, run_id: str) -> Run:
        result = await self.db.execute(
            select(Run)
            .where(Run.id == run_id)
            .execution_options(populate_existing=True)
        )
        run = result.scalars().first()
        if not run:
            raise RunNotFoundError(run_id)
        return run

    async def list_runs(self, session_id: str) -> list[RunRead]:
        result = await self.db.execute(
            select(Run)
            .where(Run.session_id == session_id)
            .order_by(Run.started_at.desc(), Run.id.desc())
        )
        return [run_to_read(run) for run in result.scalars().all()]

    async def list_tasks(self, run_id: str) -> list[TaskRead]:
        await self.get_run(run_id)
        result = await self.db.execute(
            select(RunTask)
            .where(RunTask.run_id == run_id)
            .order_by(RunTask.phase.asc(), RunTask.started_at.asc(), RunTask.id.asc())
        )
        return [task_to_read(task) for task in result.scalars().all()]

    async def list_processes(self, run_id: str) -> list[ProcessRead]:
        await self.get_run(run_id)
        result = await self.db.execute(
            select(RunProcess)
            .where(RunProcess.run_id == run_id)
            .order_by(RunProcess.started_at.asc(), RunProcess.id.asc())
        )
        return [process_to_read(process) for process in result.scalars().all()]

    async def mark_run_status(
        self,
        run_id: str,
        status: str,
        *,
        current_message_id: str | None = None,
        reason: str | None = None,
    ) -> Run:
        run = await self.get_run(run_id)
        if run.status in TERMINAL_RUN_STATUSES and run.status != status:
            return run
        now = _utcnow()
        run.status = status
        run.updated_at = now
        if current_message_id:
            run.current_message_id = current_message_id
        if status in TERMINAL_RUN_STATUSES and not run.completed_at:
            run.completed_at = now
        if reason and status == "cancelled":
            run.cancel_reason = reason
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def bind_current_message(self, run_id: str, message_id: str) -> Run:
        return await self.mark_run_status(run_id, "running", current_message_id=message_id)

    async def mark_task_status(
        self,
        task_id: str,
        status: str,
        *,
        message_id: str | None = None,
        metadata_patch: dict | None = None,
    ) -> RunTask:
        task = await self.db.get(RunTask, task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        if task.status in TERMINAL_TASK_STATUSES and task.status != status:
            return task
        now = _utcnow()
        task.status = status
        if status == "running" and not task.started_at:
            task.started_at = now
        if status in TERMINAL_TASK_STATUSES or status == "paused":
            task.completed_at = task.completed_at or now
        if message_id:
            task.message_id = message_id
        if metadata_patch:
            metadata = _loads(task.metadata_json)
            metadata.update(metadata_patch)
            task.metadata_json = _json(metadata)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def bind_process(
        self,
        *,
        run_id: str,
        task_id: str | None,
        session_id: str,
        agent_id: str | None,
        message_id: str | None,
        process_id: str,
        snapshot: dict | None = None,
    ) -> RunProcess:
        snapshot = snapshot or _snapshot_for_process(session_id, process_id)
        process = RunProcess(
            id=str(uuid.uuid4()),
            run_id=run_id,
            task_id=task_id,
            session_id=session_id,
            agent_id=agent_id,
            message_id=message_id,
            process_id=process_id,
            pid=_int_or_none(snapshot.get("pid")),
            executable=_str_or_none(snapshot.get("executable")),
            cwd=_str_or_none(snapshot.get("cwd")),
            status="running",
            started_at=_utcnow(),
        )
        self.db.add(process)
        await self.db.commit()
        await self.db.refresh(process)
        return process

    async def complete_process(
        self,
        process_id: str,
        *,
        exit_code: int | None,
        status: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        message_id: str | None = None,
    ) -> None:
        filters = [RunProcess.process_id == process_id]
        if run_id:
            filters.append(RunProcess.run_id == run_id)
        if task_id:
            filters.append(RunProcess.task_id == task_id)
        if message_id:
            filters.append(RunProcess.message_id == message_id)
        result = await self.db.execute(
            select(RunProcess).where(*filters)
        )
        processes = result.scalars().all()
        now = _utcnow()
        for process in processes:
            if process.status == "cancelled" and status != "cancelled":
                process.exit_code = exit_code
                process.completed_at = process.completed_at or now
                continue
            process.status = status or ("completed" if exit_code in (0, None) else "failed")
            process.exit_code = exit_code
            process.completed_at = process.completed_at or now
        if processes:
            await self.db.commit()

    async def cancel_run(self, run_id: str, reason: str | None = None) -> Run:
        run = await self.get_run(run_id)
        if run.status in TERMINAL_RUN_STATUSES:
            return run

        now = _utcnow()
        run.status = "cancelling"
        run.cancel_reason = reason
        run.updated_at = now
        await self.db.commit()

        result = await self.db.execute(
            select(RunProcess)
            .where(RunProcess.run_id == run.id, RunProcess.status == "running")
        )
        process_rows = result.scalars().all()
        killed = 0
        if process_rows:
            for row in process_rows:
                await cli_runtime_registry.terminate(row.process_id)
                row.status = "cancelled"
                row.completed_at = _utcnow()
                killed += 1
        else:
            killed = await cli_runtime_registry.terminate_session(run.session_id)

        task_result = await self.db.execute(
            select(RunTask)
            .where(RunTask.run_id == run.id, RunTask.status.not_in(list(TERMINAL_TASK_STATUSES)))
        )
        for task in task_result.scalars().all():
            task.status = "cancelled"
            task.completed_at = task.completed_at or _utcnow()

        run.status = "cancelled"
        run.completed_at = run.completed_at or _utcnow()
        run.updated_at = _utcnow()
        await self._merge_message_run_metadata(
            run.current_message_id,
            {"runId": run.id, "runStatus": "cancelled", "cancelReason": reason, "killedProcessCount": killed},
        )
        await self._append_cancel_message(run, reason=reason, killed_process_count=killed)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def interrupt_run(self, run_id: str, reason: str | None = None) -> Run:
        """可恢复中断运行：终止当前进程，但不把 run/task 置为取消终态。"""
        run = await self.get_run(run_id)
        if run.status in TERMINAL_RUN_STATUSES:
            return run

        now = _utcnow()
        run.status = "interrupted"
        run.cancel_reason = reason
        run.updated_at = now
        await self.db.commit()

        result = await self.db.execute(
            select(RunProcess)
            .where(RunProcess.run_id == run.id, RunProcess.status == "running")
        )
        process_rows = result.scalars().all()
        interrupted = 0
        if process_rows:
            for row in process_rows:
                await cli_runtime_registry.terminate(row.process_id)
                row.status = "interrupted"
                row.completed_at = _utcnow()
                interrupted += 1
        else:
            interrupted = await cli_runtime_registry.terminate_session(run.session_id)

        task_result = await self.db.execute(
            select(RunTask)
            .where(RunTask.run_id == run.id, RunTask.status.in_(["running", "cancelling"]))
        )
        for task in task_result.scalars().all():
            task.status = "paused"
            task.completed_at = task.completed_at or _utcnow()

        await self._merge_message_run_metadata(
            run.current_message_id,
            {
                "runId": run.id,
                "runStatus": "interrupted",
                "interruptReason": reason,
                "interruptedProcessCount": interrupted,
            },
        )
        await self._append_interrupt_message(run, reason=reason, interrupted_process_count=interrupted)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def complete_run_from_tasks(self, run_id: str) -> Run:
        result = await self.db.execute(
            select(RunTask).where(RunTask.run_id == run_id)
        )
        tasks = list(result.scalars().all())
        if not tasks:
            return await self.mark_run_status(run_id, "completed")
        if any(task.status == "cancelled" for task in tasks):
            return await self.mark_run_status(run_id, "cancelled")
        if any(task.status == "failed" for task in tasks):
            return await self.mark_run_status(run_id, "failed")
        if any(task.status == "rejected" for task in tasks):
            return await self.mark_run_status(run_id, "completed")
        if any(task.status in {"paused", "pending_review"} for task in tasks):
            return await self.mark_run_status(run_id, "paused")
        if all(task.status in {"completed", "approved"} for task in tasks):
            return await self.mark_run_status(run_id, "completed")
        return await self.mark_run_status(run_id, "running")

    async def _merge_message_run_metadata(self, message_id: str | None, patch: dict) -> None:
        if not message_id:
            return
        message = await self.db.get(Message, message_id)
        if not message:
            return
        metadata = _loads(message.metadata_json)
        metadata.update(patch)
        message.metadata_json = _json(metadata)

    async def _append_cancel_message(
        self,
        run: Run,
        *,
        reason: str | None,
        killed_process_count: int,
    ) -> None:
        detail = f"原因：{reason.strip()}" if reason and reason.strip() else "用户已停止本次运行。"
        self.db.add(Message(
            id=str(uuid.uuid4()),
            session_id=run.session_id,
            role="system",
            content=f"本次运行已中止成功。{detail}",
            content_type="text",
            source_type="system",
            source_name="运行控制",
            metadata_json=_json({
                "runId": run.id,
                "runStatus": "cancelled",
                "cancelReason": reason,
                "killedProcessCount": killed_process_count,
            }),
        ))

    async def _append_interrupt_message(
        self,
        run: Run,
        *,
        reason: str | None,
        interrupted_process_count: int,
    ) -> None:
        detail = f"原因：{reason.strip()}" if reason and reason.strip() else "运行已中断。"
        self.db.add(Message(
            id=str(uuid.uuid4()),
            session_id=run.session_id,
            role="system",
            content=f"本次运行已中断，可从执行面板继续或放弃。{detail}",
            content_type="text",
            source_type="system",
            source_name="运行控制",
            metadata_json=_json({
                "runId": run.id,
                "runStatus": "interrupted",
                "interruptReason": reason,
                "interruptedProcessCount": interrupted_process_count,
            }),
        ))


def run_to_read(run: Run) -> RunRead:
    return RunRead(
        id=run.id,
        session_id=run.session_id,
        project_id=run.project_id,
        mode=run.mode,
        status=run.status,
        current_message_id=run.current_message_id,
        started_at=run.started_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
        cancel_reason=run.cancel_reason,
        metadata=_loads(run.metadata_json) or None,
    )


def task_to_read(task: RunTask) -> TaskRead:
    return TaskRead(
        id=task.id,
        run_id=task.run_id,
        session_id=task.session_id,
        agent_id=task.agent_id,
        message_id=task.message_id,
        name=task.name,
        role=task.role,
        phase=task.phase,
        status=task.status,
        depends_on=_loads_list(task.depends_on_json),
        started_at=task.started_at,
        completed_at=task.completed_at,
        metadata=_loads(task.metadata_json) or None,
    )


def process_to_read(process: RunProcess) -> ProcessRead:
    return ProcessRead(
        id=process.id,
        run_id=process.run_id,
        task_id=process.task_id,
        session_id=process.session_id,
        agent_id=process.agent_id,
        message_id=process.message_id,
        process_id=process.process_id,
        pid=process.pid,
        executable=process.executable,
        cwd=process.cwd,
        status=process.status,
        started_at=process.started_at,
        completed_at=process.completed_at,
        exit_code=process.exit_code,
    )


def _snapshot_for_process(session_id: str, process_id: str) -> dict:
    for snapshot in cli_runtime_registry.active_snapshots(session_id):
        if snapshot.get("processId") == process_id:
            return snapshot
    return {}


def _loads(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _loads_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in data] if isinstance(data, list) else []


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _utcnow():
    return china_now()


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None
