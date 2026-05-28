"""AgentExecutor —— 执行 Agent 调用并流式输出 TokenEvent。

从 chat_service_impl 中提取，职责单一：调用 Agent，不关心 SSE 格式或持久化。
"""

import asyncio
import logging
from typing import AsyncIterator

from ..domain.orchestrator_v2 import AgentCall
from ..infrastructure.stream_merger import StreamMerger
from ..agents.registry import agent_registry

logger = logging.getLogger(__name__)


class TokenEvent:
    """Agent 流式输出的单个事件。"""

    def __init__(self, agent_id: str, agent_name: str, token: str = "",
                 done: bool = False, message_id: str = "", error: str = ""):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.token = token
        self.done = done
        self.message_id = message_id
        self.error = error

    def to_dict(self) -> dict:
        return {
            "agentId": self.agent_id,
            "agentName": self.agent_name,
            "token": self.token,
            "done": self.done,
            "messageId": self.message_id,
            "error": self.error,
        }


class AgentExecutor:
    """Agent 调用执行器。

    支持三种模式:
      - single:   单 Agent 流式调用
      - parallel: 多 Agent 并行调用，token 按到达顺序交错输出
      - chain:    链式调用 (call[0] 产出 → call[1] 输入 → ...)
    """

    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self.merger = StreamMerger()

    async def execute(
        self, calls: list[AgentCall], mode: str
    ) -> AsyncIterator[TokenEvent]:
        if not calls:
            return
        if mode == "chain":
            async for ev in self._execute_chain(calls):
                yield ev
        elif mode == "parallel" and len(calls) > 1:
            async for ev in self._execute_parallel(calls):
                yield ev
        else:
            async for ev in self._execute_single(calls[0]):
                yield ev

    async def _execute_single(self, call: AgentCall) -> AsyncIterator[TokenEvent]:
        agent = call.agent
        msg_id = f"agent-{agent.id}"

        if self.event_bus:
            await self._emit("AGENT_CALL_STARTED", {"agent_name": agent.name, "agent_id": agent.id})

        full = ""
        try:
            adapter = agent_registry.get_adapter(agent.provider)
            if not adapter:
                yield TokenEvent(agent_id=agent.id, agent_name=agent.name,
                                 token=f"[{agent.name} 不可用]", done=True,
                                 message_id=msg_id, error="adapter not found")
                return

            async for token in adapter.chat_stream(
                messages=call.input_messages,
                system_prompt=agent.system_prompt,
                model=agent.model or None,
            ):
                full += token
                yield TokenEvent(agent_id=agent.id, agent_name=agent.name, token=token)
        except Exception as e:
            logger.exception("Agent call failed: %s", agent.name)
            yield TokenEvent(agent_id=agent.id, agent_name=agent.name,
                             token=f"[{agent.name} 错误: {e}]", done=True,
                             message_id=msg_id, error=str(e))
            return

        if self.event_bus:
            await self._emit("AGENT_CALL_COMPLETED", {
                "agent_name": agent.name, "agent_id": agent.id, "status": "ok",
            })

        yield TokenEvent(agent_id=agent.id, agent_name=agent.name,
                         token="", done=True, message_id=msg_id)

    async def _execute_parallel(self, calls: list[AgentCall]) -> AsyncIterator[TokenEvent]:
        gens = [self._execute_single(c) for c in calls[:5]]
        async for ev in self.merger.merge(gens):
            yield ev

    async def _execute_chain(self, calls: list[AgentCall]) -> AsyncIterator[TokenEvent]:
        previous_output = ""
        for i, call in enumerate(calls):
            if i == 0:
                yield TokenEvent(
                    agent_id="", agent_name="orchestrator",
                    token="", done=True,
                    message_id=f"chain-start-{call.agent.id}",
                )
            else:
                call.input_messages = list(call.input_messages)
                call.input_messages.append({
                    "role": "assistant",
                    "content": f"[上一步产出]\n{previous_output[:2000]}",
                })

            full = ""
            async for ev in self._execute_single(call):
                if ev.token and not ev.done:
                    full += ev.token
                yield ev

            previous_output = full

    async def _emit(self, event_name: str, payload: dict):
        try:
            from ..event_bus import EventType
            await self.event_bus.publish(EventType[event_name], payload)
        except Exception:
            pass
