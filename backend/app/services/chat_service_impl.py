"""ChatService 实现 —— SSE 流式聊天 + Orchestrator V2 Pipeline + EventBus。

thin coordinator: 组装参数 → 委托 Pipeline → 委托 Executor → 格式化 SSE → 持久化。

Step 2 增强:
  - orchestrator.task_started / task_completed SSE 事件
  - orchestrator.chain_step SSE 事件
  - 全失败兜底: 所有 Agent 均失败时返回全局错误
"""

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Session as DBSession, Message as DBMessage, AgentConfig
from ..agents.registry import agent_registry
from ..domain.orchestrator_v2 import OrchestratorV2
from ..domain.context_manager import ContextManager, PromptAssemblyInput
from ..services.agent_executor import AgentExecutor
from ..services.group_chat_stream import GroupChatStream
from ..api.ws_manager import manager as ws_manager
from .message_service_sqlalchemy import (
    SqlAlchemyMessageService,
    build_reply_reference_metadata,
)

class ChatServiceImpl:
    """聊天服务 —— thin coordinator。

    组装参数 → 委托 OrchestratorV2 Pipeline → 委托 AgentExecutor → 格式化 SSE。
    """

    def __init__(self, db: AsyncSession, event_bus=None):
        self.db = db
        self.event_bus = event_bus
        self._context_manager = ContextManager()
        self._pipeline = OrchestratorV2(
            context_manager=self._context_manager,
            event_bus=event_bus,
        )
        self._executor = AgentExecutor(event_bus=event_bus)
        self._group_stream = GroupChatStream(db, self._pipeline, self._executor)
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
        self.db.add(DBMessage(
            id=user_msg_id, session_id=session_id, role="user",
            content=content, content_type="text", source_type="user",
            source_name="用户", parent_message_id=parent_message_id,
            metadata_json=json.dumps(reply_metadata, ensure_ascii=False) if reply_metadata else None,
        ))
        await self.db.commit()

        # 取历史消息
        history, pinned_ids = await self._messages.history_for_session(session_id)

        # 群聊: 通过 Pipeline 决定路由和执行计划
        if session.mode == "group":
            async for ev in self._group_chat(
                session_id, content, mentions, history, pinned_ids, session, chain_config,
            ):
                yield ev
            return

        # 单聊: 直接调用
        async for ev in self._single_chat(session_id, history, pinned_ids, session):
            yield ev

    # ---- 单聊 ----

    async def _single_chat(self, session_id, history, pinned_ids, session):
        agent_config = None
        if session.agent_config_id:
            agent_config = await self.db.get(AgentConfig, session.agent_config_id)
        if not agent_config:
            yield self._err("会话未关联 Agent")
            return

        adapter = agent_registry.get_adapter(agent_config.provider)
        if not adapter or not agent_registry.is_available(agent_config.provider):
            yield self._err(f"供应商 {agent_config.provider} 不可用")
            return

        assembled = self._context_manager.assemble(PromptAssemblyInput(
            session_id=session_id,
            system_prompt=agent_config.system_prompt or "",
            messages=history,
            pinned_message_ids=pinned_ids,
            max_tokens=adapter.capability.max_context_tokens,
        ))
        adapter_messages, system_prompt = _split_system_prompt(
            assembled.assembled_messages,
            agent_config.system_prompt or "",
        )

        assistant_msg_id = str(uuid.uuid4())
        full = ""

        try:
            async for token in adapter.chat_stream(
                messages=adapter_messages,
                system_prompt=system_prompt,
                model=agent_config.model or None,
            ):
                full += token
                yield self._sse({"token": token, "done": False})
                await ws_manager.broadcast(session_id, {
                    "type": "token", "token": token, "messageId": assistant_msg_id,
                })
        except Exception as e:
            yield self._err(f"{type(e).__name__}: {e}")
            return

        self.db.add(DBMessage(
            id=assistant_msg_id, session_id=session_id, role="assistant",
            content=full, content_type="text", agent_name=agent_config.name,
            source_type="agent", source_id=agent_config.id,
            source_name=agent_config.name,
        ))
        session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.commit()

        await ws_manager.broadcast(session_id, {
            "type": "message.completed", "messageId": assistant_msg_id,
        })
        yield self._sse({
            "token": "", "done": True,
            "messageId": assistant_msg_id, "agentName": agent_config.name,
        })

    # ---- 群聊 ----

    async def _group_chat(self, session_id, content, mentions, history, pinned_ids, session,
                          chain_config=None):
        async for ev in self._group_stream.send(
            session_id, content, mentions, history, pinned_ids, session, chain_config,
        ):
            yield ev

    # ---- SSE 格式化 ----

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    @staticmethod
    def _err(msg: str) -> str:
        return f"data: {json.dumps({'token': '', 'done': True, 'error': msg}, ensure_ascii=False)}\n\n"


def _split_system_prompt(messages: list[dict], fallback: str) -> tuple[list[dict], str]:
    if messages and messages[0].get("role") == "system":
        return messages[1:], str(messages[0].get("content") or fallback)
    return messages, fallback
