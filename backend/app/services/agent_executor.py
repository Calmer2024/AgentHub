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

from ..domain.execution_planner import AgentCall, DAGPhase
from ..infrastructure.stream_merger import StreamMerger
from ..agents.registry import agent_registry
from .shared_context import SharedContext
from .token_event import TokenEvent

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SECONDS = 60


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
        self, calls: list[AgentCall], mode: str,
        dag_phases: list[DAGPhase] | None = None,
        shared_context: SharedContext | None = None,
    ) -> AsyncIterator[TokenEvent]:
        """执行 Agent 调用列表，按模式分发。"""
        if not calls:
            return
        if mode == "dag" and dag_phases:
            async for ev in self._execute_dag(dag_phases, shared_context):
                yield ev
        elif mode == "chain":
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
        meta = self._call_metadata(call)

        if self.event_bus:
            await self._emit("AGENT_CALL_STARTED", {
                "agent_name": agent.name, "agent_id": agent.id,
                "task": call.task, "role": call.role, "phase": call.phase,
            })

        # 角色 Prompt 注入
        system_prompt = agent.system_prompt or ""
        if call.role_prompt_override:
            system_prompt = f"{system_prompt}\n\n{call.role_prompt_override}"

        full = ""
        try:
            adapter = agent_registry.get_adapter(agent.provider)
            if not adapter:
                await self._emit_call_completed(call, "error", "adapter not found")
                yield TokenEvent(
                    agent_id=agent.id, agent_name=agent.name,
                    token=f"[{agent.name} 不可用]", done=True,
                    message_id=msg_id, error="adapter not found",
                    metadata=meta,
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
                    yield TokenEvent(
                        agent_id=agent.id, agent_name=agent.name,
                        token=token, metadata=meta,
                    )

        except TimeoutError:
            logger.warning("Agent timeout: %s (60s)", agent.name)
            await self._emit_call_completed(call, "error", "timeout")
            yield TokenEvent(
                agent_id=agent.id, agent_name=agent.name,
                token=f"[{agent.name} 响应超时]", done=True,
                message_id=msg_id, error="timeout", metadata=meta,
            )
            return

        except Exception as e:
            logger.exception("Agent call failed: %s", agent.name)
            await self._emit_call_completed(call, "error", str(e))
            yield TokenEvent(
                agent_id=agent.id, agent_name=agent.name,
                token=f"[{agent.name} 错误: {e}]", done=True,
                message_id=msg_id, error=str(e), metadata=meta,
            )
            return

        if self.event_bus:
            await self._emit_call_completed(call, "ok", "", len(full))

        yield TokenEvent(
            agent_id=agent.id, agent_name=agent.name,
            token="", done=True, message_id=msg_id, metadata=meta,
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

    # ---- DAG ----

    async def _execute_dag(
        self, phases: list[DAGPhase], shared_context: SharedContext | None,
    ) -> AsyncIterator[TokenEvent]:
        """混合 DAG 执行: Phase 间串行，Phase 内并行。"""
        ctx = shared_context or SharedContext(
            phases[0].calls[0].input_messages if phases and phases[0].calls else []
        )

        for phase in phases:
            yield self._phase_event(phase, "running")
            outputs: dict[str, tuple[AgentCall, str, str | None]] = {}
            if phase.mode == "parallel" and len(phase.calls) > 1:
                async for ev in self._execute_parallel_phase(phase, ctx, outputs):
                    yield ev
            else:
                async for ev in self._execute_phase_call(phase.calls[0], ctx, outputs):
                    yield ev

            phase_status = "error" if any(err for _, _, err in outputs.values()) else "completed"
            for call, full, error in outputs.values():
                if not error and full:
                    ctx.append_output(call.task, call.agent.name, call.role, full)
            yield self._phase_event(phase, phase_status)

    async def _execute_parallel_phase(
        self, phase: DAGPhase, ctx: SharedContext,
        outputs: dict[str, tuple[AgentCall, str, str | None]],
    ) -> AsyncIterator[TokenEvent]:
        """执行一个并行 Phase，并收集每个 task 的完整输出。"""
        gens = [self._execute_phase_call(c, ctx, outputs) for c in phase.calls[:5]]
        async for ev in self.merger.merge(gens):
            yield ev

    async def _execute_phase_call(
        self, call: AgentCall, ctx: SharedContext,
        outputs: dict[str, tuple[AgentCall, str, str | None]],
    ) -> AsyncIterator[TokenEvent]:
        """执行单个 DAG task，完成后把完整输出写入 outputs。"""
        call.input_messages = ctx.get_for_agent(call.depends_on)
        full = ""
        error: str | None = None
        async for ev in self._execute_single(call):
            if ev.token and not ev.done:
                full += ev.token
            if ev.error:
                error = ev.error
            yield ev
        outputs[call.task] = (call, full, error)

    @staticmethod
    def _phase_event(phase: DAGPhase, status: str) -> TokenEvent:
        """构造 Phase 状态切换事件。"""
        return TokenEvent(
            event_type="phase_change",
            metadata={
                "phase": phase.phase,
                "status": status,
                "agents": [c.agent.name for c in phase.calls],
                "tasks": [c.task for c in phase.calls],
            },
        )

    @staticmethod
    def _call_metadata(call: AgentCall) -> dict:
        """统一给 token/done 事件附带协作元数据。"""
        return {
            "task": call.task,
            "role": call.role,
            "phase": call.phase,
            "depends_on": list(call.depends_on),
        }

    # ---- EventBus ----

    async def _emit(self, event_name: str, payload: dict):
        """安全发布 EventBus 事件（fire-and-forget）。"""
        try:
            from ..event_bus import EventType
            await self.event_bus.publish(EventType[event_name], payload)
        except Exception:
            pass

    async def _emit_call_completed(
        self, call: AgentCall, status: str, error: str = "", token_count: int = 0,
    ) -> None:
        """发布 Agent 调用完成事件，成功和失败路径都覆盖。"""
        if not self.event_bus:
            return
        await self._emit("AGENT_CALL_COMPLETED", {
            "agent_name": call.agent.name,
            "agent_id": call.agent.id,
            "task": call.task,
            "role": call.role,
            "phase": call.phase,
            "status": status,
            "error": error,
            "token_count": token_count,
        })
