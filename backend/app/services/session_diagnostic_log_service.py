"""从持久化业务实体聚合会话诊断日志，不依赖消息执行轨迹。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    AgentConfig,
    Artifact,
    Message,
    OrchestratorPlanRecord,
    Run,
    RunProcess,
    RunTask,
    RuntimeLog,
    RuntimeRun,
    Session,
)


class SessionDiagnosticLogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def build(self, session: Session) -> dict[str, Any]:
        agents = await self._agent_names()
        entries: list[dict[str, Any]] = [self._entry(
            entry_id=f"session:{session.id}",
            timestamp=session.created_at,
            level="info",
            category="session",
            source="AgentHub",
            title="会话已创建",
            message=f"{session.title} · {session.mode}",
            details={
                "sessionId": session.id,
                "projectId": session.project_id,
                "mode": session.mode,
                "agentConfigId": session.agent_config_id,
            },
        )]

        runs = list((await self.db.execute(
            select(Run).where(Run.session_id == session.id).order_by(Run.started_at.asc())
        )).scalars().all())
        tasks = list((await self.db.execute(
            select(RunTask).where(RunTask.session_id == session.id).order_by(RunTask.started_at.asc(), RunTask.id.asc())
        )).scalars().all())
        processes = list((await self.db.execute(
            select(RunProcess).where(RunProcess.session_id == session.id).order_by(RunProcess.started_at.asc())
        )).scalars().all())
        messages = list((await self.db.execute(
            select(Message).where(Message.session_id == session.id).order_by(Message.created_at.asc(), Message.id.asc())
        )).scalars().all())
        artifacts = list((await self.db.execute(
            select(Artifact).where(Artifact.session_id == session.id).order_by(Artifact.created_at.asc(), Artifact.id.asc())
        )).scalars().all())
        plans = list((await self.db.execute(
            select(OrchestratorPlanRecord)
            .where(OrchestratorPlanRecord.session_id == session.id)
            .order_by(OrchestratorPlanRecord.created_at.asc(), OrchestratorPlanRecord.id.asc())
        )).scalars().all())
        runtime_runs = list((await self.db.execute(
            select(RuntimeRun).where(RuntimeRun.session_id == session.id).order_by(RuntimeRun.queued_at.asc(), RuntimeRun.id.asc())
        )).scalars().all())
        runtime_run_ids = [run.id for run in runtime_runs]
        runtime_logs = []
        if runtime_run_ids:
            runtime_logs = list((await self.db.execute(
                select(RuntimeLog)
                .where(RuntimeLog.run_id.in_(runtime_run_ids))
                .order_by(RuntimeLog.created_at.asc(), RuntimeLog.sequence.asc())
            )).scalars().all())

        for message in messages:
            metadata = _loads(message.metadata_json)
            error = metadata.get("error")
            actor = message.agent_name or message.source_name or (
                "用户" if message.role == "user" else message.source_type or "AgentHub"
            )
            content = (message.content or "").strip()
            entries.append(self._entry(
                entry_id=f"message:{message.id}",
                timestamp=message.created_at,
                level="error" if error else ("output" if message.role == "assistant" else "input" if message.role == "user" else "debug"),
                category="message",
                source=actor,
                title="Agent 输出" if message.role == "assistant" else "用户输入" if message.role == "user" else "系统消息",
                message=_safe_text(content) if content else "（无可见文本）",
                message_id=message.id,
                agent_id=message.source_id,
                details={
                    "role": message.role,
                    "contentType": message.content_type,
                    "sourceType": message.source_type,
                    "sourceId": message.source_id,
                    "sourceName": message.source_name,
                    "parentMessageId": message.parent_message_id,
                    "pinned": message.is_pinned == "1",
                    "error": error,
                    "runtime": _safe_metadata(metadata),
                },
            ))

        for run in runs:
            entries.append(self._entry(
                entry_id=f"run:{run.id}", timestamp=run.started_at,
                level=_status_level(run.status), category="run", source="Run Scheduler",
                title=f"Run {run.status}", message=f"运行模式 {run.mode}，状态 {run.status}",
                run_id=run.id, message_id=run.current_message_id,
                details={
                    "projectId": run.project_id,
                    "mode": run.mode,
                    "status": run.status,
                    "currentMessageId": run.current_message_id,
                    "updatedAt": _iso(run.updated_at),
                    "completedAt": _iso(run.completed_at),
                    "cancelReason": run.cancel_reason,
                    "metadata": _safe_metadata(_loads(run.metadata_json)),
                },
            ))

        for task in tasks:
            entries.append(self._entry(
                entry_id=f"task:{task.id}", timestamp=task.started_at or _run_time(runs, task.run_id),
                level=_status_level(task.status), category="task",
                source=agents.get(task.agent_id or "", "Scheduler"),
                title=f"Task {task.status}", message=f"{task.name} · {task.role or 'executor'}",
                run_id=task.run_id, task_id=task.id, message_id=task.message_id, agent_id=task.agent_id,
                details={
                    "status": task.status,
                    "phase": task.phase,
                    "dependsOn": _loads_list(task.depends_on_json),
                    "startedAt": _iso(task.started_at),
                    "completedAt": _iso(task.completed_at),
                    "metadata": _safe_metadata(_loads(task.metadata_json)),
                },
            ))

        for process in processes:
            level = "error" if process.exit_code not in (None, 0) else _status_level(process.status)
            entries.append(self._entry(
                entry_id=f"process:{process.id}", timestamp=process.started_at,
                level=level, category="process", source=agents.get(process.agent_id or "", "CLI Runtime"),
                title=f"Process {process.status}",
                message=f"{process.executable or 'CLI'} · exit={process.exit_code if process.exit_code is not None else '-'}",
                run_id=process.run_id, task_id=process.task_id, message_id=process.message_id,
                process_id=process.process_id, agent_id=process.agent_id,
                details={
                    "pid": process.pid,
                    "executable": process.executable,
                    "cwd": process.cwd,
                    "status": process.status,
                    "exitCode": process.exit_code,
                    "completedAt": _iso(process.completed_at),
                },
            ))

        for artifact in artifacts:
            entries.append(self._entry(
                entry_id=f"artifact:{artifact.id}", timestamp=artifact.created_at,
                level=_status_level(artifact.status), category="artifact", source="Artifact Bridge",
                title=f"Artifact {artifact.status}", message=f"{artifact.title or artifact.type} · v{artifact.version}",
                message_id=artifact.message_id, task_id=artifact.task_id,
                details={
                    "artifactId": artifact.id,
                    "type": artifact.type,
                    "status": artifact.status,
                    "filePath": artifact.file_path,
                    "source": artifact.source,
                    "previewId": artifact.preview_id,
                },
            ))

        for plan in plans:
            entries.append(self._entry(
                entry_id=f"plan:{plan.id}", timestamp=plan.created_at,
                level=_status_level(plan.status), category="orchestrator", source="Orchestrator",
                title=f"Plan {plan.status}", message=f"计划 {plan.id} · 当前节点 {plan.current_step_id or '-'}",
                run_id=plan.run_id, agent_id=plan.orchestrator_agent_id,
                details={
                    "planId": plan.id,
                    "executionId": plan.execution_id,
                    "status": plan.status,
                    "currentStepId": plan.current_step_id,
                    "agentScope": _loads_list(plan.agent_scope_json),
                    "updatedAt": _iso(plan.updated_at),
                },
            ))

        for runtime_run in runtime_runs:
            entries.append(self._entry(
                entry_id=f"runtime:{runtime_run.id}", timestamp=runtime_run.started_at or runtime_run.queued_at,
                level=_status_level(runtime_run.status), category="runtime",
                source=agents.get(runtime_run.agent_id, "Cloud Runtime"),
                title=f"Runtime {runtime_run.status}", message=f"{runtime_run.runtime_mode} · {runtime_run.status}",
                run_id=runtime_run.id, agent_id=runtime_run.agent_id,
                details={
                    "sandboxId": runtime_run.sandbox_id,
                    "queuedAt": _iso(runtime_run.queued_at),
                    "finishedAt": _iso(runtime_run.finished_at),
                    "syncCompletedAt": _iso(runtime_run.sync_completed_at),
                    "errorSummary": _safe_text(runtime_run.error_summary or "") or None,
                },
            ))

        for log in runtime_logs:
            entries.append(self._entry(
                entry_id=f"runtime-log:{log.id}", timestamp=log.created_at,
                level="error" if log.stream == "stderr" else "debug",
                category="stdio", source=log.stream,
                title=f"{log.stream} #{log.sequence}", message=_safe_text(log.text),
                run_id=log.run_id,
                details={"sequence": log.sequence, "stream": log.stream},
            ))

        entries.sort(key=lambda item: (item["timestamp"], item["id"]))
        return {
            "session": {
                "id": session.id,
                "title": session.title,
                "mode": session.mode,
                "projectId": session.project_id,
                "createdAt": _iso(session.created_at),
                "updatedAt": _iso(session.updated_at),
            },
            "generatedAt": datetime.now().astimezone().isoformat(),
            "counts": {
                "entries": len(entries),
                "messages": len(messages),
                "runs": len(runs),
                "tasks": len(tasks),
                "processes": len(processes),
                "artifacts": len(artifacts),
                "plans": len(plans),
            },
            "entries": entries,
        }

    async def _agent_names(self) -> dict[str, str]:
        result = await self.db.execute(select(AgentConfig.id, AgentConfig.name))
        return {str(agent_id): str(name) for agent_id, name in result.all()}

    @staticmethod
    def _entry(
        *, entry_id: str, timestamp: datetime | None, level: str, category: str,
        source: str, title: str, message: str, details: dict[str, Any],
        run_id: str | None = None, task_id: str | None = None,
        process_id: str | None = None, message_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": entry_id,
            "timestamp": _iso(timestamp) or "",
            "level": level,
            "category": category,
            "source": source,
            "title": title,
            "message": message,
            "runId": run_id,
            "taskId": task_id,
            "processId": process_id,
            "messageId": message_id,
            "agentId": agent_id,
            "details": details,
        }


def _loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _loads_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _safe_metadata(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in ("secret", "token", "password", "api_key", "apikey", "cookie", "authorization")):
        return "[已脱敏]"
    if key in {"executionTrace", "orchestratorExecution"}:
        return "[由独立诊断日志替代]"
    if isinstance(value, dict):
        return {str(k): _safe_metadata(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_metadata(item) for item in value[:100]]
    if isinstance(value, str):
        value = _safe_text(value)
        if len(value) > 4000:
            return value[:4000] + "…"
    return value


def _safe_text(value: str) -> str:
    """保留排障上下文，同时遮蔽日志中常见的凭据形式。"""
    redacted = re.sub(
        r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|(?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+",
        r"\1[已脱敏]",
        value,
    )
    redacted = re.sub(
        r"\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,})\b",
        "[已脱敏]",
        redacted,
    )
    return redacted


def _status_level(status: str | None) -> str:
    clean = str(status or "").lower()
    if clean in {"failed", "error", "timed_out"}:
        return "error"
    if clean in {"cancelled", "cancelling", "interrupted", "paused", "blocked", "rejected"}:
        return "warning"
    if clean in {"completed", "accepted", "ready", "approved"}:
        return "success"
    if clean in {"running", "submitted", "reviewing", "active"}:
        return "info"
    return "debug"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _run_time(runs: list[Run], run_id: str) -> datetime | None:
    return next((run.started_at for run in runs if run.id == run_id), None)
