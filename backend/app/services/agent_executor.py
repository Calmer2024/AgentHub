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

from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.execution_planner import AgentCall, DAGPhase
from ..infrastructure.stream_merger import StreamMerger
from .cli_agent_executor import CliAgentCallRunner
from .shared_context import SharedContext
from .token_event import TokenEvent

logger = logging.getLogger(__name__)

class AgentExecutor:
    """Agent 调用执行器。

    支持四种模式:
      - single:   单 Agent 流式调用 (60s 超时保护)
      - serial:   多 Agent 串行调用，上一步产出注入下一步
      - parallel: 历史兼容模式，目前降级为串行执行
      - chain:    链式调用，角色 Prompt 注入 + 中断处理
    """

    def __init__(self, db: AsyncSession | None = None, event_bus=None, cli_runner: CliAgentCallRunner | None = None):
        self.event_bus = event_bus
        self.merger = StreamMerger()
        self._cli_runner = cli_runner or CliAgentCallRunner(db=db, event_bus=event_bus)

    async def execute(
        self, calls: list[AgentCall], mode: str,
        dag_phases: list[DAGPhase] | None = None,
        shared_context: SharedContext | None = None,
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> AsyncIterator[TokenEvent]:
        """执行 Agent 调用列表，按模式分发。"""
        if not calls:
            return
        if mode == "dag" and dag_phases:
            async for ev in self._execute_dag(dag_phases, shared_context, session_id, workspace_path):
                yield ev
        elif mode == "chain":
            async for ev in self._execute_chain(calls, session_id, workspace_path):
                yield ev
        elif len(calls) > 1 and mode in {"serial", "parallel"}:
            async for ev in self._execute_serial(calls, session_id, workspace_path):
                yield ev
        else:
            async for ev in self._execute_single(calls[0], session_id, workspace_path):
                yield ev

    # ---- Single ----

    async def _execute_single(
        self,
        call: AgentCall,
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> AsyncIterator[TokenEvent]:
        """单 Agent 流式调用。用户 Agent 执行只允许 CLI wrapper。"""
        agent = call.agent
        msg_id = f"agent-{agent.id}"
        meta = self._call_metadata(call)

        if workspace_path and (agent.agent_type or "cli_wrapper") == "cli_wrapper":
            async for ev in self._cli_runner.execute(
                call,
                session_id=session_id,
                workspace_path=workspace_path,
            ):
                yield ev
            return

        yield TokenEvent(
            agent_id=agent.id,
            agent_name=agent.name,
            token=f"[{agent.name} 无法执行：当前项目只支持 CLI Agent]",
            done=True,
            message_id=msg_id,
            error="CLI Agent requires a project workspace",
            metadata=meta,
        )

    # ---- Parallel ----

    async def _execute_parallel(
        self,
        calls: list[AgentCall],
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> AsyncIterator[TokenEvent]:
        """多 Agent 并行调用，StreamMerger 交错输出。"""
        gens = [self._execute_single(c, session_id, workspace_path) for c in calls[:5]]
        async for ev in self.merger.merge(gens):
            yield ev

    # ---- Serial ----

    async def _execute_serial(
        self,
        calls: list[AgentCall],
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> AsyncIterator[TokenEvent]:
        """多 Agent 串行执行，后续 Agent 读取前序完整产出。"""
        previous_outputs: list[tuple[AgentCall, str]] = []
        for call in calls:
            if previous_outputs:
                call.input_messages = [
                    *call.input_messages,
                    *_serial_output_messages(previous_outputs),
                ]
            full = ""
            step_error = None
            async for ev in self._execute_single(call, session_id, workspace_path):
                if ev.token and not ev.done:
                    full += ev.token
                if ev.error:
                    step_error = ev.error
                yield ev
            previous_outputs.append((call, full))
            if step_error:
                logger.warning("Serial call failed (%s): %s", call.agent.name, step_error)
                break

    # ---- Chain ----

    async def _execute_chain(
        self,
        calls: list[AgentCall],
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> AsyncIterator[TokenEvent]:
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
            async for ev in self._execute_single(call, session_id, workspace_path):
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
        self,
        phases: list[DAGPhase],
        shared_context: SharedContext | None,
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> AsyncIterator[TokenEvent]:
        """混合 DAG 执行: Phase 间串行，Phase 内也按顺序执行。"""
        ctx = shared_context or SharedContext(
            phases[0].calls[0].input_messages if phases and phases[0].calls else []
        )

        for phase in phases:
            yield self._phase_event(phase, "running")
            outputs: dict[str, tuple[AgentCall, str, str | None]] = {}
            phase_failed = False
            for call in phase.calls:
                async for ev in self._execute_phase_call(
                    call, ctx, outputs, session_id, workspace_path,
                ):
                    yield ev
                done_call, full, error = outputs.get(call.task, (call, "", None))
                if not error and full:
                    ctx.append_output(done_call.task, done_call.agent.name, done_call.role, full)
                if error:
                    phase_failed = True
                    break

            phase_status = "error" if any(err for _, _, err in outputs.values()) else "completed"
            yield self._phase_event(phase, phase_status)
            if phase_failed:
                break

    async def _execute_parallel_phase(
        self, phase: DAGPhase, ctx: SharedContext,
        outputs: dict[str, tuple[AgentCall, str, str | None]],
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> AsyncIterator[TokenEvent]:
        """执行一个并行 Phase，并收集每个 task 的完整输出。"""
        gens = [
            self._execute_phase_call(c, ctx, outputs, session_id, workspace_path)
            for c in phase.calls[:5]
        ]
        async for ev in self.merger.merge(gens):
            yield ev

    async def _execute_phase_call(
        self, call: AgentCall, ctx: SharedContext,
        outputs: dict[str, tuple[AgentCall, str, str | None]],
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> AsyncIterator[TokenEvent]:
        """执行单个 DAG task，完成后把完整输出写入 outputs。"""
        call.input_messages = ctx.get_for_agent(call.depends_on)
        full = ""
        error: str | None = None
        async for ev in self._execute_single(call, session_id, workspace_path):
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


def _serial_output_messages(outputs: list[tuple[AgentCall, str]]) -> list[dict]:
    """把串行上游产出转成后续 Agent 可读上下文。"""
    messages: list[dict] = []
    for call, content in outputs:
        if not content:
            continue
        messages.append({
            "role": "assistant",
            "content": f"[上一步 @{call.agent.name} / {call.task} 产出]\n{content[:3000]}",
        })
    return messages
