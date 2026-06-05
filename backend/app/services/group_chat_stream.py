"""GroupChatStream —— 群聊 Orchestrator SSE 编排。"""

import json
import uuid
import logging
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Session as DBSession, AgentConfig, Message as DBMessage, SessionMember
from ..agents.cli_trace import trace_text
from ..domain.orchestrator_v2 import OrchestratorV2, PipelineRequest
from ..domain.execution_planner import AgentCall, ChainConfig
from ..domain.orchestrator_plan import (
    build_plan_prompt,
    extract_json_object,
    normalize_plan,
    validate_plan,
    visualize_mermaid,
)
from .agent_executor import AgentExecutor
from .cli_agent_service import CliAgentService
from .execution_trace import ExecutionTraceBuilder, merge_trace_metadata
from .project_service import ProjectService, ProjectNotFoundError
from .shared_context import SharedContext
from .group_chat_finalizer import GroupChatFinalizer

logger = logging.getLogger(__name__)


class GroupChatStream:
    """群聊流式处理器：Pipeline → Executor → SSE → 持久化。"""

    def __init__(
        self, db: AsyncSession, pipeline: OrchestratorV2, executor: AgentExecutor,
    ):
        self.db = db
        self._pipeline = pipeline
        self._executor = executor
        self._finalizer = GroupChatFinalizer(db, pipeline)

    async def send(
        self, session_id: str, content: str, mentions: list[str] | None,
        history: list[dict], pinned_message_ids: list[str], session: DBSession, chain_config=None,
    ) -> AsyncGenerator[str, None]:
        member_agents = await self._member_agents(session_id)
        if not member_agents:
            yield self._err("该群聊没有可用的 Agent")
            return
        try:
            workspace_path = await ProjectService(self.db).get_workspace_path_for_session(session_id)
        except ProjectNotFoundError:
            yield self._err("当前会话未绑定项目，无法启动 CLI Agent")
            return

        orchestrator_agent = self._mentioned_orchestrator(member_agents, mentions, content)
        if orchestrator_agent:
            async for item in self._run_plan_only(
                session_id=session_id,
                content=content,
                history=history,
                workspace_path=workspace_path,
                orchestrator_agent=orchestrator_agent,
                member_agents=member_agents,
            ):
                yield item
            return

        cc = None
        if chain_config:
            cc = ChainConfig(
                chain_name=getattr(chain_config, 'chain_name', None),
                agent_order=getattr(chain_config, 'agent_order', None),
            )

        result = await self._pipeline.run(PipelineRequest(
            session_id=session_id,
            content=content,
            mentions=mentions,
            messages=history,
            pinned_message_ids=pinned_message_ids,
            member_agents=member_agents,
            system_prompt="",
            context_budget=100_000,
            chain_config=cc,
            supplemental=self._is_supplemental_turn(content, mentions),
        ))
        if not result.agent_calls:
            yield self._err("没有合适的 Agent 处理此请求，请尝试 @ 指定 Agent")
            return

        yield self._sse({"type": "orchestrator.route", "agents": self._route_info(result.agent_calls)})
        yield self._sse(self._task_started_payload(result))
        if result.truncated:
            logger.info("会话 %s 触发上下文截断: tokens=%d", session_id, result.total_tokens)

        agent_names = {
            self._call_key(c.agent.id, c.task, c.phase): c.agent.name
            for c in result.agent_calls
        }
        agent_calls = {
            self._call_key(c.agent.id, c.task, c.phase): c
            for c in result.agent_calls
        }
        msg_ids: dict[str, str] = {}
        agent_texts: dict[str, str] = {}
        agent_errors: dict[str, str] = {}
        agent_traces: dict[str, list[dict]] = {}
        seen_calls: set[str] = set()
        shared_context = SharedContext(result.assembled_messages) \
            if result.execution_mode == "dag" else None

        async for ev in self._executor.execute(
            result.agent_calls,
            result.execution_mode,
            dag_phases=result.dag_phases,
            shared_context=shared_context,
            session_id=session_id,
            workspace_path=workspace_path,
        ):
            async for item in self._event_to_sse(
                ev, agent_names, msg_ids, agent_errors, seen_calls, agent_traces,
            ):
                yield item
            if ev.event_type == "token" and ev.token and not ev.done:
                agent_texts[self._event_key(ev)] = agent_texts.get(self._event_key(ev), "") + ev.token

        async for item in self._finalizer.finish(
            session_id, session, result, agent_names, agent_calls,
            msg_ids, agent_texts, agent_errors, agent_traces,
        ):
            yield item

    async def _member_agents(self, session_id: str) -> list[AgentConfig]:
        rows = await self.db.execute(
            select(AgentConfig).join(
                SessionMember, SessionMember.agent_config_id == AgentConfig.id,
            ).where(
                SessionMember.session_id == session_id,
                AgentConfig.is_active == True,
            )
        )
        return list(rows.scalars().all())

    async def _run_plan_only(
        self,
        *,
        session_id: str,
        content: str,
        history: list[dict],
        workspace_path: str,
        orchestrator_agent: AgentConfig,
        member_agents: list[AgentConfig],
    ) -> AsyncGenerator[str, None]:
        candidate_agents = [
            self._agent_snapshot(agent)
            for agent in member_agents
            if agent.id != orchestrator_agent.id
        ]
        prompt = build_plan_prompt(content, candidate_agents)
        raw_output = ""
        parse_output = ""
        visible = ""
        process_id = ""
        exit_code = None
        message_id = str(uuid.uuid4())
        call_key = self._call_key(orchestrator_agent.id, "draft plan", 0)
        trace = ExecutionTraceBuilder(
            agent_name=orchestrator_agent.name,
            cli_tool=orchestrator_agent.cli_tool or "custom",
            workspace_path=workspace_path,
        )
        metadata: dict = {
            "agentType": orchestrator_agent.agent_type or "cli_wrapper",
            "cliTool": orchestrator_agent.cli_tool or "custom",
            "workspacePath": workspace_path,
        }

        yield self._sse({
            "type": "agent.start",
            "agentId": orchestrator_agent.id,
            "agentName": orchestrator_agent.name,
            "messageId": message_id,
            "role": "planner",
            "phase": 0,
            "task": "draft plan",
            "callKey": call_key,
        })

        async for event in CliAgentService().stream(
            agent=orchestrator_agent,
            session_id=session_id,
            workspace_path=workspace_path,
            messages=[*history, {"role": "user", "content": prompt}],
            system_prompt=orchestrator_agent.system_prompt or "",
        ):
            process_id = event.process_id or process_id
            if event.type == "agent.process.started":
                metadata["processId"] = process_id
                trace.set_process(process_id)
                item = trace.add(
                    kind="process",
                    text=trace_text(event.trace or {}, f"正在启动 {orchestrator_agent.name}"),
                    process_id=process_id,
                    trace=event.trace,
                )
                if item:
                    yield self._plan_trace_delta(orchestrator_agent, message_id, process_id, call_key, item)
                yield self._sse({
                    "type": "agent.process.started",
                    "agentId": orchestrator_agent.id,
                    "agentName": orchestrator_agent.name,
                    "messageId": message_id,
                    "processId": process_id,
                    "callKey": call_key,
                    "role": "planner",
                    "phase": 0,
                    "task": "draft plan",
                    "token": "",
                    "done": False,
                })
                continue

            if event.type == "agent.output":
                if event.chunk_type in {"text", "artifact_signal"}:
                    raw_output += event.chunk
                    parse_output += event.chunk
                    visible += event.chunk
                trace_item = None
                if event.chunk_type != "text":
                    trace_item = trace.add(
                        kind="artifact" if event.chunk_type == "artifact_signal"
                        else "error" if event.chunk_type == "error" else "progress",
                        text=event.chunk,
                        source="cli",
                        chunk_type=event.chunk_type,
                        process_id=process_id,
                        trace=event.trace,
                    )
                if trace_item:
                    yield self._plan_trace_delta(orchestrator_agent, message_id, process_id, call_key, trace_item)
                yield self._sse({
                    "type": "agent.output",
                    "agentId": orchestrator_agent.id,
                    "agentName": orchestrator_agent.name,
                    "token": event.chunk if event.chunk_type == "text" else "",
                    "messageId": message_id,
                    "role": "planner",
                    "phase": 0,
                    "task": "draft plan",
                    "callKey": call_key,
                    "processId": process_id,
                    "chunk": event.chunk,
                    "chunkType": event.chunk_type,
                    "done": False,
                })
                continue
            elif event.type == "interactive_prompt":
                item = trace.add(
                    kind="prompt",
                    text=event.chunk,
                    source="cli",
                    chunk_type="interactive_prompt",
                    process_id=process_id,
                    trace=event.trace,
                )
                if item:
                    yield self._plan_trace_delta(orchestrator_agent, message_id, process_id, call_key, item)
                yield self._sse({
                    "type": "interactive_prompt",
                    "agentId": orchestrator_agent.id,
                    "agentName": orchestrator_agent.name,
                    "messageId": message_id,
                    "processId": process_id,
                    "callKey": call_key,
                    "content": event.chunk,
                    "promptType": event.prompt_type,
                    "token": "",
                    "done": False,
                })
                continue
            elif event.type == "agent.process.completed":
                exit_code = event.exit_code
                metadata["exitCode"] = exit_code
                status = "completed" if exit_code in (0, None) else "error"
                item = trace.add(
                    kind="process",
                    text=trace_text(event.trace or {}, f"{orchestrator_agent.name} 已结束"),
                    process_id=process_id,
                    trace=event.trace,
                )
                trace.complete(status=status, exit_code=exit_code)
                if item:
                    yield self._plan_trace_delta(orchestrator_agent, message_id, process_id, call_key, item)
                yield self._sse({
                    "type": "agent.process.completed",
                    "agentId": orchestrator_agent.id,
                    "agentName": orchestrator_agent.name,
                    "messageId": message_id,
                    "processId": process_id,
                    "callKey": call_key,
                    "role": "planner",
                    "phase": 0,
                    "task": "draft plan",
                    "exitCode": exit_code,
                    "token": "",
                    "done": False,
                })
                continue
            elif event.type == "error":
                error = event.error or "调度器执行失败"
                trace.add(kind="error", text=error, process_id=process_id, trace=event.trace)
                trace.complete(status="error", exit_code=exit_code)
                metadata["error"] = error
                await self._persist_orchestrator_message(
                    session_id=session_id,
                    message_id=message_id,
                    agent=orchestrator_agent,
                    content=visible or raw_output or f"调度器执行失败：{error}",
                    metadata=merge_trace_metadata(metadata, trace),
                )
                yield self._err(error)
                return

        try:
            parsed = extract_json_object(parse_output)
            plan = normalize_plan(parsed)
            validation = validate_plan(
                plan,
                {str(agent["id"]) for agent in candidate_agents},
            )
        except ValueError as exc:
            await self._persist_orchestrator_message(
                session_id=session_id,
                message_id=message_id,
                agent=orchestrator_agent,
                content=visible or raw_output,
                metadata=merge_trace_metadata({
                    **metadata,
                    "orchestratorPlanError": str(exc),
                }, trace),
            )
            yield self._sse({
                "token": "",
                "done": True,
                "messageId": message_id,
                "error": str(exc),
            })
            return

        await self._persist_orchestrator_message(
            session_id=session_id,
            message_id=message_id,
            agent=orchestrator_agent,
            content=visible,
            metadata=merge_trace_metadata({
                **metadata,
                "orchestratorPlan": {
                    "ok": validation["ok"],
                    "normalizedPlan": plan,
                    "validation": validation,
                    "visualization": {"mermaid": visualize_mermaid(plan)},
                }
            }, trace),
        )
        yield self._sse({
            "token": "",
            "done": True,
            "messageId": message_id,
        })

    async def _persist_orchestrator_message(
        self,
        *,
        session_id: str,
        message_id: str,
        agent: AgentConfig,
        content: str,
        metadata: dict,
    ) -> None:
        self.db.add(DBMessage(
            id=message_id,
            session_id=session_id,
            role="assistant",
            content=content,
            content_type="text",
            agent_name=agent.name,
            source_type="agent",
            source_id=agent.id,
            source_name=agent.name,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ))
        await self.db.commit()

    def _plan_trace_delta(
        self,
        agent: AgentConfig,
        message_id: str,
        process_id: str,
        call_key: str,
        item: dict,
    ) -> str:
        return self._sse({
            "type": "agent.trace.delta",
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "processId": process_id,
            "callKey": call_key,
            "role": "planner",
            "phase": 0,
            "task": "draft plan",
            "item": item,
            "token": "",
            "done": False,
        })

    @staticmethod
    def _mentioned_orchestrator(
        agents: list[AgentConfig],
        mentions: list[str] | None,
        content: str = "",
    ) -> AgentConfig | None:
        mention_ids = set(mentions or [])
        for agent in agents:
            if agent.id in mention_ids and (agent.primary_skill or "") == "orchestrator_planner":
                return agent
        for agent in agents:
            if (agent.primary_skill or "") != "orchestrator_planner":
                continue
            if f"@{agent.name}" in content or "@Orchestrator" in content:
                return agent
        return None

    @staticmethod
    def _agent_snapshot(agent: AgentConfig) -> dict:
        try:
            auxiliary = json.loads(agent.auxiliary_skills or "[]")
        except json.JSONDecodeError:
            auxiliary = []
        return {
            "id": agent.id,
            "name": agent.name,
            "engine": agent.cli_tool or "custom",
            "primary_skill": agent.primary_skill or "general_coding",
            "auxiliary_skills": auxiliary if isinstance(auxiliary, list) else [],
            "context_policy": agent.context_policy or "workspace_coding",
        }

    async def _event_to_sse(
        self, ev, agent_names, msg_ids, agent_errors, seen_calls, agent_traces,
    ):
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
                agent_errors[self._event_key(ev)] = ev.metadata.get("error", "链式中断")
            return

        if ev.is_phase_change:
            yield self._sse({
                "type": "orchestrator.phase_change",
                "phase": ev.metadata.get("phase", 0),
                "status": ev.metadata.get("status", "running"),
                "agents": ev.metadata.get("agents", []),
                "tasks": ev.metadata.get("tasks", []),
            })
            return

        call_key = self._event_key(ev)
        if ev.agent_id and call_key not in seen_calls:
            seen_calls.add(call_key)
            msg_ids[call_key] = str(uuid.uuid4())
            yield self._agent_start(ev, agent_names.get(call_key, ""), msg_ids[call_key], call_key)

        if ev.done:
            if ev.error:
                agent_errors[call_key] = ev.error
            yield self._agent_done(ev, agent_names.get(call_key, ""), msg_ids.get(call_key), call_key)
            return

        if ev.is_structured:
            trace = ev.metadata.get("trace")
            if isinstance(trace, dict):
                agent_traces.setdefault(call_key, []).append(trace)
                yield self._trace_delta(
                    ev, agent_names.get(call_key, ""), msg_ids.get(call_key), call_key, trace,
                )
            yield self._structured_event(ev, agent_names.get(call_key, ""), msg_ids.get(call_key), call_key)
            return

        yield self._sse({
            "token": ev.token,
            "agentId": ev.agent_id,
            "agentName": ev.agent_name or agent_names.get(call_key, ""),
            "done": False,
            "messageId": msg_ids.get(call_key),
            "role": ev.metadata.get("role"),
            "phase": ev.metadata.get("phase"),
            "task": ev.metadata.get("task"),
            "callKey": call_key,
        })

    def _agent_start(self, ev, fallback_name: str, msg_id: str, call_key: str) -> str:
        return self._sse({
            "type": "agent.start",
            "agentId": ev.agent_id,
            "agentName": ev.agent_name or fallback_name,
            "messageId": msg_id,
            "role": ev.metadata.get("role"),
            "phase": ev.metadata.get("phase"),
            "task": ev.metadata.get("task"),
            "callKey": call_key,
        })

    def _agent_done(self, ev, fallback_name: str, msg_id: str | None, call_key: str) -> str:
        data = {
            "token": ev.token if ev.error else "",
            "agentId": ev.agent_id,
            "agentName": ev.agent_name or fallback_name,
            "done": True,
            "messageId": msg_id or str(uuid.uuid4()),
            "role": ev.metadata.get("role"),
            "phase": ev.metadata.get("phase"),
            "task": ev.metadata.get("task"),
            "callKey": call_key,
        }
        if ev.error:
            data["error"] = ev.error
        return self._sse(data)

    def _structured_event(self, ev, fallback_name: str, msg_id: str | None, call_key: str) -> str:
        base = {
            "type": ev.event_type,
            "agentId": ev.agent_id,
            "agentName": ev.agent_name or fallback_name,
            "messageId": msg_id,
            "role": ev.metadata.get("role"),
            "phase": ev.metadata.get("phase"),
            "task": ev.metadata.get("task"),
            "callKey": call_key,
            "metadata": ev.metadata,
        }
        if ev.event_type == "agent.output":
            base.update({
                "chunk": ev.metadata.get("chunk", ev.token),
                "chunkType": ev.metadata.get("chunkType", "text"),
                "token": ev.token,
                "done": False,
                "processId": ev.metadata.get("processId"),
            })
        elif ev.event_type == "interactive_prompt":
            base.update({
                "sessionId": ev.metadata.get("sessionId"),
                "processId": ev.metadata.get("processId"),
                "content": ev.metadata.get("content", ""),
                "promptType": ev.metadata.get("promptType", "confirm"),
                "token": "",
                "done": False,
            })
        elif ev.event_type.startswith("agent.process."):
            base.update({
                "processId": ev.metadata.get("processId"),
                "exitCode": ev.metadata.get("exitCode"),
                "token": "",
                "done": False,
            })
        return self._sse(base)

    def _trace_delta(
        self, ev, fallback_name: str, msg_id: str | None, call_key: str, trace: dict,
    ) -> str:
        return self._sse({
            "type": "agent.trace.delta",
            "agentId": ev.agent_id,
            "agentName": ev.agent_name or fallback_name,
            "messageId": msg_id,
            "role": ev.metadata.get("role"),
            "phase": ev.metadata.get("phase"),
            "task": ev.metadata.get("task"),
            "callKey": call_key,
            "processId": ev.metadata.get("processId"),
            "item": trace,
            "token": "",
            "done": False,
        })

    @staticmethod
    def _task_started_payload(result) -> dict:
        tasks = [GroupChatStream._task_payload(c, result.execution_mode == "dag")
                 for c in result.agent_calls]
        payload = {
            "type": "orchestrator.task_started",
            "intent": result.intent,
            "plan_summary": result.plan_summary,
            "tasks": tasks,
        }
        if result.dag_phases:
            payload["dag"] = {"phases": [
                {
                    "phase": p.phase,
                    "mode": p.mode,
                    "tasks": [GroupChatStream._task_payload(c, True) for c in p.calls],
                }
                for p in result.dag_phases
            ]}
        return payload

    @staticmethod
    def _task_payload(call: AgentCall, pending: bool) -> dict:
        return {
            "name": call.task,
            "role": call.role,
            "agent": call.agent.name,
            "agentId": call.agent.id,
            "status": "pending" if pending else "running",
            "depends_on": list(call.depends_on),
            "phase": call.phase,
        }

    @staticmethod
    def _route_info(calls: list[AgentCall]) -> list[dict]:
        seen: set[str] = set()
        result = []
        for call in calls:
            if call.agent.id not in seen:
                seen.add(call.agent.id)
                result.append({"id": call.agent.id, "name": call.agent.name})
        return result

    @staticmethod
    def _call_key(agent_id: str, task: str | None, phase: int | None) -> str:
        return f"{agent_id}:{phase if phase is not None else 0}:{task or 'primary'}"

    @classmethod
    def _event_key(cls, ev) -> str:
        return cls._call_key(ev.agent_id, ev.metadata.get("task"), ev.metadata.get("phase"))

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    @staticmethod
    def _is_supplemental_turn(content: str, mentions: list[str] | None) -> bool:
        if mentions:
            return True
        markers = ("补充", "补上", "缺失", "缺少", "遗漏", "漏了",
                   "还需要", "只让", "单独让", "再让")
        return any(marker in content for marker in markers)

    @staticmethod
    def _err(msg: str) -> str:
        return f"data: {json.dumps({'token': '', 'done': True, 'error': msg}, ensure_ascii=False)}\n\n"
