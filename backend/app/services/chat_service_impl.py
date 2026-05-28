"""ChatService 实现 —— SSE 流式聊天 + Orchestrator V2 Pipeline + EventBus。

thin coordinator: 组装参数 → 委托 Pipeline → 委托 Executor → 格式化 SSE → 持久化。
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Session as DBSession, Message as DBMessage, AgentConfig, SessionMember
from ..agents.registry import agent_registry
from ..domain.orchestrator_v2 import OrchestratorV2, PipelineRequest
from ..domain.context_manager import ContextManager
from ..services.agent_executor import AgentExecutor
from ..api.ws_manager import manager as ws_manager

logger = logging.getLogger(__name__)


class ChatServiceImpl:
    """聊天服务 —— thin coordinator。

    组装参数 → 委托 OrchestratorV2 Pipeline → 委托 AgentExecutor → 格式化 SSE。
    """

    def __init__(self, db: AsyncSession, event_bus=None):
        self.db = db
        self.event_bus = event_bus
        self._pipeline = OrchestratorV2(
            context_manager=ContextManager(),
            event_bus=event_bus,
        )
        self._executor = AgentExecutor(event_bus=event_bus)

    async def send_message_stream(
        self,
        session_id: str,
        content: str,
        mentions: list[str] | None = None,
        parent_message_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        session = await self.db.get(DBSession, session_id)
        if not session:
            yield self._err("session not found")
            return

        # 持久化用户消息
        user_msg_id = str(uuid.uuid4())
        self.db.add(DBMessage(
            id=user_msg_id, session_id=session_id, role="user",
            content=content, parent_message_id=parent_message_id,
        ))
        await self.db.commit()

        # 取历史消息
        raw = await self.db.execute(
            select(DBMessage).where(DBMessage.session_id == session_id)
            .order_by(DBMessage.created_at.asc()).limit(50)
        )
        history = [
            {"role": m.role, "content": m.content, "id": m.id}
            for m in raw.scalars().all()
        ]

        # 群聊: 通过 Pipeline 决定路由和执行计划
        if session.mode == "group":
            async for ev in self._group_chat(session_id, content, mentions, history, session):
                yield ev
            return

        # 单聊: 直接调用
        async for ev in self._single_chat(session_id, history, session):
            yield ev

    # ---- 单聊 ----

    async def _single_chat(self, session_id, history, session):
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

        assistant_msg_id = str(uuid.uuid4())
        full = ""

        try:
            async for token in adapter.chat_stream(
                messages=history,
                system_prompt=agent_config.system_prompt,
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
            content=full, agent_name=agent_config.name,
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

    async def _group_chat(self, session_id, content, mentions, history, session):
        # 获取群成员
        member_rows = (await self.db.execute(
            select(AgentConfig).join(
                SessionMember, SessionMember.agent_config_id == AgentConfig.id
            ).where(
                SessionMember.session_id == session_id,
                AgentConfig.is_active == True,
            )
        )).scalars().all()
        member_agents = list(member_rows)

        if not member_agents:
            yield self._err("该群聊没有可用的 Agent")
            return

        # === Pipeline: 意图 → 选 Agent → 拆解 → 执行计划 ===
        req = PipelineRequest(
            session_id=session_id,
            content=content,
            mentions=mentions,
            messages=history,
            member_agents=member_agents,
            system_prompt="",
            context_budget=100_000,
        )
        result = await self._pipeline.run(req)

        if not result.agent_calls:
            yield self._err("没有合适的 Agent 处理此请求，请尝试 @ 指定 Agent")
            return

        # SSE: 路由信息
        route_info = [{"id": c.agent.id, "name": c.agent.name} for c in result.agent_calls]
        yield self._sse({"type": "orchestrator.route", "agents": route_info})

        if result.truncated:
            logger.info("会话 %s 触发上下文截断: tokens=%d", session_id, result.total_tokens)

        # === Executor: 调用 Agent ===
        agent_names: dict[str, str] = {c.agent.id: c.agent.name for c in result.agent_calls}
        seen_agents: set[str] = set()
        msg_ids: dict[str, str] = {}
        agent_texts: dict[str, str] = {}

        async for ev in self._executor.execute(result.agent_calls, result.execution_mode):
            # agent.start 事件——前端创建 placeholder 气泡
            if ev.agent_id and ev.agent_id not in seen_agents:
                seen_agents.add(ev.agent_id)
                mid = str(uuid.uuid4())
                msg_ids[ev.agent_id] = mid
                name = ev.agent_name or agent_names.get(ev.agent_id, "")
                yield self._sse({
                    "type": "agent.start", "agentId": ev.agent_id,
                    "agentName": name, "messageId": mid,
                })

            if ev.done:
                mid = msg_ids.get(ev.agent_id, str(uuid.uuid4()))
                name = ev.agent_name or agent_names.get(ev.agent_id, "")
                yield self._sse({
                    "token": "", "agentId": ev.agent_id,
                    "agentName": name, "done": True,
                    "messageId": mid,
                })
                continue

            yield self._sse({
                "token": ev.token, "agentId": ev.agent_id,
                "agentName": ev.agent_name or agent_names.get(ev.agent_id, ""),
                "done": False,
            })
            agent_texts[ev.agent_id] = agent_texts.get(ev.agent_id, "") + ev.token

        # 持久化
        for agent_id, text in agent_texts.items():
            mid = msg_ids.get(agent_id, str(uuid.uuid4()))
            name = agent_names.get(agent_id, "")
            self.db.add(DBMessage(
                id=mid, session_id=session_id, role="assistant",
                content=text, agent_name=name,
            ))
        session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.commit()

        # 生命周期完成
        await self._pipeline.emit_completed(
            session_id, f"{len(result.agent_calls)} agents completed",
        )

    # ---- SSE 格式化 ----

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    @staticmethod
    def _err(msg: str) -> str:
        return f"data: {json.dumps({'token': '', 'done': True, 'error': msg}, ensure_ascii=False)}\n\n"
