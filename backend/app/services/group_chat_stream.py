"""GroupChatStream —— 群聊 Orchestrator SSE 编排。"""

import json
import uuid
import logging
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..models import Session as DBSession, AgentConfig, Message as DBMessage, SessionMember
from ..domain.orchestrator_v2 import OrchestratorV2, PipelineRequest
from ..domain.execution_planner import AgentCall, ChainConfig
from .agent_executor import AgentExecutor
from .approval_service import ApprovalService, approval_to_read
from .project_service import ProjectService, ProjectNotFoundError
from .run_service import RunService, task_to_read, run_to_read
from .session_service import SessionService
from .shared_context import SharedContext
from .group_chat_finalizer import GroupChatFinalizer
from .orchestrator_plan_chat import OrchestratorPlanChat
from .orchestrator_steward_chat import OrchestratorStewardChat, StewardAgentDecision

logger = logging.getLogger(__name__)


class GroupChatStream:
    """群聊流式处理器：Pipeline → Executor → SSE → 持久化。"""

    def __init__(
        self, db: AsyncSession, pipeline: OrchestratorV2, executor: AgentExecutor, event_bus=None,
    ):
        self.db = db
        self.event_bus = event_bus
        self._pipeline = pipeline
        self._executor = executor
        self._finalizer = GroupChatFinalizer(db, pipeline, event_bus=event_bus)
        self._plan_chat = OrchestratorPlanChat(db)
        self._steward_chat = OrchestratorStewardChat(db, event_bus=event_bus)

    async def send(
        self, session_id: str, content: str, mentions: list[str] | None,
        history: list[dict], pinned_message_ids: list[str], session: DBSession, chain_config=None,
        run_id: str | None = None, approval_required: bool = False,
    ) -> AsyncGenerator[str, None]:
        member_agents = await self._member_agents(session_id)
        if not member_agents:
            if run_id:
                run = await RunService(self.db, event_bus=self.event_bus).mark_run_status(
                    run_id,
                    "failed",
                    reason="该群聊没有可用的 Agent",
                )
                yield self._run_status_changed(run)
            await self._persist_system_notice(session, session_id, "该群聊没有可用的 Agent")
            yield self._err("该群聊没有可用的 Agent")
            return
        try:
            workspace_path = await ProjectService(self.db).get_workspace_path_for_session(session_id)
        except ProjectNotFoundError:
            if run_id:
                run = await RunService(self.db, event_bus=self.event_bus).mark_run_status(
                    run_id,
                    "failed",
                    reason="当前会话未绑定项目",
                )
                yield self._run_status_changed(run)
            yield self._err("当前会话未绑定项目，无法启动 CLI Agent")
            return

        orchestrator_agent = self._mentioned_orchestrator(member_agents, mentions, content)
        if orchestrator_agent:
            async for item in self._plan_chat.send(
                session_id=session_id,
                content=content,
                history=history,
                workspace_path=workspace_path,
                orchestrator_agent=orchestrator_agent,
                member_agents=member_agents,
                run_id=run_id,
            ):
                yield item
            return

        steward_decision: StewardAgentDecision | None = None
        if not mentions:
            orchestrator_agent = self._orchestrator(member_agents)
            if not orchestrator_agent:
                message_id = await self._persist_system_notice(
                    session,
                    session_id,
                    "群聊缺少 Orchestrator 调度器，无法处理无 @ 消息。请在群聊中加入调度器后重试。",
                )
                if run_id:
                    run = await RunService(self.db, event_bus=self.event_bus).mark_run_status(
                        run_id,
                        "failed",
                        current_message_id=message_id,
                        reason="群聊缺少 Orchestrator 调度器",
                    )
                    yield self._run_status_changed(run)
                yield self._err("群聊缺少 Orchestrator 调度器，无法处理无 @ 消息")
                return
            if await self._plan_chat.has_latest_orchestrator_plan(session_id):
                async for item in self._plan_chat.send(
                    session_id=session_id,
                    content=content,
                    history=history,
                    workspace_path=workspace_path,
                    orchestrator_agent=orchestrator_agent,
                    member_agents=member_agents,
                    run_id=run_id,
                ):
                    yield item
                return
            steward_message_id = ""
            steward_error = None
            async for item in self._steward_chat.stream(
                session=session,
                content=content,
                history=history,
                workspace_path=workspace_path,
                orchestrator_agent=orchestrator_agent,
                member_agents=member_agents,
                run_id=run_id,
            ):
                steward_message_id = item.message_id
                steward_error = item.error or steward_error
                if item.decision:
                    steward_decision = item.decision
                    yield self._steward_decision_event(steward_decision)
                yield item.sse
            if run_id and await self._run_was_cancelled(run_id):
                return
            if steward_error:
                if run_id:
                    run = await RunService(self.db, event_bus=self.event_bus).mark_run_status(
                        run_id,
                        "failed",
                        current_message_id=steward_message_id,
                        reason=steward_error,
                    )
                    yield self._run_status_changed(run)
                yield self._sse({"token": "", "done": True, "messageId": steward_message_id, "error": steward_error})
                return
            if steward_decision is None:
                if run_id:
                    run = await RunService(self.db, event_bus=self.event_bus).mark_run_status(
                        run_id,
                        "completed",
                        current_message_id=steward_message_id,
                    )
                    yield self._run_status_changed(run)
                yield self._sse({"token": "", "done": True, "messageId": steward_message_id})
                return
            if steward_decision.route_type == "context_only":
                if run_id:
                    run = await RunService(self.db, event_bus=self.event_bus).mark_run_status(
                        run_id,
                        "completed",
                        current_message_id=steward_message_id,
                    )
                    yield self._run_status_changed(run)
                yield self._sse({"token": "", "done": True, "messageId": steward_message_id})
                return
            if steward_decision.route_type in {"draft_plan", "mini_collab"}:
                plan_member_agents = (
                    steward_decision.selected_agents
                    if steward_decision.route_type == "mini_collab" and steward_decision.selected_agents
                    else member_agents
                )
                async for item in self._plan_chat.send(
                    session_id=session_id,
                    content=self._plan_content_for_steward_decision(content, steward_decision),
                    history=history,
                    workspace_path=workspace_path,
                    orchestrator_agent=orchestrator_agent,
                    member_agents=plan_member_agents,
                    run_id=run_id,
                ):
                    yield item
                return
            if not steward_decision.selected_agents:
                if run_id:
                    run = await RunService(self.db, event_bus=self.event_bus).mark_run_status(
                        run_id,
                        "failed",
                        reason="Orchestrator 调度器没有找到合适的 Agent",
                    )
                    yield self._run_status_changed(run)
                yield self._err("Orchestrator 调度器没有找到合适的 Agent，请尝试 @ 指定 Agent")
                return
            mentions = [agent.id for agent in steward_decision.selected_agents]

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
            supplemental=(
                True if steward_decision else self._is_supplemental_turn(content, mentions)
            ),
        ))
        if not result.agent_calls:
            if run_id:
                run = await RunService(self.db, event_bus=self.event_bus).mark_run_status(
                    run_id,
                    "failed",
                    reason="没有合适的 Agent 处理此请求",
                )
                yield self._run_status_changed(run)
            yield self._err("没有合适的 Agent 处理此请求，请尝试 @ 指定 Agent")
            return

        run_service = RunService(self.db, event_bus=self.event_bus) if run_id else None
        approval_service = ApprovalService(self.db, event_bus=self.event_bus) if run_id else None
        run_tasks: dict[str, str] = {}
        if run_service and run_id:
            run = await run_service.get_run(run_id)
            for index, call in enumerate(result.agent_calls):
                requires_approval = approval_required and index == len(result.agent_calls) - 1
                task = await run_service.create_task(
                    run,
                    agent_id=call.agent.id,
                    name=call.task,
                    role=call.role,
                    phase=call.phase,
                    depends_on=list(call.depends_on),
                    metadata={
                        "requiresHumanApproval": requires_approval,
                        "approvalTitle": f"确认 {call.task}",
                    },
                )
                run_tasks[self._call_key(call.agent.id, call.task, call.phase)] = task.id
                yield self._task_status_changed(run_id, task)

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
        agent_metadata: dict[str, dict] = {}
        seen_calls: set[str] = set()
        persisted_calls: set[str] = set()
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
            sse_items = []
            self._merge_agent_metadata(agent_metadata, ev)
            async for item in self._event_to_sse(
                ev, agent_names, msg_ids, agent_errors, seen_calls, agent_traces,
            ):
                sse_items.append(item)
            if run_service and run_id:
                async for runtime_event in self._runtime_events_for_executor_event(
                    run_service,
                    run_id,
                    run_tasks,
                    ev,
                    msg_ids,
                    session_id,
                ):
                    yield runtime_event
            for item in sse_items:
                yield item
            if ev.event_type == "token" and ev.token and not ev.done:
                agent_texts[self._event_key(ev)] = agent_texts.get(self._event_key(ev), "") + ev.token
            if ev.done and ev.agent_id:
                call_key = self._event_key(ev)
                if ev.error:
                    agent_errors[call_key] = ev.error
                if call_key not in persisted_calls:
                    async for item in self._finalizer.persist_one(
                        session_id=session_id,
                        session=session,
                        key=call_key,
                        agent_names=agent_names,
                        agent_calls=agent_calls,
                        msg_ids=msg_ids,
                        text=agent_texts.get(call_key, ""),
                        error=agent_errors.get(call_key),
                        trace_items=agent_traces.get(call_key),
                        metadata=agent_metadata.get(call_key),
                    ):
                        yield item
                    if agent_texts.get(call_key):
                        persisted_calls.add(call_key)

        async for item in self._finalizer.finish(
            session_id, session, result, agent_names, agent_calls,
            msg_ids, agent_texts, agent_errors, agent_traces, persisted_calls,
            agent_metadata,
        ):
            yield item

        if run_service and run_id:
            pending_checkpoints = []
            if approval_service:
                for call_key, task_id in run_tasks.items():
                    checkpoint = await approval_service.create_for_completed_task_if_needed(
                        task_id=task_id,
                        message_id=msg_ids.get(call_key),
                        summary=(agent_texts.get(call_key) or "")[:240],
                    )
                    if checkpoint:
                        pending_checkpoints.append(checkpoint)
                        yield self._approval_created(checkpoint)
                        task = await run_service.mark_task_status(
                            task_id,
                            "paused",
                            message_id=msg_ids.get(call_key),
                            metadata_patch={"approvalCheckpointId": checkpoint.id},
                        )
                        yield self._task_status_changed(run_id, task)
            run = await run_service.complete_run_from_tasks(run_id)
            if pending_checkpoints:
                run = await run_service.mark_run_status(
                    run_id,
                    "paused",
                    current_message_id=pending_checkpoints[-1].message_id,
                )
            yield self._run_status_changed(run)

    def _steward_decision_event(self, decision: StewardAgentDecision) -> str:
        return self._sse({
            "type": "orchestrator.steward_decision",
            "decision": decision.to_payload(),
            "routeType": decision.route_type,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "selectedAgents": [
                {"id": agent.id, "name": agent.name}
                for agent in decision.selected_agents
            ],
            "taskBrief": decision.task_brief,
            "riskLevel": decision.risk_level,
            "token": "",
            "done": False,
        })

    async def _member_agents(self, session_id: str) -> list[AgentConfig]:
        rows = await self.db.execute(
            select(AgentConfig).join(
                SessionMember, SessionMember.agent_config_id == AgentConfig.id,
            ).where(
                SessionMember.session_id == session_id,
                AgentConfig.is_active == True,
            )
        )
        agents = list(rows.scalars().all())
        if any((agent.primary_skill or "") == "orchestrator_planner" for agent in agents):
            return agents
        fallback = await self.db.execute(
            select(AgentConfig).where(
                AgentConfig.primary_skill == "orchestrator_planner",
                AgentConfig.is_active == True,
            ).limit(1)
        )
        orchestrator = fallback.scalars().first()
        if orchestrator:
            agents.append(orchestrator)
        return agents

    async def _persist_system_notice(self, session: DBSession, session_id: str, content: str) -> str:
        message_id = f"msg_system_{uuid.uuid4().hex}"
        self.db.add(DBMessage(
            id=message_id,
            session_id=session_id,
            role="system",
            content=content,
            content_type="text",
            source_type="system",
            source_name="运行控制",
        ))
        session.updated_at = china_now()
        SessionService.increment_unread(session, 1)
        await self.db.commit()
        return message_id

    async def _run_was_cancelled(self, run_id: str) -> bool:
        run = await RunService(self.db, event_bus=self.event_bus).get_run(run_id)
        return run.status in {"cancelling", "cancelled"}

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
        return None

    @staticmethod
    def _orchestrator(agents: list[AgentConfig]) -> AgentConfig | None:
        for agent in agents:
            if (agent.primary_skill or "") == "orchestrator_planner":
                return agent
        return None

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

    async def _runtime_events_for_executor_event(
        self,
        run_service: RunService,
        run_id: str,
        run_tasks: dict[str, str],
        ev,
        msg_ids: dict[str, str],
        session_id: str,
    ):
        call_key = self._event_key(ev)
        task_id = run_tasks.get(call_key)
        if not task_id:
            return
        message_id = msg_ids.get(call_key)
        if ev.event_type == "agent.process.started":
            task = await run_service.mark_task_status(
                task_id,
                "running",
                message_id=message_id,
            )
            yield self._task_status_changed(run_id, task)
            process_id = ev.metadata.get("processId")
            if process_id:
                await run_service.bind_process(
                    run_id=run_id,
                    task_id=task_id,
                    session_id=session_id,
                    agent_id=ev.agent_id,
                    message_id=message_id,
                    process_id=process_id,
                )
            run = await run_service.mark_run_status(
                run_id,
                "running",
                current_message_id=message_id,
            )
            yield self._run_status_changed(run)
        elif ev.event_type in {"agent.process.completed", "agent.process.turn_completed"}:
            process_id = ev.metadata.get("processId")
            exit_code = ev.metadata.get("exitCode")
            if process_id:
                await run_service.complete_process(
                    str(process_id),
                    exit_code=exit_code if isinstance(exit_code, int) else None,
                )
        elif ev.done:
            status = "failed" if ev.error else "completed"
            task = await run_service.mark_task_status(
                task_id,
                status,
                message_id=message_id,
                metadata_patch={"error": ev.error} if ev.error else None,
            )
            yield self._task_status_changed(run_id, task)

    def _run_status_changed(self, run) -> str:
        return self._sse({
            "type": "run.status_changed",
            "runId": run.id,
            "sessionId": run.session_id,
            "status": run.status,
            "updatedAt": run.updated_at.isoformat() if run.updated_at else "",
            "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
            "token": "",
            "done": False,
        })

    def _task_status_changed(self, run_id: str, task) -> str:
        return self._sse({
            "type": "task.status_changed",
            "runId": run_id,
            "taskId": task.id,
            "sessionId": task.session_id,
            "status": task.status,
            "task": task_to_read(task).model_dump(by_alias=True, mode="json"),
            "token": "",
            "done": False,
        })

    def _approval_created(self, checkpoint) -> str:
        return self._sse({
            "type": "approval.created",
            "checkpointId": checkpoint.id,
            "runId": checkpoint.run_id,
            "taskId": checkpoint.task_id,
            "sessionId": checkpoint.session_id,
            "messageId": checkpoint.message_id,
            "artifactId": checkpoint.artifact_id,
            "approval": approval_to_read(checkpoint).model_dump(by_alias=True, mode="json"),
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
    def _plan_content_for_steward_decision(content: str, decision: StewardAgentDecision) -> str:
        if decision.route_type != "mini_collab":
            return content
        selected = "、".join(f"@{agent.name}" for agent in decision.selected_agents) or "管家选择的 Agent"
        task_brief = decision.task_brief.strip() or content.strip()
        return (
            f"{content.strip()}\n\n"
            "[调度器管家预判]\n"
            "route_type=mini_collab。不要直接启动多个 Agent 执行；请复用 plan-first DAG 契约，"
            "生成一份小型 draft plan，等待用户确认后再由 Scheduler 执行。\n"
            f"候选协作 Agent: {selected}\n"
            f"任务摘要: {task_brief}\n"
            "计划约束: 任务数量控制在 2-3 个；优先按上述 Agent 顺序和职责分配；"
            "每个任务都要写清 goal、expected_outputs、acceptance_criteria 和 depends_on；"
            "前序 Agent 只交付本节点产物与交接说明，不代做下游 Agent 的职责。"
        )

    @staticmethod
    def _call_key(agent_id: str, task: str | None, phase: int | None) -> str:
        return f"{agent_id}:{phase if phase is not None else 0}:{task or 'primary'}"

    @classmethod
    def _event_key(cls, ev) -> str:
        return cls._call_key(ev.agent_id, ev.metadata.get("task"), ev.metadata.get("phase"))

    @classmethod
    def _merge_agent_metadata(cls, by_key: dict[str, dict], ev) -> None:
        if not ev.agent_id or not isinstance(ev.metadata, dict):
            return
        key = cls._event_key(ev)
        target = by_key.setdefault(key, {})
        for name in (
            "agentType",
            "cliTool",
            "workspacePath",
            "workspaceSnapshotId",
            "snapshotError",
            "engineSessionPolicy",
            "engineSession",
            "processId",
            "token_count",
        ):
            value = ev.metadata.get(name)
            if value is not None:
                target[name] = value
        runtime = ev.metadata.get("engineRuntime")
        if isinstance(runtime, dict):
            current = target.get("engineRuntime") if isinstance(target.get("engineRuntime"), dict) else {}
            target["engineRuntime"] = {**current, **runtime}

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
