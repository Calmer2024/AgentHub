"""群聊单 Agent 直接回合，不生成或延续协作 DAG。"""

from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..domain.agent_call import AgentCall
from ..models import AgentConfig, Message as DBMessage, Session as DBSession
from .artifact_output_bridge import ArtifactOutputBridge, artifact_to_event_payload
from .cli_agent_executor import CliAgentCallRunner
from .cli_session_runtime import current_turn_message, mark_pinned_messages
from .run_service import RunService, run_to_read, task_to_read
from .session_service import SessionService


class GroupDirectTurn:
    def __init__(self, db: AsyncSession, event_bus=None, cli_runner: CliAgentCallRunner | None = None):
        self.db = db
        self.event_bus = event_bus
        self._cli_runner = cli_runner or CliAgentCallRunner(db=self.db, event_bus=self.event_bus)

    async def send(
        self,
        *,
        session: DBSession,
        content: str,
        history: list[dict],
        workspace_path: str,
        agent: AgentConfig,
        run_id: str | None = None,
        pinned_message_ids: list[str] | None = None,
        goal: str = "",
        source: str = "explicit_mention",
    ) -> AsyncGenerator[str, None]:
        message_id = str(uuid.uuid4())
        call_key = f"{agent.id}:0:direct_turn"
        direct_goal = goal or content.strip()
        task_row = None
        if run_id:
            run_service = RunService(self.db, event_bus=self.event_bus)
            run = await run_service.mark_run_status(run_id, "running", current_message_id=message_id)
            yield self._sse({
                "type": "run.status_changed",
                "runId": run.id,
                "sessionId": run.session_id,
                "status": run.status,
                "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
                "token": "",
                "done": False,
            })
            task_row = await run_service.create_task(
                run,
                agent_id=agent.id,
                name="direct turn",
                role="responder",
                phase=0,
                status="running",
                metadata={
                    "routeMode": "direct_turn",
                    "goal": direct_goal,
                },
            )
            yield self._sse({
                "type": "task.status_changed",
                "runId": run.id,
                "taskId": task_row.id,
                "sessionId": run.session_id,
                "status": task_row.status,
                "task": task_to_read(task_row).model_dump(by_alias=True, mode="json"),
                "token": "",
                "done": False,
            })

        yield self._sse({
            "type": "group.direct_turn_started",
            "sessionId": session.id,
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "source": source,
            "token": "",
            "done": False,
        })
        yield self._sse({
            "type": "agent.start",
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "role": "responder",
            "phase": 0,
            "task": "direct turn",
            "callKey": call_key,
            "metadata": {
                "routeMode": "direct_turn",
            },
        })

        visible = ""
        error_text = None
        metadata_extra: dict = {}
        artifact_workspace_path = workspace_path
        trace_items: list[dict] = []
        exit_code: int | None = None
        prompt = self._build_prompt(content, direct_goal)
        call = AgentCall(
            agent=agent,
            task="direct turn",
            role="responder",
            input_messages=[
                *mark_pinned_messages(history, pinned_message_ids),
                current_turn_message(prompt),
            ],
            phase=0,
        )
        async for event in self._cli_runner.execute(
            call,
            session_id=session.id,
            workspace_path=workspace_path,
        ):
            if event.metadata.get("artifactWorkspacePath"):
                artifact_workspace_path = str(event.metadata["artifactWorkspacePath"])
            metadata_extra.update(_message_metadata_from_event(event.metadata))
            trace = event.metadata.get("trace")
            if isinstance(trace, dict):
                trace_items.append(trace)
                yield self._trace_delta(event, message_id, call_key, trace)

            if event.event_type in {
                "agent.process.started",
                "agent.process.completed",
                "agent.process.turn_completed",
                "agent.output",
                "interactive_prompt",
            }:
                if event.event_type in {"agent.process.completed", "agent.process.turn_completed"}:
                    raw_exit = event.metadata.get("exitCode")
                    exit_code = raw_exit if isinstance(raw_exit, int) else exit_code
                yield self._structured_event(event, message_id, call_key)
                continue

            if event.token and not event.done:
                visible += event.token
                yield self._sse({
                    "type": "agent.output",
                    "agentId": agent.id,
                    "agentName": agent.name,
                    "messageId": message_id,
                    "role": "responder",
                    "phase": 0,
                    "task": "direct turn",
                    "callKey": call_key,
                    "chunk": event.token,
                    "chunkType": "text",
                    "token": event.token,
                    "done": False,
                })
                continue

            if event.done:
                if event.error:
                    error_text = event.error or "直接对话执行失败"
                    if event.token:
                        visible += event.token
                break

        if not visible.strip() and error_text:
            visible = f"直接对话执行失败：{error_text}"
        elif not visible.strip():
            visible = "我已收到。"

        if trace_items:
            metadata_extra["executionTrace"] = _execution_trace_metadata(
                agent=agent,
                metadata=metadata_extra,
                trace_items=trace_items,
                status="error" if error_text else "completed",
                exit_code=exit_code,
            )

        await self._persist_message(
            session=session,
            message_id=message_id,
            agent=agent,
            content=visible,
            goal=direct_goal,
            source=source,
            task_id=task_row.id if task_row else None,
            run_id=run_id,
            error=error_text,
            metadata_extra=metadata_extra,
        )
        async for item in self._scan_artifacts(
            session=session,
            message_id=message_id,
            agent=agent,
            process_id=str(metadata_extra.get("processId") or ""),
            workspace_path=artifact_workspace_path,
            visible=visible,
            metadata=metadata_extra,
            snapshot_id=str(metadata_extra.get("workspaceSnapshotId") or "") or None,
        ):
            yield item

        if run_id:
            run_service = RunService(self.db, event_bus=self.event_bus)
            if task_row:
                task = await run_service.mark_task_status(
                    task_row.id,
                    "completed" if not error_text else "failed",
                    message_id=message_id,
                    metadata_patch={
                        "routeMode": "direct_turn",
                        "error": error_text,
                    },
                )
                yield self._sse({
                    "type": "task.status_changed",
                    "runId": run_id,
                    "taskId": task.id,
                    "sessionId": task.session_id,
                    "status": task.status,
                    "task": task_to_read(task).model_dump(by_alias=True, mode="json"),
                    "token": "",
                    "done": False,
                })
            run = await run_service.mark_run_status(
                run_id,
                "completed" if not error_text else "failed",
                current_message_id=message_id,
                reason=error_text,
            )
            yield self._sse({
                "type": "run.status_changed",
                "runId": run.id,
                "sessionId": run.session_id,
                "status": run.status,
                "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
                "token": "",
                "done": False,
            })

        yield self._sse({
            "agentId": agent.id,
            "agentName": agent.name,
            "done": True,
            "messageId": message_id,
            "role": "responder",
            "phase": 0,
            "task": "direct turn",
            "callKey": call_key,
            "token": "",
            "error": error_text or "",
        })
        yield self._sse({
            "done": True,
            "messageId": message_id,
            "token": "",
            "error": error_text or "",
        })

    async def _scan_artifacts(
        self,
        *,
        session: DBSession,
        message_id: str,
        agent: AgentConfig,
        process_id: str,
        workspace_path: str,
        visible: str,
        metadata: dict,
        snapshot_id: str | None,
    ) -> AsyncGenerator[str, None]:
        if not session.project_id:
            return
        message = await self.db.get(DBMessage, message_id)
        if not message:
            return
        yield self._sse({
            "type": "artifact.scan.started",
            "sessionId": session.id,
            "messageId": message_id,
            "projectId": session.project_id,
            "agentId": agent.id,
            "agentName": agent.name,
            "processId": process_id,
            "token": "",
            "done": False,
        })
        try:
            result = await ArtifactOutputBridge(self.db, event_bus=self.event_bus).scan_completed_message(
                session=session,
                message=message,
                workspace_path=workspace_path,
                visible_content=visible,
                raw_output_preview=visible[-4000:],
                execution_trace=metadata.get("executionTrace")
                if isinstance(metadata.get("executionTrace"), dict) else None,
                snapshot_id=snapshot_id,
            )
            for artifact in result.created:
                payload = artifact_to_event_payload(artifact)
                yield self._sse({
                    "type": "artifact.created",
                    "artifact": payload,
                    "artifactId": payload["id"],
                    "sessionId": payload["sessionId"],
                    "messageId": payload["messageId"],
                    "projectId": payload["projectId"],
                    "artifactType": payload["type"],
                    "title": payload["title"],
                    "version": payload["version"],
                    "filePath": payload["filePath"],
                    "source": payload["source"],
                    "token": "",
                    "done": False,
                })
            yield self._sse({
                "type": "artifact.scan.completed",
                "sessionId": session.id,
                "messageId": message_id,
                "projectId": session.project_id,
                "createdCount": len(result.created),
                "candidateCount": len(result.candidates),
                "skippedCount": len(result.skipped),
                "token": "",
                "done": False,
            })
        except Exception as exc:
            yield self._sse({
                "type": "artifact.detection_failed",
                "sessionId": session.id,
                "messageId": message_id,
                "projectId": session.project_id,
                "reason": f"{type(exc).__name__}: {exc}",
                "recoverable": True,
                "token": "",
                "done": False,
            })

    async def _persist_message(
        self,
        *,
        session: DBSession,
        message_id: str,
        agent: AgentConfig,
        content: str,
        goal: str,
        source: str,
        task_id: str | None,
        run_id: str | None,
        error: str | None,
        metadata_extra: dict | None = None,
    ) -> None:
        metadata = {
            **(metadata_extra or {}),
            "isCollaborating": True,
            "agentRole": "responder",
            "taskName": "direct turn",
            "phase": 0,
            "routeMode": "direct_turn",
            "routeSource": source,
            "goal": goal,
        }
        if run_id:
            metadata["runId"] = run_id
            metadata["runStatus"] = "completed" if error is None else "failed"
        if task_id:
            metadata["taskId"] = task_id
        if error:
            metadata["error"] = error
        self.db.add(DBMessage(
            id=message_id,
            session_id=session.id,
            role="assistant",
            content=content,
            content_type="text",
            agent_name=agent.name,
            source_type="agent",
            source_id=agent.id,
            source_name=agent.name,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ))
        session.updated_at = china_now()
        SessionService.increment_unread(session, 1)
        await self.db.commit()

    @staticmethod
    def _build_prompt(content: str, goal: str) -> str:
        return (
            "你正在 AgentHub 群聊里与用户进行直接对话。"
            "当前不是 DAG 任务执行，也不是自动交接流程。\n"
            "只回答本轮明确交给你的问题。不要擅自把任务交给其他 Agent；"
            "不要生成计划 JSON；不要修改 workspace 文件，除非用户明确要求进入产出阶段。\n\n"
            f"当前直接对话目标：{goal or '未声明'}\n\n"
            f"用户本轮消息：\n{content.strip()}"
        )

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    def _structured_event(self, event, message_id: str, call_key: str) -> str:
        metadata = _public_event_metadata(event.metadata)
        base = {
            "type": event.event_type,
            "agentId": event.agent_id,
            "agentName": event.agent_name,
            "messageId": message_id,
            "role": "responder",
            "phase": 0,
            "task": "direct turn",
            "callKey": call_key,
            "metadata": metadata,
        }
        if event.event_type == "agent.output":
            base.update({
                "chunk": metadata.get("chunk", event.token),
                "chunkType": metadata.get("chunkType", "text"),
                "token": event.token,
                "done": False,
                "processId": metadata.get("processId"),
            })
        elif event.event_type == "interactive_prompt":
            base.update({
                "sessionId": metadata.get("sessionId"),
                "processId": metadata.get("processId"),
                "content": metadata.get("content", ""),
                "promptType": metadata.get("promptType", "confirm"),
                "token": "",
                "done": False,
            })
        elif event.event_type.startswith("agent.process."):
            base.update({
                "processId": metadata.get("processId"),
                "exitCode": metadata.get("exitCode"),
                "token": "",
                "done": False,
            })
        return self._sse(base)

    def _trace_delta(self, event, message_id: str, call_key: str, trace: dict) -> str:
        return self._sse({
            "type": "agent.trace.delta",
            "agentId": event.agent_id,
            "agentName": event.agent_name,
            "messageId": message_id,
            "role": "responder",
            "phase": 0,
            "task": "direct turn",
            "callKey": call_key,
            "processId": event.metadata.get("processId"),
            "item": trace,
            "token": "",
            "done": False,
        })


def _message_metadata_from_event(metadata: dict) -> dict:
    keep = {
        "agentType",
        "cliTool",
        "workspacePath",
        "workspaceSnapshotId",
        "processId",
        "engineRuntime",
        "engineSessionPolicy",
        "engineSession",
        "token_count",
    }
    return {key: metadata[key] for key in keep if key in metadata}


def _public_event_metadata(metadata: dict | None) -> dict:
    if not isinstance(metadata, dict):
        return {}
    return {
        key: value
        for key, value in metadata.items()
        if key != "artifactWorkspacePath"
    }


def _execution_trace_metadata(
    *,
    agent: AgentConfig,
    metadata: dict,
    trace_items: list[dict],
    status: str,
    exit_code: int | None,
) -> dict:
    timestamps = [str(item.get("timestamp") or "") for item in trace_items if item.get("timestamp")]
    return {
        "status": status,
        "agentName": agent.name,
        "cliTool": metadata.get("cliTool") or agent.cli_tool,
        "workspacePath": metadata.get("workspacePath"),
        "startedAt": timestamps[0] if timestamps else None,
        "completedAt": timestamps[-1] if timestamps else None,
        "processId": metadata.get("processId"),
        "exitCode": exit_code,
        "totalItemCount": len(trace_items),
        "truncated": len(trace_items) > 300,
        "items": trace_items[-300:],
    }
