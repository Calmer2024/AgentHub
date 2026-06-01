"""AgentExecutor —— 执行 Agent 调用并流式输出 TokenEvent。

从 chat_service_impl 中提取，职责单一：调用 Agent，不关心 SSE 格式或持久化。

Step 2 增强:
  - TokenEvent 扩展 event_type + metadata 字段
  - 60s 超时保护
  - 链式中断处理
  - 角色 Prompt 注入
"""

import asyncio
import logging
from typing import AsyncIterator

from ..domain.execution_planner import AgentCall
from ..infrastructure.stream_merger import StreamMerger
from ..agents.registry import agent_registry

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SECONDS = 60


class TokenEvent:
    """Agent 流式输出的单个事件。

    扩展字段 (Step 2):
      - event_type: 事件类型 ("thinking" | "planning" | "tool_call" | "token" | "chain_step")
      - metadata: 结构化元数据 (role, step, status, tool_name 等)
    """

    def __init__(self, agent_id: str = "", agent_name: str = "", token: str = "",
                 done: bool = False, message_id: str = "", error: str = "",
                 event_type: str = "token", metadata: dict | None = None):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.token = token
        self.done = done
        self.message_id = message_id
        self.error = error
        self.event_type = event_type
        self.metadata = metadata or {}

    @property
    def is_chain_step(self) -> bool:
        return self.event_type == "chain_step"

    @property
    def is_structured(self) -> bool:
        """非纯 token 的结构化事件 (thinking/planning/tool_call/chain_step)。"""
        return self.event_type != "token"

    def to_dict(self) -> dict:
        d = {
            "agentId": self.agent_id,
            "agentName": self.agent_name,
            "token": self.token,
            "done": self.done,
            "messageId": self.message_id,
            "error": self.error,
        }
        if self.event_type != "token":
            d["eventType"] = self.event_type
        if self.metadata:
            d["metadata"] = self.metadata
        return d


class AgentExecutor:
    """Agent 调用执行器。

    支持三种模式:
      - single:   单 Agent 流式调用 (60s 超时保护)
      - parallel: 多 Agent 并行调用，token 按到达顺序交错输出
      - chain:    链式调用，角色 Prompt 注入 + 中断处理
    """

    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self.merger = StreamMerger()

    async def execute(
        self, calls: list[AgentCall], mode: str
    ) -> AsyncIterator[TokenEvent]:
        """执行 Agent 调用列表，按模式分发。"""
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

    # ---- Single ----

    async def _execute_single(self, call: AgentCall) -> AsyncIterator[TokenEvent]:
        """单 Agent 流式调用，含 60s 超时保护。"""
        agent = call.agent
        msg_id = f"agent-{agent.id}"

        if self.event_bus:
            await self._emit("AGENT_CALL_STARTED", {
                "agent_name": agent.name, "agent_id": agent.id,
            })

        # 角色 Prompt 注入
        system_prompt = agent.system_prompt or ""
        if call.role_prompt_override:
            system_prompt = f"{system_prompt}\n\n{call.role_prompt_override}"

        full = ""
        try:
            adapter = agent_registry.get_adapter(agent.provider)
            if not adapter:
                yield TokenEvent(
                    agent_id=agent.id, agent_name=agent.name,
                    token=f"[{agent.name} 不可用]", done=True,
                    message_id=msg_id, error="adapter not found",
                )
                return

            # 60s 超时保护 (asyncio.timeout 支持 async generator)
            async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
                async for token in adapter.chat_stream(
                    messages=call.input_messages,
                    system_prompt=system_prompt,
                    model=agent.model or None,
                ):
                    full += token
                    yield TokenEvent(agent_id=agent.id, agent_name=agent.name, token=token)

        except TimeoutError:
            logger.warning("Agent timeout: %s (60s)", agent.name)
            yield TokenEvent(
                agent_id=agent.id, agent_name=agent.name,
                token=f"[{agent.name} 响应超时]", done=True,
                message_id=msg_id, error="timeout",
            )
            return

        except Exception as e:
            logger.exception("Agent call failed: %s", agent.name)
            yield TokenEvent(
                agent_id=agent.id, agent_name=agent.name,
                token=f"[{agent.name} 错误: {e}]", done=True,
                message_id=msg_id, error=str(e),
            )
            return

        if self.event_bus:
            await self._emit("AGENT_CALL_COMPLETED", {
                "agent_name": agent.name, "agent_id": agent.id, "status": "ok",
            })

        yield TokenEvent(
            agent_id=agent.id, agent_name=agent.name,
            token="", done=True, message_id=msg_id,
        )

    # ---- Parallel ----

    async def _execute_parallel(self, calls: list[AgentCall]) -> AsyncIterator[TokenEvent]:
        """多 Agent 并行调用，StreamMerger 交错输出。"""
        gens = [self._execute_single(c) for c in calls[:5]]
        async for ev in self.merger.merge(gens):
            yield ev

    # ---- Chain ----

    async def _execute_chain(self, calls: list[AgentCall]) -> AsyncIterator[TokenEvent]:
        """链式调用: call[0] 产出 → call[1] 输入 → ...，含中断处理。

        每步开始时发送 chain_step 事件。
        上一步异常时中断后续步骤，发送中断事件。
        """
        total = len(calls)
        previous_output = ""

        for i, call in enumerate(calls):
            # 发送 chain_step 事件
            yield TokenEvent(
                agent_id=call.agent.id,
                agent_name=call.agent.name,
                event_type="chain_step",
                metadata={
                    "step": i,
                    "agent": call.agent.name,
                    "role": call.role,
                    "total": total,
                    "status": "running",
                },
            )

            # 前一步产出注入到当前步输入
            if i > 0 and previous_output:
                call.input_messages = list(call.input_messages)
                call.input_messages.append({
                    "role": "assistant",
                    "content": f"[上一步 ({calls[i-1].role}) 产出]\n{previous_output[:2000]}",
                })

            # 执行当前步，通过检查产出事件中的 error 字段来检测失败
            # （_execute_single 在内部捕获异常并转为 error TokenEvent，不会传播）
            full = ""
            step_error = None
            async for ev in self._execute_single(call):
                if ev.token and not ev.done:
                    full += ev.token
                # 跟踪错误信息
                if ev.error:
                    step_error = ev.error
                yield ev

            # 步骤失败检测：产出事件带有 error 字段 → 中断后续步骤
            if step_error:
                logger.warning("Chain step %d failed (%s): %s", i, call.agent.name, step_error)
                yield TokenEvent(
                    agent_id=call.agent.id,
                    agent_name=call.agent.name,
                    event_type="chain_step",
                    metadata={
                        "step": i,
                        "agent": call.agent.name,
                        "role": call.role,
                        "total": total,
                        "status": "interrupted",
                        "error": step_error,
                    },
                )
                break  # 中断后续步骤

            previous_output = full

    # ---- EventBus ----

    async def _emit(self, event_name: str, payload: dict):
        """安全发布 EventBus 事件（fire-and-forget）。"""
        try:
            from ..event_bus import EventType
            await self.event_bus.publish(EventType[event_name], payload)
        except Exception:
            pass
