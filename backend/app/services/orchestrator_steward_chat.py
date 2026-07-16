"""可见项目 Leader 管家回合。

群聊无 @ 消息必须交给真实 Orchestrator Agent 判断分流：
context_only / single_agent / direct_dialog / mini_collab / draft_plan。这里不做隐藏规则路由，
只负责把调度器 Agent 的判断过程尽早流式暴露给前端。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..domain.orchestrator_plan import extract_json_object
from ..models import AgentConfig, Message as DBMessage, Session as DBSession
from .cli_agent_service import CliAgentService
from .cli_session_runtime import (
    current_turn_message,
    mark_pinned_messages,
    merge_runtime_process_metadata,
    prepare_cli_session_runtime,
    remember_assigned_engine_session_if_needed,
    remember_engine_session_from_metadata,
)
from .run_service import RunNotFoundError, RunService, run_to_read, task_to_read
from .session_service import SessionService


StewardRouteType = Literal["context_only", "single_agent", "direct_dialog", "mini_collab", "draft_plan"]


@dataclass(frozen=True)
class StewardAgentDecision:
    """项目 Leader 给出的无 @ 路由决策。"""

    route_type: StewardRouteType
    reply: str
    reason: str = ""
    selected_agents: list[AgentConfig] = field(default_factory=list)
    task_brief: str = ""
    confidence: float = 0.0
    requires_approval: bool = False
    risk_level: str = "low"
    raw_output: str = ""

    def to_payload(self) -> dict:
        return {
            "routeType": self.route_type,
            "confidence": self.confidence,
            "reason": self.reason,
            "selectedAgents": [
                {"id": agent.id, "name": agent.name}
                for agent in self.selected_agents
            ],
            "taskBrief": self.task_brief,
            "requiresApproval": self.requires_approval,
            "riskLevel": self.risk_level,
            "intent": "orchestrator_steward",
            "requiredTags": [],
            "reply": self.reply,
        }


@dataclass(frozen=True)
class StewardStreamItem:
    """管家流中的一个 SSE 片段，最后一个片段携带决策。"""

    sse: str
    message_id: str
    decision: StewardAgentDecision | None = None
    error: str | None = None
    completed: bool = False


class OrchestratorStewardChat:
    """把无 @ 群聊输入交给可见 Orchestrator Agent 做轻量分流。"""

    def __init__(self, db: AsyncSession, event_bus=None, cli_agents: CliAgentService | None = None):
        self.db = db
        self.event_bus = event_bus
        self._cli_agents = cli_agents or CliAgentService(event_bus=event_bus)

    async def stream(
        self,
        *,
        session: DBSession,
        content: str,
        history: list[dict],
        workspace_path: str,
        orchestrator_agent: AgentConfig,
        member_agents: list[AgentConfig],
        run_id: str | None = None,
        pinned_message_ids: list[str] | None = None,
    ):
        message_id = str(uuid.uuid4())
        call_key = f"{orchestrator_agent.id}:0:steward"
        run_service = RunService(self.db, event_bus=self.event_bus) if run_id else None
        task_id: str | None = None

        if run_service and run_id:
            run = await run_service.mark_run_status(
                run_id,
                "running",
                current_message_id=message_id,
            )
            yield StewardStreamItem(self._run_status_changed(run), message_id)
            task = await run_service.create_task(
                run,
                agent_id=orchestrator_agent.id,
                name="steward",
                role="planner",
                phase=0,
                status="running",
                metadata={"steward": True, "label": "调度器判断"},
            )
            task_id = task.id
            yield StewardStreamItem(self._task_status_changed(run_id, task), message_id)

        yield StewardStreamItem(
            self._sse({
                "type": "agent.start",
                "agentId": orchestrator_agent.id,
                "agentName": orchestrator_agent.name,
                "messageId": message_id,
                "role": "planner",
                "phase": 0,
                "task": "steward",
                "callKey": call_key,
            }),
            message_id,
        )
        yield StewardStreamItem(
            self._agent_progress(
                orchestrator_agent,
                message_id,
                call_key,
                "项目Leader正在判断该记录上下文、分派 Agent，还是生成计划...",
            ),
            message_id,
        )

        raw_output = ""
        prompt = self._build_prompt(content, member_agents, orchestrator_agent.id)
        exit_code: int | None = None
        error_text: str | None = None
        prompt_messages = [
            *mark_pinned_messages(history, pinned_message_ids),
            current_turn_message(prompt),
        ]
        cli_runtime = await prepare_cli_session_runtime(
            db=self.db,
            cli_agents=self._cli_agents,
            session_id=session.id,
            agent=orchestrator_agent,
            workspace_path=workspace_path,
            messages=prompt_messages,
            pinned_message_ids=pinned_message_ids,
            process_scope="one_group_session_agent_one_process",
            turn_isolation="session_agent_lock",
        )
        metadata_extra = dict(cli_runtime.metadata)
        engine_session_remembered = False

        async for event in self._cli_agents.stream(
            agent=orchestrator_agent,
            session_id=session.id,
            runtime_session_id=cli_runtime.runtime_session_id,
            workspace_path=workspace_path,
            messages=cli_runtime.messages,
            system_prompt=orchestrator_agent.system_prompt or "",
            engine_session_id=cli_runtime.engine_invocation.engine_session_id,
            engine_session_mode=cli_runtime.engine_invocation.mode,
            persistent_process=cli_runtime.supports_persistent_process,
        ):
            if run_service and run_id and await _run_is_cancelled(run_service, run_id):
                if task_id:
                    task = await run_service.mark_task_status(
                        task_id,
                        "cancelled",
                        message_id=message_id,
                    )
                    yield StewardStreamItem(self._task_status_changed(run_id, task), message_id)
                return

            if event.type == "agent.metadata":
                engine_session_remembered = await remember_engine_session_from_metadata(
                    db=self.db,
                    runtime=cli_runtime,
                    session_id=session.id,
                    agent=orchestrator_agent,
                    workspace_path=str(cli_runtime.metadata.get("workspacePath") or workspace_path),
                    event_metadata=event.metadata,
                ) or engine_session_remembered
                metadata_extra.update(cli_runtime.metadata)
                continue

            if event.type == "agent.process.started":
                metadata_extra["processId"] = event.process_id
                merge_runtime_process_metadata(metadata_extra, event.metadata)
                if run_service and run_id and task_id and event.process_id:
                    await run_service.bind_process(
                        run_id=run_id,
                        task_id=task_id,
                        session_id=session.id,
                        agent_id=orchestrator_agent.id,
                        message_id=message_id,
                        process_id=event.process_id,
                    )
                yield StewardStreamItem(
                    self._process_started(orchestrator_agent, message_id, call_key, event),
                    message_id,
                )
                continue

            if event.type == "agent.output":
                if event.chunk_type == "progress":
                    yield StewardStreamItem(
                        self._agent_progress(
                            orchestrator_agent,
                            message_id,
                            call_key,
                            event.chunk,
                            process_id=event.process_id,
                        ),
                        message_id,
                    )
                    continue
                if event.chunk_type in {"text", "artifact_signal"}:
                    raw_output += event.chunk
                continue

            if event.type == "interactive_prompt":
                yield StewardStreamItem(
                    self._interactive_prompt(orchestrator_agent, message_id, call_key, session.id, event),
                    message_id,
                )
                continue

            if event.type in {"agent.process.timeout", "error"}:
                error_text = event.error or "调度器执行失败"
                raw_output = raw_output or error_text
                break

            if event.type in {"agent.process.completed", "agent.process.turn_completed"}:
                exit_code = event.exit_code
                if event.type == "agent.process.turn_completed":
                    merge_runtime_process_metadata(metadata_extra, {
                        **(event.metadata or {}),
                        "turnCompleted": True,
                        "processKeptAlive": True,
                    })
                if run_service and event.process_id:
                    await run_service.complete_process(
                        event.process_id,
                        exit_code=exit_code if isinstance(exit_code, int) else None,
                    )
                yield StewardStreamItem(
                    self._process_completed(orchestrator_agent, message_id, call_key, event),
                    message_id,
                )

        engine_session_remembered = await remember_assigned_engine_session_if_needed(
            db=self.db,
            runtime=cli_runtime,
            session_id=session.id,
            agent=orchestrator_agent,
            workspace_path=str(cli_runtime.metadata.get("workspacePath") or workspace_path),
            remembered=engine_session_remembered,
            metadata={"lastGroupTask": "steward"},
        )
        if engine_session_remembered:
            metadata_extra.update(cli_runtime.metadata)

        if run_service and run_id and await _run_is_cancelled(run_service, run_id):
            if task_id:
                task = await run_service.mark_task_status(
                    task_id,
                    "cancelled",
                    message_id=message_id,
                )
                yield StewardStreamItem(self._task_status_changed(run_id, task), message_id)
            return

        decision = self._parse_decision(raw_output, member_agents, orchestrator_agent.id, content)
        visible = decision.reply if decision else (raw_output.strip() or "我已收到，但暂时无法判断下一步。")
        await self._persist_message(
            session=session,
            message_id=message_id,
            agent=orchestrator_agent,
            content=visible,
            decision=decision,
            raw_output=raw_output,
            metadata_extra=metadata_extra,
        )
        if run_service and run_id and task_id:
            task_status = "failed" if error_text else "completed"
            task = await run_service.mark_task_status(task_id, task_status, message_id=message_id)
            yield StewardStreamItem(self._task_status_changed(run_id, task), message_id)

        yield StewardStreamItem(
            self._agent_output(orchestrator_agent, message_id, call_key, visible),
            message_id,
        )
        yield StewardStreamItem(
            self._sse({
                "agentId": orchestrator_agent.id,
                "agentName": orchestrator_agent.name,
                "done": True,
                "messageId": message_id,
                "role": "planner",
                "phase": 0,
                "task": "steward",
                "callKey": call_key,
                "token": f"[调度器执行失败: {error_text}]" if error_text else "",
                "error": error_text or "",
            }),
            message_id,
            decision=decision,
            error=error_text,
            completed=True,
        )

    async def _persist_message(
        self,
        *,
        session: DBSession,
        message_id: str,
        agent: AgentConfig,
        content: str,
        decision: StewardAgentDecision | None,
        raw_output: str,
        metadata_extra: dict | None = None,
    ) -> None:
        metadata = {
            **(metadata_extra or {}),
            "isCollaborating": True,
            "agentRole": "planner",
            "taskName": "steward",
            "phase": 0,
            "orchestratorStewardRawOutput": raw_output,
        }
        if decision:
            metadata["stewardDecision"] = decision.to_payload()
        self.db.add(DBMessage(
            id=message_id,
            session_id=session.id,
            role="assistant",
            content=content,
            content_type="text",
            agent_name=agent.name,
            source_type="agent",
            source_id=agent.id,
            source_name=agent.name,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ))
        session.updated_at = china_now()
        SessionService.increment_unread(session, 1)
        await self.db.commit()

    def _parse_decision(
        self,
        raw_output: str,
        member_agents: list[AgentConfig],
        orchestrator_id: str,
        content: str,
    ) -> StewardAgentDecision | None:
        try:
            data = extract_json_object(raw_output)
        except ValueError:
            return None

        route_type = str(data.get("route_type") or data.get("routeType") or "")
        if route_type not in {"context_only", "single_agent", "direct_dialog", "mini_collab", "draft_plan"}:
            return None

        candidates = {
            agent.id: agent
            for agent in member_agents
            if agent.id != orchestrator_id and (agent.primary_skill or "") != "orchestrator_planner"
        }
        selected_ids = data.get("selected_agent_ids") or data.get("selectedAgentIds") or []
        if not isinstance(selected_ids, list):
            selected_ids = []
        selected_agents = [
            candidates[str(agent_id)]
            for agent_id in selected_ids
            if str(agent_id) in candidates
        ]
        reply = str(data.get("reply") or data.get("message") or "").strip()
        if not reply:
            reply = self._default_reply(route_type, selected_agents)
        return StewardAgentDecision(
            route_type=route_type,  # type: ignore[arg-type]
            reply=reply,
            reason=str(data.get("reason") or ""),
            selected_agents=selected_agents,
            task_brief=str(data.get("task_brief") or data.get("taskBrief") or content.strip()),
            confidence=_float_or_zero(data.get("confidence")),
            requires_approval=bool(data.get("requires_approval") or data.get("requiresApproval")),
            risk_level=str(data.get("risk_level") or data.get("riskLevel") or "low"),
            raw_output=raw_output,
        )

    @staticmethod
    def _default_reply(route_type: str, selected_agents: list[AgentConfig]) -> str:
        if route_type == "context_only":
            return "已记录到群聊上下文，我不会启动执行。"
        if route_type == "draft_plan":
            return "这个需求更适合先生成计划，我会先给出 draft plan，确认后再执行。"
        if route_type == "direct_dialog":
            if selected_agents:
                return f"可以，我先请 @{selected_agents[0].name} 出来和你连续对齐。"
            return "可以，我先切到单独对话模式。"
        if route_type == "mini_collab":
            names = "、".join(f"@{agent.name}" for agent in selected_agents)
            suffix = f"：{names}" if names else ""
            return f"我会先生成一份小型协作计划{suffix}，确认后再执行。"
        if selected_agents:
            names = "、".join(f"@{agent.name}" for agent in selected_agents)
            return f"我会先分派给 {names} 处理。"
        return "我已判断下一步，但还缺少可分派的 Agent。"

    @staticmethod
    def _build_prompt(content: str, member_agents: list[AgentConfig], orchestrator_id: str) -> str:
        agents = []
        for agent in member_agents:
            if agent.id == orchestrator_id or (agent.primary_skill or "") == "orchestrator_planner":
                continue
            agents.append({
                "id": agent.id,
                "name": agent.name,
                "primary_skill": agent.primary_skill or "general_coding",
                "auxiliary_skills": agent.auxiliary_skills,
                "description": agent.description or "",
            })
        schema = {
            "route_type": "context_only | single_agent | direct_dialog | mini_collab | draft_plan",
            "reply": "给用户看的简短中文回复",
            "reason": "内部判断原因",
            "selected_agent_ids": ["agent_id"],
            "task_brief": "给后续 Agent 或计划使用的任务摘要",
            "confidence": 0.0,
            "requires_approval": False,
            "risk_level": "low | medium | high",
        }
        return (
            "你是 AgentHub 群聊中的项目Leader。用户没有 @ 任何成员时，"
            "这条消息默认就是发给你的。你必须先作为可见群聊成员判断下一步。\n\n"
            "只输出一个 JSON 对象，不要输出 Markdown，不要修改文件，不要执行子任务。\n"
            "四档含义（当前已扩展 direct_dialog 分流档位）：\n"
            "- context_only：只是背景、约束、偏好或记忆；回复用户已记录，不启动 Agent。\n"
            "- single_agent：适合一个 Agent 轻量回答或处理；selected_agent_ids 只填 1 个。\n"
            "- direct_dialog：用户想直接和某个群成员连续交流、访谈、澄清，或明确不想走任务/计划；"
            "selected_agent_ids 只填 1 个；后续用户无 @ 消息会继续交给该 Agent，直到用户通过结构化操作结束或交接。\n"
            "- mini_collab：适合 2-3 个 Agent 协作，但仍需要先生成小型 draft plan；selected_agent_ids 填 2-3 个。\n"
            "- draft_plan：多阶段、高成本、可能写多文件或需要确认范围；先生成 draft plan。\n\n"
            "重要：如果一句话同时包含约束和明确需求，要按明确需求判断，不能只因为有"
            "“用中文、先别急着写代码、补充一下”等词就判成 context_only。"
            "如果用户想找产品经理、前端、后端、测试等角色进行单独交流、访谈或需求对齐，应选择 direct_dialog。"
            "如果用户只是让某个 Agent 一次性回答一个轻量问题，才选择 single_agent。"
            "如果用户说先让 A 再让 B，选择 mini_collab，并按用户语序填写 selected_agent_ids；"
            "mini_collab 后续也会进入 plan-first，不会直接启动这些 Agent。\n\n"
            "候选 Agent：\n"
            f"{json.dumps(agents, ensure_ascii=False, indent=2)}\n\n"
            "输出结构：\n"
            f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            f"用户消息：\n{content.strip()}\n"
        )

    def _agent_output(self, agent: AgentConfig, message_id: str, call_key: str, text: str) -> str:
        return self._sse({
            "type": "agent.output",
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "role": "planner",
            "phase": 0,
            "task": "steward",
            "callKey": call_key,
            "chunk": text,
            "chunkType": "text",
            "token": text,
            "done": False,
        })

    def _agent_progress(
        self,
        agent: AgentConfig,
        message_id: str,
        call_key: str,
        text: str,
        process_id: str | None = None,
    ) -> str:
        return self._sse({
            "type": "agent.output",
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "role": "planner",
            "phase": 0,
            "task": "steward",
            "callKey": call_key,
            "chunk": text,
            "chunkType": "progress",
            "processId": process_id,
            "token": "",
            "done": False,
        })

    def _process_started(self, agent: AgentConfig, message_id: str, call_key: str, event) -> str:
        return self._sse({
            "type": "agent.process.started",
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "role": "planner",
            "phase": 0,
            "task": "steward",
            "callKey": call_key,
            "processId": event.process_id,
            "metadata": {"trace": event.trace} if event.trace else {},
            "token": "",
            "done": False,
        })

    def _process_completed(self, agent: AgentConfig, message_id: str, call_key: str, event) -> str:
        return self._sse({
            "type": "agent.process.completed",
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "role": "planner",
            "phase": 0,
            "task": "steward",
            "callKey": call_key,
            "processId": event.process_id,
            "exitCode": event.exit_code,
            "metadata": {"trace": event.trace} if event.trace else {},
            "token": "",
            "done": False,
        })

    def _interactive_prompt(
        self,
        agent: AgentConfig,
        message_id: str,
        call_key: str,
        session_id: str,
        event,
    ) -> str:
        return self._sse({
            "type": "interactive_prompt",
            "agentId": agent.id,
            "agentName": agent.name,
            "messageId": message_id,
            "role": "planner",
            "phase": 0,
            "task": "steward",
            "callKey": call_key,
            "sessionId": session_id,
            "processId": event.process_id,
            "content": event.chunk,
            "promptType": event.prompt_type,
            "token": "",
            "done": False,
        })

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

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _float_or_zero(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


async def _run_is_cancelled(run_service: RunService, run_id: str) -> bool:
    try:
        run = await run_service.get_run(run_id)
    except RunNotFoundError:
        return False
    return run.status in {"cancelling", "cancelled"}
