"""群聊收尾：中枢总结、消息持久化、完成事件。"""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.execution_planner import AgentCall
from ..models import Message as DBMessage
from .orchestrator_summarizer import (
    OrchestratorSummarizer,
    ORCHESTRATOR_SOURCE_ID,
    ORCHESTRATOR_SOURCE_NAME,
    SUMMARY_CONTENT_TYPE,
)


class GroupChatFinalizer:
    """处理 Agent 全部结束后的最终阶段。"""

    def __init__(self, db: AsyncSession, pipeline):
        self.db = db
        self._pipeline = pipeline
        self._summarizer = OrchestratorSummarizer()

    async def finish(
        self, session_id, session, result, agent_names: dict[str, str],
        agent_calls: dict[str, AgentCall], msg_ids: dict[str, str],
        agent_texts: dict[str, str], agent_errors: dict[str, str],
        agent_traces: dict[str, list[dict]] | None = None,
    ) -> AsyncIterator[str]:
        agent_traces = agent_traces or {}
        if not agent_texts:
            yield self._all_failed(agent_names, agent_errors)
        elif self._should_generate_summary(result, agent_texts):
            async for item in self._summarize_and_persist(
                session_id, session, result, agent_names, agent_calls,
                msg_ids, agent_texts, agent_errors, agent_traces,
            ):
                yield item
        else:
            self._add_agent_messages(
                session_id, agent_names, agent_calls, msg_ids, agent_texts,
                agent_errors, agent_traces,
            )
            session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await self.db.commit()

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

    async def _summarize_and_persist(
        self, session_id, session, result, agent_names, agent_calls,
        msg_ids, agent_texts, agent_errors, agent_traces,
    ):
        summary_id = str(uuid.uuid4())
        summary = ""
        yield self._summary_started(summary_id, result, list(agent_texts))
        async for token in self._summarizer.stream_summary(
            self._last_user_content(result.assembled_messages),
            result.plan_summary,
            agent_texts,
            agent_calls,
        ):
            summary += token
            yield self._summary_delta(summary_id, token)
        yield self._summary_completed(summary_id)

        self._add_agent_messages(
            session_id, agent_names, agent_calls, msg_ids, agent_texts,
            agent_errors, agent_traces,
        )
        self._add_summary_message(session_id, summary_id, summary, result, agent_texts)
        session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.commit()

    def _add_agent_messages(
        self, session_id, agent_names, agent_calls, msg_ids, agent_texts,
        agent_errors=None, agent_traces=None,
    ):
        agent_errors = agent_errors or {}
        agent_traces = agent_traces or {}
        for key, text in agent_texts.items():
            call = agent_calls.get(key)
            trace_items = list(agent_traces.get(key) or [])
            self.db.add(DBMessage(
                id=msg_ids.get(key, str(uuid.uuid4())),
                session_id=session_id,
                role="assistant",
                content=text,
                content_type="text",
                agent_name=agent_names.get(key, ""),
                source_type="agent",
                source_id=call.agent.id if call else None,
                source_name=agent_names.get(key, ""),
                metadata_json=json.dumps({
                    "task": call.task if call else None,
                    "role": call.role if call else None,
                    "phase": call.phase if call else None,
                    "executionTrace": {
                        "status": "error" if agent_errors.get(key) else "completed",
                        "agentName": agent_names.get(key, ""),
                        "cliTool": getattr(call.agent, "cli_tool", None) if call else None,
                        "workspacePath": None,
                        "startedAt": trace_items[0].get("timestamp") if trace_items else None,
                        "completedAt": trace_items[-1].get("timestamp") if trace_items else None,
                        "processId": _first_process_id(trace_items),
                        "exitCode": _last_exit_code(trace_items),
                        "items": trace_items[-300:],
                    } if trace_items else None,
                }, ensure_ascii=False),
            ))

    def _add_summary_message(self, session_id, summary_id, summary, result, agent_texts):
        model_config = self._summarizer.current_model_config()
        self.db.add(DBMessage(
            id=summary_id,
            session_id=session_id,
            role="assistant",
            content=summary,
            content_type=SUMMARY_CONTENT_TYPE,
            agent_name=None,
            source_type="orchestrator",
            source_id=ORCHESTRATOR_SOURCE_ID,
            source_name=ORCHESTRATOR_SOURCE_NAME,
            metadata_json=json.dumps({
                "intent": result.intent,
                "plan_summary": result.plan_summary,
                "summary_of": list(agent_texts),
                "phases_completed": len(result.dag_phases) if result.dag_phases else None,
                "system_model_provider": model_config["system_model_provider"],
                "system_model": model_config["system_model"],
            }, ensure_ascii=False),
        ))

    def _all_failed(self, agent_names, agent_errors) -> str:
        detail = "; ".join(f"{agent_names.get(k, k)}: {e}" for k, e in agent_errors.items())
        return self._sse({
            "type": "error",
            "error": f"所有 Agent 均无法响应: {detail}" if detail else "所有 Agent 均无法响应",
            "done": True,
        })

    @staticmethod
    def _should_generate_summary(result, agent_texts: dict[str, str]) -> bool:
        return result.execution_mode in {"dag", "chain"} and len(agent_texts) >= 2

    def _summary_started(self, message_id: str, result, summary_of: list[str]) -> str:
        model_config = self._summarizer.current_model_config()
        return self._sse({
            "type": "orchestrator.summary_started",
            "messageId": message_id,
            "sourceType": "orchestrator",
            "sourceId": ORCHESTRATOR_SOURCE_ID,
            "sourceName": ORCHESTRATOR_SOURCE_NAME,
            "contentType": SUMMARY_CONTENT_TYPE,
            "metadata": {
                "intent": result.intent,
                "plan_summary": result.plan_summary,
                "summary_of": summary_of,
                "system_model_provider": model_config["system_model_provider"],
                "system_model": model_config["system_model"],
            },
        })

    def _summary_delta(self, message_id: str, token: str) -> str:
        return self._sse({
            "type": "orchestrator.summary_delta",
            "messageId": message_id,
            "token": token,
            "done": False,
            "sourceType": "orchestrator",
            "sourceName": ORCHESTRATOR_SOURCE_NAME,
            "contentType": SUMMARY_CONTENT_TYPE,
        })

    def _summary_completed(self, message_id: str) -> str:
        return self._sse({
            "type": "orchestrator.summary_completed",
            "messageId": message_id,
            "done": True,
            "sourceType": "orchestrator",
            "sourceName": ORCHESTRATOR_SOURCE_NAME,
            "contentType": SUMMARY_CONTENT_TYPE,
        })

    @staticmethod
    def _last_user_content(messages: list[dict]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return str(msg.get("content", ""))
        return ""

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
