"""ChatService 实现 —— 用户消息入口与 single/group 分发。"""

import json
import uuid
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Session as DBSession, Message as DBMessage
from ..domain.orchestrator_v2 import OrchestratorV2
from ..domain.context_manager import ContextManager
from ..services.agent_executor import AgentExecutor
from ..services.group_chat_stream import GroupChatStream
from .message_service_sqlalchemy import (
    SqlAlchemyMessageService,
    build_reply_reference_metadata,
)
from .run_service import RunService, run_to_read, task_to_read
from .session_service import SessionService
from .single_cli_chat_stream import SingleCliChatStream

class ChatServiceImpl:
    """聊天服务：持久化用户输入，然后委托单聊或群聊流。"""

    def __init__(self, db: AsyncSession, event_bus=None):
        self.db = db
        self.event_bus = event_bus
        self._context_manager = ContextManager()
        self._pipeline = OrchestratorV2(
            context_manager=self._context_manager,
            event_bus=event_bus,
        )
        self._executor = AgentExecutor(event_bus=event_bus)
        self._group_stream = GroupChatStream(db, self._pipeline, self._executor, event_bus=event_bus)
        self._single_stream = SingleCliChatStream(db, self._context_manager, event_bus)
        self._messages = SqlAlchemyMessageService(db, self._context_manager)

    async def send_message_stream(
        self,
        session_id: str,
        content: str,
        mentions: list[str] | None = None,
        parent_message_id: str | None = None,
        chain_config: object = None,  # ChainConfigSchema | None
    ) -> AsyncGenerator[str, None]:
        session = await self.db.get(DBSession, session_id)
        if not session:
            yield self._err("session not found")
            return

        reply_metadata = None
        if parent_message_id:
            parent = await self.db.get(DBMessage, parent_message_id)
            if not parent:
                yield self._err("quoted message not found")
                return
            if parent.session_id != session_id:
                yield self._err("quoted message belongs to another session")
                return
            reply_metadata = build_reply_reference_metadata(parent)

        # 持久化用户消息
        user_msg_id = str(uuid.uuid4())
        SessionService.clear_unread(session)
        self.db.add(DBMessage(
            id=user_msg_id, session_id=session_id, role="user",
            content=content, content_type="text", source_type="user",
            source_name="用户", parent_message_id=parent_message_id,
            metadata_json=json.dumps(reply_metadata, ensure_ascii=False) if reply_metadata else None,
        ))
        await self.db.commit()

        run_service = RunService(self.db, event_bus=self.event_bus)
        run_mode = "orchestrated" if session.mode == "group" else "single"
        approval_required = _approval_requested(content)
        run = await run_service.create_run(
            session,
            mode=run_mode,
            metadata={
                "userMessageId": user_msg_id,
                "requiresHumanApproval": approval_required,
            },
        )
        yield self._sse({
            "type": "run.started",
            "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
            "runId": run.id,
            "sessionId": session_id,
            "mode": run_mode,
            "messageId": None,
            "startedAt": run.started_at.isoformat() if run.started_at else "",
            "token": "",
            "done": False,
        })

        # 取历史消息
        history, pinned_ids = await self._messages.history_for_session(session_id)

        # 群聊: 通过 Pipeline 决定路由和执行计划
        if session.mode == "group":
            async for ev in self._group_chat(
                session_id, content, mentions, history, pinned_ids, session, chain_config,
                run_id=run.id,
                approval_required=approval_required,
            ):
                yield ev
            return

        task = await run_service.create_task(
            run,
            agent_id=session.agent_config_id,
            name="primary",
            role="executor",
            phase=0,
            metadata={
                "requiresHumanApproval": approval_required,
                "approvalTitle": "确认本轮产出",
            },
        )
        yield self._sse({
            "type": "task.status_changed",
            "runId": run.id,
            "taskId": task.id,
            "sessionId": session_id,
            "status": task.status,
            "task": task_to_read(task).model_dump(by_alias=True, mode="json"),
            "token": "",
            "done": False,
        })

        async for ev in self._single_stream.send(
            session_id,
            history,
            pinned_ids,
            session,
            run_id=run.id,
            task_id=task.id,
        ):
            yield ev

    # ---- 群聊 ----

    async def _group_chat(self, session_id, content, mentions, history, pinned_ids, session,
                          chain_config=None, run_id: str | None = None,
                          approval_required: bool = False):
        async for ev in self._group_stream.send(
            session_id, content, mentions, history, pinned_ids, session, chain_config,
            run_id=run_id,
            approval_required=approval_required,
        ):
            yield ev

    # ---- SSE 格式化 ----

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    @staticmethod
    def _err(msg: str) -> str:
        return f"data: {json.dumps({'type': 'error', 'token': '', 'done': True, 'error': msg}, ensure_ascii=False)}\n\n"


def _approval_requested(content: str) -> bool:
    lowered = content.lower()
    markers = (
        "requireshumanapproval",
        "human approval",
        "人工确认",
        "人工审批",
        "需要审批",
        "审批后",
        "确认继续",
        "审核后",
    )
    return any(marker in lowered for marker in markers)
