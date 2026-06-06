"""Chat flow for Orchestrator Agent draft plans and plan approval."""

import json
import uuid
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.cli_trace import trace_text
from ..domain.orchestrator_plan import (
    build_plan_followup_prompt,
    build_plan_prompt,
    extract_json_object,
    normalize_plan,
    validate_plan,
    visualize_mermaid,
)
from ..models import AgentConfig, Message as DBMessage, SessionMember
from .cli_agent_service import CliAgentService
from .execution_trace import ExecutionTraceBuilder, merge_trace_metadata
from .orchestrator_execution import PlanExecutionError, execution_registry


class OrchestratorPlanChat:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def send(
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
        latest_plan = await self._latest_orchestrator_plan(session_id)
        is_followup = latest_plan is not None
        prompt = (
            build_plan_followup_prompt(content, candidate_agents, latest_plan)
            if latest_plan
            else build_plan_prompt(content, candidate_agents)
        )
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
                if not is_followup:
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

            if event.type == "interactive_prompt":
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

            if event.type == "agent.process.completed":
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

            if event.type == "error":
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
            if is_followup and parsed.get("action") == "approve_plan":
                async for item in self._approve_latest_plan(
                    session_id=session_id,
                    message_id=message_id,
                    agent=orchestrator_agent,
                    plan=latest_plan,
                    action=parsed,
                    metadata=metadata,
                    trace=trace,
                ):
                    yield item
                return
            plan = normalize_plan(parsed)
            validation = validate_plan(plan, {str(agent["id"]) for agent in candidate_agents})
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
        if is_followup and visible:
            yield self._sse({
                "type": "agent.output",
                "agentId": orchestrator_agent.id,
                "agentName": orchestrator_agent.name,
                "token": visible,
                "messageId": message_id,
                "role": "planner",
                "phase": 0,
                "task": "draft plan",
                "callKey": call_key,
                "processId": process_id,
                "chunk": visible,
                "chunkType": "text",
                "done": False,
            })
        yield self._sse({"token": "", "done": True, "messageId": message_id})

    async def _approve_latest_plan(
        self,
        *,
        session_id: str,
        message_id: str,
        agent: AgentConfig,
        plan: dict,
        action: dict,
        metadata: dict,
        trace: ExecutionTraceBuilder,
    ) -> AsyncGenerator[str, None]:
        try:
            execution = execution_registry.create_execution(
                session_id=session_id,
                plan=plan,
                active_agent_ids={member.id for member in await self._member_agents(session_id)},
            )
        except PlanExecutionError as exc:
            content = "计划暂时无法进入执行：\n" + "\n".join(f"- {error}" for error in exc.errors)
            await self._persist_orchestrator_message(
                session_id=session_id,
                message_id=message_id,
                agent=agent,
                content=content,
                metadata=merge_trace_metadata({
                    **metadata,
                    "orchestratorAction": action,
                    "orchestratorExecutionError": {
                        "errors": exc.errors,
                        "warnings": exc.warnings,
                    },
                }, trace),
            )
            yield self._sse({
                "type": "agent.output",
                "agentId": agent.id,
                "agentName": agent.name,
                "token": content,
                "messageId": message_id,
                "role": "planner",
                "phase": 0,
                "task": "approve plan",
                "callKey": self._call_key(agent.id, "approve plan", 0),
                "chunk": content,
                "chunkType": "text",
                "done": False,
            })
            yield self._sse({"token": "", "done": True, "messageId": message_id})
            return

        content = (
            f"已确认计划 {execution['planId']}，创建执行 {execution['executionId']}。\n"
            f"模拟 Scheduler 已按 DAG 完成 {len(execution['tasks'])} 个任务。"
        )
        await self._persist_orchestrator_message(
            session_id=session_id,
            message_id=message_id,
            agent=agent,
            content=content,
            metadata=merge_trace_metadata({
                **metadata,
                "orchestratorAction": action,
                "orchestratorExecution": execution,
            }, trace),
        )
        yield self._sse({
            "type": "orchestrator.plan_execution_created",
            "executionId": execution["executionId"],
            "planId": execution["planId"],
            "status": execution["status"],
            "tasks": execution["tasks"],
        })
        yield self._sse({
            "type": "agent.output",
            "agentId": agent.id,
            "agentName": agent.name,
            "token": content,
            "messageId": message_id,
            "role": "planner",
            "phase": 0,
            "task": "approve plan",
            "callKey": self._call_key(agent.id, "approve plan", 0),
            "chunk": content,
            "chunkType": "text",
            "done": False,
        })
        yield self._sse({"token": "", "done": True, "messageId": message_id})

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

    async def _latest_orchestrator_plan(self, session_id: str) -> dict | None:
        rows = await self.db.execute(
            select(DBMessage)
            .where(DBMessage.session_id == session_id, DBMessage.role == "assistant")
            .order_by(DBMessage.created_at.desc(), DBMessage.id.desc())
            .limit(20)
        )
        for message in rows.scalars().all():
            try:
                metadata = json.loads(message.metadata_json or "{}")
            except json.JSONDecodeError:
                continue
            plan_meta = metadata.get("orchestratorPlan")
            if not isinstance(plan_meta, dict):
                continue
            plan = plan_meta.get("normalizedPlan")
            if isinstance(plan, dict):
                return plan
        return None

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

    @staticmethod
    def _call_key(agent_id: str, task: str | None, phase: int | None) -> str:
        return f"{agent_id}:{phase if phase is not None else 0}:{task or 'primary'}"

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    @staticmethod
    def _err(msg: str) -> str:
        return f"data: {json.dumps({'token': '', 'done': True, 'error': msg}, ensure_ascii=False)}\n\n"
