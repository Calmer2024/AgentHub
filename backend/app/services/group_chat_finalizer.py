"""群聊收尾：Agent 消息持久化、产物扫描、完成事件。"""

import json
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..domain.execution_planner import AgentCall
from ..models import Message as DBMessage
from .artifact_output_bridge import ArtifactOutputBridge, artifact_to_event_payload
from .session_service import SessionService


class GroupChatFinalizer:
    """处理 Agent 全部结束后的最终阶段。"""

    def __init__(self, db: AsyncSession, pipeline, event_bus=None):
        self.db = db
        self._pipeline = pipeline
        self.event_bus = event_bus

    async def finish(
        self, session_id, session, result, agent_names: dict[str, str],
        agent_calls: dict[str, AgentCall], msg_ids: dict[str, str],
        agent_texts: dict[str, str], agent_errors: dict[str, str],
        agent_traces: dict[str, list[dict]] | None = None,
        persisted_keys: set[str] | None = None,
        agent_metadata: dict[str, dict] | None = None,
    ) -> AsyncIterator[str]:
        agent_traces = agent_traces or {}
        persisted_keys = persisted_keys or set()
        agent_metadata = agent_metadata or {}
        remaining_texts = {
            key: text for key, text in agent_texts.items()
            if key not in persisted_keys
        }
        if not agent_texts:
            yield self._all_failed(agent_names, agent_errors)
        elif remaining_texts:
            created_ids = self._add_agent_messages(
                session_id, agent_names, agent_calls, msg_ids, remaining_texts,
                agent_errors, agent_traces, agent_metadata,
            )
            session.updated_at = china_now()
            SessionService.increment_unread(session, len(created_ids))
            await self.db.commit()
            async for item in self._scan_agent_messages(session, created_ids):
                yield item

        completed_count = len(agent_texts)
        yield self._sse({
            "type": "orchestrator.task_completed",
            "summary": f"{completed_count} agents completed",
            "total_tokens": sum(len(t) for t in agent_texts.values()),
            "phases_completed": len(result.dag_phases) if result.dag_phases else None,
        })
        await self._pipeline.emit_completed(
            session_id,
            f"{completed_count} agents completed" if completed_count else "全部失败",
        )

    async def persist_one(
        self,
        *,
        session_id: str,
        session,
        key: str,
        agent_names: dict[str, str],
        agent_calls: dict[str, AgentCall],
        msg_ids: dict[str, str],
        text: str,
        error: str | None,
        trace_items: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> AsyncIterator[str]:
        """单个 Agent 完成后立即落库，降低中断造成的可见消息丢失。"""
        message_id = msg_ids.get(key)
        if not message_id or not text:
            return
        if await self.db.get(DBMessage, message_id):
            return
        created_ids = self._add_agent_messages(
            session_id,
            agent_names,
            agent_calls,
            msg_ids,
            {key: text},
            {key: error} if error else {},
            {key: trace_items or []},
            {key: metadata or {}},
        )
        session.updated_at = china_now()
        SessionService.increment_unread(session, len(created_ids))
        await self.db.commit()
        async for item in self._scan_agent_messages(session, created_ids):
            yield item

    def _add_agent_messages(
        self, session_id, agent_names, agent_calls, msg_ids, agent_texts,
        agent_errors=None, agent_traces=None, agent_metadata=None,
    ) -> list[str]:
        agent_errors = agent_errors or {}
        agent_traces = agent_traces or {}
        agent_metadata = agent_metadata or {}
        created_ids: list[str] = []
        for key, text in agent_texts.items():
            call = agent_calls.get(key)
            trace_items = list(agent_traces.get(key) or [])
            runtime_metadata = {
                name: value
                for name, value in dict(agent_metadata.get(key) or {}).items()
                if name != "trace" and value is not None
            }
            message_id = msg_ids.get(key, str(uuid.uuid4()))
            created_ids.append(message_id)
            message_metadata = {
                **runtime_metadata,
                "task": call.task if call else None,
                "role": call.role if call else None,
                "phase": call.phase if call else None,
                "executionTrace": {
                    "status": "error" if agent_errors.get(key) else "completed",
                    "agentName": agent_names.get(key, ""),
                    "cliTool": getattr(call.agent, "cli_tool", None) if call else None,
                    "workspacePath": runtime_metadata.get("workspacePath"),
                    "startedAt": trace_items[0].get("timestamp") if trace_items else None,
                    "completedAt": trace_items[-1].get("timestamp") if trace_items else None,
                    "processId": _first_process_id(trace_items) or runtime_metadata.get("processId"),
                    "exitCode": _last_exit_code(trace_items),
                    "totalItemCount": len(trace_items),
                    "truncated": len(trace_items) > 300,
                    "items": trace_items[-300:],
                } if trace_items else None,
            }
            self.db.add(DBMessage(
                id=message_id,
                session_id=session_id,
                role="assistant",
                content=text,
                content_type="text",
                agent_name=agent_names.get(key, ""),
                source_type="agent",
                source_id=call.agent.id if call else None,
                source_name=agent_names.get(key, ""),
                metadata_json=json.dumps(message_metadata, ensure_ascii=False),
            ))
        return created_ids

    async def _scan_agent_messages(self, session, message_ids: list[str]):
        if not getattr(session, "project_id", None):
            return
        bridge = ArtifactOutputBridge(self.db, event_bus=self.event_bus)
        for message_id in message_ids:
            message = await self.db.get(DBMessage, message_id)
            if not message:
                continue
            yield self._sse({
                "type": "artifact.scan.started",
                "sessionId": session.id,
                "messageId": message_id,
                "projectId": session.project_id,
                "agentId": message.source_id,
                "agentName": message.source_name,
                "token": "",
                "done": False,
            })
            try:
                metadata = _message_metadata(message)
                result = await bridge.scan_completed_message(
                    session=session,
                    message=message,
                    workspace_path=str(metadata.get("workspacePath") or "") or None,
                    visible_content=message.content,
                    execution_trace=_message_trace(message),
                    snapshot_id=str(metadata.get("workspaceSnapshotId") or "") or None,
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

    def _all_failed(self, agent_names, agent_errors) -> str:
        detail = "; ".join(f"{agent_names.get(k, k)}: {e}" for k, e in agent_errors.items())
        return self._sse({
            "type": "error",
            "error": f"所有 Agent 均无法响应: {detail}" if detail else "所有 Agent 均无法响应",
            "done": True,
        })

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _first_process_id(items: list[dict]) -> str | None:
    for item in items:
        value = item.get("processId")
        if value:
            return str(value)
    return None


def _last_exit_code(items: list[dict]) -> int | None:
    for item in reversed(items):
        value = item.get("exitCode")
        if isinstance(value, int):
            return value
    return None


def _message_trace(message: DBMessage) -> dict | None:
    metadata = _message_metadata(message)
    trace = metadata.get("executionTrace")
    return trace if isinstance(trace, dict) else None


def _message_metadata(message: DBMessage) -> dict:
    raw = getattr(message, "metadata_json", None)
    if not raw:
        return {}
    try:
        metadata = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return metadata if isinstance(metadata, dict) else {}
