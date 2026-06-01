"""ChatService 实现 —— SSE 流式聊天 + Orchestrator V2 Pipeline + EventBus。

thin coordinator: 组装参数 → 委托 Pipeline → 委托 Executor → 格式化 SSE → 持久化。

Step 2 增强:
  - orchestrator.task_started / task_completed SSE 事件
  - orchestrator.chain_step SSE 事件
  - 全失败兜底: 所有 Agent 均失败时返回全局错误
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
from ..domain.execution_planner import AgentCall
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
        chain_config: object = None,  # ChainConfigSchema | None
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
            async for ev in self._group_chat(
                session_id, content, mentions, history, session, chain_config,
            ):
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

    async def _group_chat(self, session_id, content, mentions, history, session,
                          chain_config=None):
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

        # 链式配置转换
        cc = None
        if chain_config:
            from ..domain.execution_planner import ChainConfig
            cc = ChainConfig(
                chain_name=getattr(chain_config, 'chain_name', None),
                agent_order=getattr(chain_config, 'agent_order', None),
            )

        # === Pipeline: 意图 → 选 Agent → 拆解 → 执行计划 ===
        req = PipelineRequest(
            session_id=session_id,
            content=content,
            mentions=mentions,
            messages=history,
            member_agents=member_agents,
            system_prompt="",
            context_budget=100_000,
            chain_config=cc,
        )
        result = await self._pipeline.run(req)

        if not result.agent_calls:
            yield self._err("没有合适的 Agent 处理此请求，请尝试 @ 指定 Agent")
            return

        # SSE: 路由信息
        route_info = [{"id": c.agent.id, "name": c.agent.name} for c in result.agent_calls]
        yield self._sse({"type": "orchestrator.route", "agents": route_info})

        # SSE: 任务开始事件 (新增)
        yield self._sse({
            "type": "orchestrator.task_started",
            "intent": result.intent,
            "tasks": [
                {"name": c.task, "role": c.role, "agent": c.agent.name,
                 "status": "running"}
                for c in result.agent_calls
            ],
        })

        if result.truncated:
            logger.info("会话 %s 触发上下文截断: tokens=%d", session_id, result.total_tokens)

        # === Executor: 调用 Agent ===
        agent_names: dict[str, str] = {c.agent.id: c.agent.name for c in result.agent_calls}
        seen_agents: set[str] = set()
        msg_ids: dict[str, str] = {}
        agent_texts: dict[str, str] = {}
        agent_errors: dict[str, str] = {}

        async for ev in self._executor.execute(result.agent_calls, result.execution_mode):
            # chain_step 事件 (新增)
            if ev.is_chain_step:
                yield self._sse({
                    "type": "orchestrator.chain_step",
                    "step": ev.metadata.get("step", 0),
                    "agent": ev.agent_name,
                    "role": ev.metadata.get("role", "executor"),
                    "total": ev.metadata.get("total", 0),
                    "status": ev.metadata.get("status", "running"),
                })
                if ev.metadata.get("status") == "interrupted":
                    agent_errors[ev.agent_id] = ev.metadata.get("error", "链式中断")
                continue

            # agent.start 事件
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
                done_event: dict = {
                    "token": ev.token if ev.error else "",  # 保留错误 token 文本
                    "agentId": ev.agent_id,
                    "agentName": name, "done": True,
                    "messageId": mid,
                }
                if ev.error:
                    done_event["error"] = ev.error
                yield self._sse(done_event)
                # 记录错误用于全局回退
                if ev.error:
                    agent_errors[ev.agent_id] = ev.error
                continue

            # 结构化事件透传 (thinking/planning/tool_call)
            if ev.is_structured:
                yield self._sse({
                    "type": ev.event_type,
                    "agentId": ev.agent_id,
                    "agentName": ev.agent_name or agent_names.get(ev.agent_id, ""),
                    "metadata": ev.metadata,
                })
                continue

            yield self._sse({
                "token": ev.token, "agentId": ev.agent_id,
                "agentName": ev.agent_name or agent_names.get(ev.agent_id, ""),
                "done": False,
            })
            agent_texts[ev.agent_id] = agent_texts.get(ev.agent_id, "") + ev.token

        # === 全失败兜底 (新增) ===
        if not agent_texts and agent_errors:
            error_detail = "; ".join(
                f"{agent_names.get(aid, aid)}: {err}"
                for aid, err in agent_errors.items()
            )
            yield self._sse({
                "type": "error",
                "error": f"所有 Agent 均无法响应: {error_detail}",
                "done": True,
            })
        elif not agent_texts and not agent_errors:
            yield self._sse({
                "type": "error",
                "error": "所有 Agent 均无法响应",
                "done": True,
            })
        else:
            # 正常路径: 持久化 + 完成事件
            for agent_id, text in agent_texts.items():
                mid = msg_ids.get(agent_id, str(uuid.uuid4()))
                name = agent_names.get(agent_id, "")
                self.db.add(DBMessage(
                    id=mid, session_id=session_id, role="assistant",
                    content=text, agent_name=name,
                ))
            session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await self.db.commit()

        # 无论成功或失败，始终发送 task_completed
        completed_count = len(agent_texts)
        yield self._sse({
            "type": "orchestrator.task_completed",
            "summary": f"{completed_count} agents completed",
            "total_tokens": sum(len(t) for t in agent_texts.values()),
        })

        await self._pipeline.emit_completed(
            session_id,
            f"{completed_count} agents completed" if completed_count else "全部失败",
        )

    # ---- SSE 格式化 ----

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    @staticmethod
    def _err(msg: str) -> str:
        return f"data: {json.dumps({'token': '', 'done': True, 'error': msg}, ensure_ascii=False)}\n\n"
