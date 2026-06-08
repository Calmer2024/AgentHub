"""群聊直接对话流。

用于“请某个 Agent 出来连续对齐/访谈”的会话型协作，不生成 DAG，
也不触发下游 Agent。自然语言意图由 Orchestrator/当前 Agent 输出结构化动作，
本服务只负责执行已确认的 direct dialog 状态。
"""

from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..domain.execution_planner import AgentCall
from ..models import AgentConfig, Message as DBMessage, Session as DBSession
from .cli_agent_executor import CliAgentCallRunner
from .group_dialog_state import GroupDialogState
from .run_service import RunService, run_to_read, task_to_read
from .session_service import SessionService


class GroupDirectDialog:
    def __init__(self, db: AsyncSession, event_bus=None):
        self.db = db
        self.event_bus = event_bus

    async def send(
        self,
        *,
        session: DBSession,
        content: str,
        history: list[dict],
        workspace_path: str,
        agent: AgentConfig,
        run_id: str | None = None,
        goal: str = "",
        source: str = "direct_dialog",
        execution_id: str | None = None,
        task_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        message_id = str(uuid.uuid4())
        call_key = f"{agent.id}:0:direct_dialog"
        dialog_state = GroupDialogState(
            session_id=session.id,
            agent_id=agent.id,
            agent_name=agent.name,
            status="awaiting_user_input",
            goal=goal or content.strip(),
            source=source,
            execution_id=execution_id,
            task_id=task_id,
        )
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
                name="direct dialog",
                role="interviewer",
                phase=0,
                status="running",
                metadata={
                    "dialogMode": "direct",
                    "awaitingUserInput": True,
                    "goal": dialog_state.goal,
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
            "type": "group.direct_dialog_started",
            "sessionId": session.id,
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "dialog": dialog_state.to_metadata(),
            "token": "",
            "done": False,
        })
        yield self._sse({
            "type": "agent.start",
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "role": "interviewer",
            "phase": 0,
            "task": "direct dialog",
            "callKey": call_key,
            "metadata": {
                "dialogMode": "direct",
                "awaitingUserInput": True,
            },
        })

        visible = ""
        error_text = None
        metadata_extra: dict = {}
        trace_items: list[dict] = []
        exit_code: int | None = None
        prompt = self._build_prompt(content, dialog_state)
        call = AgentCall(
            agent=agent,
            task="direct dialog",
            role="interviewer",
            input_messages=[*history, {"role": "user", "content": prompt}],
            phase=0,
        )
        async for event in CliAgentCallRunner(db=self.db, event_bus=self.event_bus).execute(
            call,
            session_id=session.id,
            workspace_path=workspace_path,
        ):
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
                    "role": "interviewer",
                    "phase": 0,
                    "task": "direct dialog",
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
            visible = "我已收到。你可以继续补充，我会留在当前对话里。"

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
            dialog_state=dialog_state,
            task_id=task_row.id if task_row else None,
            run_id=run_id,
            error=error_text,
            metadata_extra=metadata_extra,
        )
        if run_id:
            run_service = RunService(self.db, event_bus=self.event_bus)
            if task_row:
                task = await run_service.mark_task_status(
                    task_row.id,
                    "paused" if not error_text else "failed",
                    message_id=message_id,
                    metadata_patch={
                        "dialogMode": "direct",
                        "awaitingUserInput": not bool(error_text),
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
                "paused" if not error_text else "failed",
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
            "type": "group.direct_dialog_waiting",
            "sessionId": session.id,
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "dialog": dialog_state.to_metadata(),
            "token": "",
            "done": False,
        })
        yield self._sse({
            "agentId": agent.id,
            "agentName": agent.name,
            "done": True,
            "messageId": message_id,
            "role": "interviewer",
            "phase": 0,
            "task": "direct dialog",
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

    async def _persist_message(
        self,
        *,
        session: DBSession,
        message_id: str,
        agent: AgentConfig,
        content: str,
        dialog_state: GroupDialogState,
        task_id: str | None,
        run_id: str | None,
        error: str | None,
        metadata_extra: dict | None = None,
    ) -> None:
        metadata = {
            **(metadata_extra or {}),
            "isCollaborating": True,
            "agentRole": "interviewer",
            "taskName": "direct dialog",
            "phase": 0,
            "dialogMode": "direct",
            "awaitingUserInput": error is None,
            "groupDialog": dialog_state.to_metadata(),
        }
        if run_id:
            metadata["runId"] = run_id
            metadata["runStatus"] = "paused" if error is None else "failed"
        if task_id:
            metadata["taskId"] = task_id
        if error:
            metadata["error"] = error
            metadata["groupDialog"]["status"] = "error"
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
    def _build_prompt(content: str, state: GroupDialogState) -> str:
        return (
            "你正在 AgentHub 群聊里与用户进行直接对话。"
            "当前不是 DAG 任务执行，也不是自动交接流程。\n"
            "你的职责是围绕当前目标持续澄清、追问、总结，并等待用户确认。"
            "如果信息不足，优先提出少量关键问题；不要擅自把任务交给其他 Agent；"
            "不要生成计划 JSON；不要修改 workspace 文件，除非用户明确要求进入产出阶段。\n\n"
            f"当前直接对话目标：{state.goal or '未声明'}\n\n"
            f"用户本轮消息：\n{content.strip()}"
        )

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    def _structured_event(self, event, message_id: str, call_key: str) -> str:
        metadata = dict(event.metadata or {})
        base = {
            "type": event.event_type,
            "agentId": event.agent_id,
            "agentName": event.agent_name,
            "messageId": message_id,
            "role": "interviewer",
            "phase": 0,
            "task": "direct dialog",
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
            "role": "interviewer",
            "phase": 0,
            "task": "direct dialog",
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
        "items": trace_items[-300:],
    }
