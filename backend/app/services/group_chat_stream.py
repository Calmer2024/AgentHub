"""群聊唯一协作入口：直接回合或 Orchestrator 管理的静态 DAG。"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentConfig, Session as DBSession, SessionMember
from .group_direct_turn import GroupDirectTurn
from .orchestrator_plan_chat import OrchestratorPlanChat
from .orchestrator_plan_service import OrchestratorPlanService
from .orchestrator_execution import execution_registry
from .orchestrator_steward_chat import OrchestratorStewardChat, StewardAgentDecision
from .project_service import ProjectNotFoundError, ProjectService
from .run_service import RunService


class GroupChatStream:
    """群聊只保留 direct_turn 与 orchestrated_run 两种执行模型。"""

    def __init__(
        self,
        db: AsyncSession,
        event_bus=None,
        *,
        plan_chat: OrchestratorPlanChat | None = None,
        steward_chat: OrchestratorStewardChat | None = None,
        direct_turn: GroupDirectTurn | None = None,
        workspace_path_resolver: Callable[[str], str | Awaitable[str]] | None = None,
    ):
        self.db = db
        self.event_bus = event_bus
        self._plan_chat = plan_chat or OrchestratorPlanChat(db)
        self._steward_chat = steward_chat or OrchestratorStewardChat(db, event_bus=event_bus)
        self._direct_turn = direct_turn or GroupDirectTurn(db, event_bus=event_bus)
        self._workspace_path_resolver = workspace_path_resolver

    async def send(
        self,
        session_id: str,
        content: str,
        mentions: list[str] | None,
        history: list[dict],
        pinned_message_ids: list[str],
        session: DBSession,
        run_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        members = await self._member_agents(session_id)
        workers = [agent for agent in members if not self._is_orchestrator(agent)]
        orchestrator = next((agent for agent in members if self._is_orchestrator(agent)), None)
        if not workers:
            await self._fail_run(run_id)
            yield self._err("该群聊没有可用的 Worker Agent")
            return
        try:
            workspace_path = await self._workspace_path(session_id)
        except ProjectNotFoundError:
            await self._fail_run(run_id)
            yield self._err("当前会话未绑定项目，无法启动 CLI Agent")
            return

        mention_ids = list(dict.fromkeys(mentions or []))
        mentioned_workers = [agent for agent in workers if agent.id in mention_ids]
        orchestrator_mentioned = orchestrator is not None and orchestrator.id in mention_ids

        if len(mention_ids) == 1 and len(mentioned_workers) == 1:
            revision = await execution_registry.request_worker_revision(
                session_id=session_id,
                agent_id=mentioned_workers[0].id,
                feedback=content,
                run_id=run_id,
            )
            if revision is None:
                persisted = await OrchestratorPlanService(self.db).latest_execution_snapshot(session_id)
                if persisted is not None:
                    execution_registry.restore_execution(persisted)
                    revision = await execution_registry.request_worker_revision(
                        session_id=session_id,
                        agent_id=mentioned_workers[0].id,
                        feedback=content,
                        run_id=run_id,
                    )
            if revision is not None:
                yield self._sse({
                    "type": "orchestrator.worker_revision_started",
                    "sessionId": session_id,
                    "executionId": revision["executionId"],
                    "agentId": mentioned_workers[0].id,
                    "agentName": mentioned_workers[0].name,
                    "token": "",
                    "done": False,
                })
                yield self._sse({
                    "messageId": None,
                    "token": "",
                    "done": True,
                })
                return
            async for item in self._direct_turn.send(
                session=session,
                content=content,
                history=history,
                workspace_path=workspace_path,
                agent=mentioned_workers[0],
                run_id=run_id,
                pinned_message_ids=pinned_message_ids,
                goal=content,
                source="explicit_mention",
            ):
                yield item
            return

        if orchestrator is None:
            await self._fail_run(run_id)
            yield self._err("该群聊缺少项目Leader，无法进行协作调度")
            return

        if len(mentioned_workers) >= 2 or orchestrator_mentioned:
            scope = mentioned_workers or workers
            async for item in self._plan_chat.send(
                session_id=session_id,
                content=content,
                history=history,
                workspace_path=workspace_path,
                orchestrator_agent=orchestrator,
                member_agents=[orchestrator, *scope],
                run_id=run_id,
                pinned_message_ids=pinned_message_ids,
            ):
                yield item
            return

        decision: StewardAgentDecision | None = None
        steward_message_id = ""
        steward_error = None
        async for item in self._steward_chat.stream(
            session=session,
            content=content,
            history=history,
            workspace_path=workspace_path,
            orchestrator_agent=orchestrator,
            member_agents=members,
            run_id=run_id,
            pinned_message_ids=pinned_message_ids,
        ):
            steward_message_id = item.message_id
            steward_error = item.error or steward_error
            if item.decision:
                decision = item.decision
                yield self._decision_event(decision)
            yield item.sse

        if steward_error or decision is None:
            await self._fail_run(run_id)
            return
        if decision.route_type == "context_only":
            await self._complete_run(run_id, steward_message_id)
            return
        if decision.route_type == "direct_turn":
            if len(decision.selected_agents) != 1:
                await self._fail_run(run_id)
                yield self._err("项目Leader没有为直接回合选择唯一 Agent")
                return
            async for item in self._direct_turn.send(
                session=session,
                content=content,
                history=history,
                workspace_path=workspace_path,
                agent=decision.selected_agents[0],
                run_id=run_id,
                pinned_message_ids=pinned_message_ids,
                goal=decision.task_brief or content,
                source="orchestrator_route",
            ):
                yield item
            return

        scope = decision.selected_agents or workers
        async for item in self._plan_chat.send(
            session_id=session_id,
            content=content,
            history=history,
            workspace_path=workspace_path,
            orchestrator_agent=orchestrator,
            member_agents=[orchestrator, *scope],
            run_id=run_id,
            pinned_message_ids=pinned_message_ids,
        ):
            yield item

    async def _member_agents(self, session_id: str) -> list[AgentConfig]:
        result = await self.db.execute(
            select(AgentConfig)
            .join(SessionMember, SessionMember.agent_config_id == AgentConfig.id)
            .where(SessionMember.session_id == session_id, AgentConfig.is_active == True)
            .order_by(SessionMember.joined_at.asc(), SessionMember.agent_config_id.asc())
        )
        return list(result.scalars().all())

    async def _workspace_path(self, session_id: str) -> str:
        if self._workspace_path_resolver:
            value = self._workspace_path_resolver(session_id)
            if inspect.isawaitable(value):
                value = await value
            return str(value)
        return await ProjectService(self.db).get_workspace_path_for_session(session_id)

    async def _fail_run(self, run_id: str | None) -> None:
        if run_id:
            await RunService(self.db, event_bus=self.event_bus).mark_run_status(run_id, "failed")

    async def _complete_run(self, run_id: str | None, message_id: str) -> None:
        if run_id:
            await RunService(self.db, event_bus=self.event_bus).mark_run_status(
                run_id,
                "completed",
                current_message_id=message_id,
            )

    @staticmethod
    def _is_orchestrator(agent: AgentConfig) -> bool:
        return (agent.primary_skill or "") == "orchestrator_planner"

    @staticmethod
    def _decision_event(decision: StewardAgentDecision) -> str:
        return GroupChatStream._sse({
            "type": "orchestrator.route_decided",
            "routeType": decision.route_type,
            "reason": decision.reason,
            "selectedAgents": [
                {"id": agent.id, "name": agent.name}
                for agent in decision.selected_agents
            ],
            "taskBrief": decision.task_brief,
            "token": "",
            "done": False,
        })

    @staticmethod
    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @staticmethod
    def _err(message: str) -> str:
        return GroupChatStream._sse({"token": "", "done": True, "error": message})
