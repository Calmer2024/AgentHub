"""Chat flow for Orchestrator Agent draft plans and plan approval."""

import json
import uuid
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..agents.cli_trace import trace_text
from ..domain.orchestrator_plan import (
    build_plan_followup_prompt,
    build_plan_prompt,
    extract_json_object,
    normalize_plan,
    validate_plan,
    visualize_mermaid,
)
from ..models import AgentConfig, Message as DBMessage, Session as DBSession, SessionMember
from .cli_agent_service import CliAgentService
from .cli_session_runtime import (
    current_turn_message,
    mark_pinned_messages,
    merge_runtime_process_metadata,
    prepare_cli_session_runtime,
    remember_assigned_engine_session_if_needed,
    remember_engine_session_from_metadata,
)
from .execution_trace import ExecutionTraceBuilder, merge_trace_metadata
from .file_change_detector import FileChangeDetector
from .orchestrator_execution import (
    OrchestratorPhaseReviewer,
    PlanExecutionError,
    execution_registry,
)
from .orchestrator_plan_service import OrchestratorPlanNotFoundError, OrchestratorPlanService
from .run_service import RunService, run_to_read, task_to_read


class OrchestratorPlanChat:
    def __init__(
        self,
        db: AsyncSession,
        detector: FileChangeDetector | None = None,
        cli_agents: CliAgentService | None = None,
        execution_task_runner=None,
    ):
        self.db = db
        self._detector = detector or FileChangeDetector()
        self._cli_agents = cli_agents or CliAgentService()
        self._execution_task_runner = execution_task_runner

    async def send(
        self,
        *,
        session_id: str,
        content: str,
        history: list[dict],
        workspace_path: str,
        orchestrator_agent: AgentConfig,
        member_agents: list[AgentConfig],
        run_id: str | None = None,
        pinned_message_ids: list[str] | None = None,
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
        prompt_messages = [
            *mark_pinned_messages(history, pinned_message_ids),
            current_turn_message(prompt),
        ]
        cli_runtime = await prepare_cli_session_runtime(
            db=self.db,
            cli_agents=self._cli_agents,
            session_id=session_id,
            agent=orchestrator_agent,
            workspace_path=workspace_path,
            messages=prompt_messages,
            pinned_message_ids=pinned_message_ids,
            process_scope="one_group_session_agent_one_process",
            turn_isolation="session_agent_lock",
        )
        metadata.update(cli_runtime.metadata)
        engine_session_remembered = False
        workspace_snapshot_id = self._create_workspace_snapshot(workspace_path, "orchestrator-plan")

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

        async for event in self._cli_agents.stream(
            agent=orchestrator_agent,
            session_id=session_id,
            runtime_session_id=cli_runtime.runtime_session_id,
            workspace_path=workspace_path,
            messages=cli_runtime.messages,
            system_prompt=orchestrator_agent.system_prompt or "",
            engine_session_id=cli_runtime.engine_invocation.engine_session_id,
            engine_session_mode=cli_runtime.engine_invocation.mode,
            persistent_process=cli_runtime.supports_persistent_process,
        ):
            process_id = event.process_id or process_id
            if event.type == "agent.metadata":
                engine_session_remembered = await remember_engine_session_from_metadata(
                    db=self.db,
                    runtime=cli_runtime,
                    session_id=session_id,
                    agent=orchestrator_agent,
                    workspace_path=str(cli_runtime.metadata.get("workspacePath") or workspace_path),
                    event_metadata=event.metadata,
                ) or engine_session_remembered
                metadata.update(cli_runtime.metadata)
                continue
            if event.type == "agent.process.started":
                metadata["processId"] = process_id
                merge_runtime_process_metadata(metadata, event.metadata)
                if run_id:
                    async for item in self._bind_planner_runtime(
                        run_id=run_id,
                        session_id=session_id,
                        agent=orchestrator_agent,
                        message_id=message_id,
                        process_id=process_id,
                    ):
                        yield item
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

            if event.type in {"agent.process.completed", "agent.process.turn_completed"}:
                exit_code = event.exit_code
                metadata["exitCode"] = exit_code
                if event.type == "agent.process.turn_completed":
                    merge_runtime_process_metadata(metadata, {
                        **(event.metadata or {}),
                        "turnCompleted": True,
                        "processKeptAlive": True,
                    })
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
                if run_id:
                    async for item in self._mark_run_failed(
                        run_id=run_id,
                        message_id=message_id,
                        error=error,
                    ):
                        yield item
                yield self._err(error)
                return

        engine_session_remembered = await remember_assigned_engine_session_if_needed(
            db=self.db,
            runtime=cli_runtime,
            session_id=session_id,
            agent=orchestrator_agent,
            workspace_path=str(cli_runtime.metadata.get("workspacePath") or workspace_path),
            remembered=engine_session_remembered,
            metadata={"lastGroupTask": "orchestrator_plan"},
        )
        if engine_session_remembered:
            metadata.update(cli_runtime.metadata)

        workspace_changes = self._workspace_changes_since(workspace_path, workspace_snapshot_id)

        try:
            parsed = extract_json_object(parse_output)
            if is_followup:
                action = parsed.get("action")
                if action == "approve_plan":
                    async for item in self._approve_latest_plan(
                        session_id=session_id,
                        message_id=message_id,
                        agent=orchestrator_agent,
                        plan=latest_plan,
                        action=parsed,
                        metadata=metadata,
                        trace=trace,
                        run_id=run_id,
                        history=history,
                    ):
                        yield item
                    return
                if action == "discard_plan":
                    async for item in self._discard_latest_plan(
                        session_id=session_id,
                        message_id=message_id,
                        agent=orchestrator_agent,
                        plan=latest_plan,
                        action=parsed,
                        metadata=metadata,
                        trace=trace,
                        run_id=run_id,
                    ):
                        yield item
                    return
            plan = normalize_plan(parsed)
            validation = validate_plan(plan, {str(agent["id"]) for agent in candidate_agents})
            if workspace_changes:
                validation["ok"] = False
                validation["errors"].append(
                    "项目Leader在 plan-only 阶段写入了工作区文件，请撤销这些变更后重新生成计划"
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
            if run_id:
                async for item in self._mark_run_failed(
                    run_id=run_id,
                    message_id=message_id,
                    error=str(exc),
                ):
                    yield item
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
                "orchestratorWorkspaceChanges": workspace_changes,
                "orchestratorPlan": {
                    "ok": validation["ok"],
                    "normalizedPlan": plan,
                    "validation": validation,
                    "visualization": {"mermaid": visualize_mermaid(plan)},
                }
            }, trace),
        )
        await OrchestratorPlanService(self.db).create_or_update_from_normalized_plan(
            session_id=session_id,
            normalized_plan=plan,
            run_id=run_id,
            orchestrator_agent_id=orchestrator_agent.id,
            agent_scope=[str(item["id"]) for item in candidate_agents],
        )
        if is_followup and latest_plan:
            previous_plan_id = str(latest_plan.get("plan_id") or "")
            next_plan_id = str(plan.get("plan_id") or "")
            if previous_plan_id and previous_plan_id != next_plan_id:
                await self._mark_plan_status(
                    session_id=session_id,
                    plan_id=previous_plan_id,
                    status="revised",
                    action_message_id=message_id,
                )
        if run_id:
            async for item in self._complete_planner_run(
                run_id=run_id,
                message_id=message_id,
            ):
                yield item
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
        run_id: str | None = None,
        history: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        member_agents = await self._member_agents(session_id)
        worker_agents = [
            member for member in member_agents
            if member.id != agent.id and (member.primary_skill or "") != "orchestrator_planner"
        ]
        assigned_scope = {
            str(task.get("assigned_agent_id") or "")
            for task in plan.get("tasks") or []
            if isinstance(task, dict) and task.get("assigned_agent_id")
        }
        active_worker_ids = {member.id for member in worker_agents}
        try:
            execution = execution_registry.create_execution(
                session_id=session_id,
                plan=plan,
                active_agent_ids=assigned_scope & active_worker_ids,
                auto_start=False,
                task_runner=self._execution_task_runner,
                phase_reviewer=OrchestratorPhaseReviewer(
                    AsyncSessionLocal,
                    self._cli_agents,
                ),
                orchestrator_agent_id=agent.id,
                group_context=history,
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
            if run_id:
                async for item in self._mark_run_failed(
                    run_id=run_id,
                    message_id=message_id,
                    error="；".join(exc.errors),
                ):
                    yield item
            yield self._sse({"token": "", "done": True, "messageId": message_id})
            return

        if run_id:
            runtime_task_ids = await self._bind_execution_runtime(
                session_id=session_id,
                execution=execution,
                run_id=run_id,
            )
            execution_registry.bind_runtime(
                execution["executionId"],
                run_id=run_id,
                task_id_by_orchestrator_task_id=runtime_task_ids,
            )
            execution = execution_registry.get_execution(execution["executionId"]) or execution

        content = (
            f"已确认计划 {execution['planId']}，创建执行 {execution['executionId']}。\n"
            f"Scheduler 已启动，{len(execution['tasks'])} 个任务将按 DAG 异步推进。"
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
        await OrchestratorPlanService(self.db).create_or_update_from_normalized_plan(
            session_id=session_id,
            normalized_plan=plan,
            run_id=run_id,
            orchestrator_agent_id=agent.id,
            agent_scope=sorted(assigned_scope),
        )
        await self._mark_plan_status(
            session_id=session_id,
            plan_id=str(plan.get("plan_id") or execution["planId"]),
            status="approved",
            action_message_id=message_id,
        )
        execution_registry.bind_control_message(execution["executionId"], message_id)
        execution_registry.start_execution(execution["executionId"])
        yield self._sse({
            "type": "orchestrator.plan_execution_created",
            "sessionId": session_id,
            "messageId": message_id,
            "executionId": execution["executionId"],
            "planId": execution["planId"],
            "status": execution["status"],
            "tasks": execution["tasks"],
            "runId": execution.get("runId") or run_id,
            "execution": execution,
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

    async def _discard_latest_plan(
        self,
        *,
        session_id: str,
        message_id: str,
        agent: AgentConfig,
        plan: dict,
        action: dict,
        metadata: dict,
        trace: ExecutionTraceBuilder,
        run_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        plan_id = str(action.get("target_plan_id") or plan.get("plan_id") or "")
        reason = str(action.get("reason") or "用户决定不再跟进这版计划")
        content = f"已放弃计划 {plan_id}。后续消息会重新交给调度器管家判断。"
        await self._persist_orchestrator_message(
            session_id=session_id,
            message_id=message_id,
            agent=agent,
            content=content,
            metadata=merge_trace_metadata({
                **metadata,
                "orchestratorAction": {
                    **action,
                    "action": "discard_plan",
                    "target_plan_id": plan_id,
                    "reason": reason,
                },
                "orchestratorPlanState": {
                    "planId": plan_id,
                    "status": "discarded",
                    "reason": reason,
                },
            }, trace),
        )
        await self._mark_plan_status(
            session_id=session_id,
            plan_id=plan_id,
            status="discarded",
            action_message_id=message_id,
        )
        if run_id:
            async for item in self._complete_planner_run(
                run_id=run_id,
                message_id=message_id,
            ):
                yield item
        yield self._sse({
            "type": "agent.output",
            "agentId": agent.id,
            "agentName": agent.name,
            "token": content,
            "messageId": message_id,
            "role": "planner",
            "phase": 0,
            "task": "discard plan",
            "callKey": self._call_key(agent.id, "discard plan", 0),
            "chunk": content,
            "chunkType": "text",
            "done": False,
        })
        yield self._sse({
            "type": "orchestrator.plan_discarded",
            "planId": plan_id,
            "reason": reason,
            "messageId": message_id,
            "token": "",
            "done": False,
        })
        yield self._sse({"token": "", "done": True, "messageId": message_id})

    async def _bind_planner_runtime(
        self,
        *,
        run_id: str,
        session_id: str,
        agent: AgentConfig,
        message_id: str,
        process_id: str,
    ) -> AsyncGenerator[str, None]:
        service = RunService(self.db)
        run = await service.bind_current_message(run_id, message_id)
        await service.bind_process(
            run_id=run_id,
            task_id=None,
            session_id=session_id,
            agent_id=agent.id,
            message_id=message_id,
            process_id=process_id,
        )
        yield self._sse({
            "type": "run.status_changed",
            "runId": run.id,
            "sessionId": run.session_id,
            "status": run.status,
            "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
            "token": "",
            "done": False,
        })

    async def _bind_execution_runtime(
        self,
        *,
        session_id: str,
        execution: dict,
        run_id: str,
    ) -> dict[str, str]:
        session = await self.db.get(DBSession, session_id)
        if not session:
            return {}
        service = RunService(self.db)
        run = await service.mark_run_status(
            run_id,
            "running",
        )
        runtime_task_ids: dict[str, str] = {}
        for task in execution.get("tasks") or []:
            runtime_task = await service.create_task(
                run,
                agent_id=task.get("assignedAgentId"),
                name=f"{task.get('taskId')} · {task.get('title')}",
                role="executor",
                phase=task.get("phase"),
                depends_on=task.get("dependsOn") or [],
                metadata={
                    "executionId": execution["executionId"],
                    "planId": execution["planId"],
                    "orchestratorTaskId": task.get("taskId"),
                    "maxAttempts": int(task.get("maxAttempts") or 3),
                },
            )
            runtime_task_ids[str(task.get("taskId"))] = runtime_task.id
            await self._broadcast_ws(session_id, {
                "type": "task.status_changed",
                "runId": run_id,
                "taskId": runtime_task.id,
                "sessionId": session_id,
                "status": runtime_task.status,
                "task": task_to_read(runtime_task).model_dump(by_alias=True, mode="json"),
                "token": "",
                "done": False,
            })
        await self._broadcast_ws(session_id, {
            "type": "run.status_changed",
            "runId": run.id,
            "sessionId": session_id,
            "status": run.status,
            "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
            "token": "",
            "done": False,
        })
        return runtime_task_ids

    async def _complete_planner_run(
        self,
        *,
        run_id: str,
        message_id: str,
    ) -> AsyncGenerator[str, None]:
        service = RunService(self.db)
        run = await service.mark_run_status(
            run_id,
            "completed",
            current_message_id=message_id,
        )
        yield self._sse({
            "type": "run.status_changed",
            "runId": run.id,
            "sessionId": run.session_id,
            "status": run.status,
            "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
            "token": "",
            "done": False,
        })

    async def _mark_run_failed(
        self,
        *,
        run_id: str,
        message_id: str,
        error: str,
    ) -> AsyncGenerator[str, None]:
        service = RunService(self.db)
        run = await service.mark_run_status(
            run_id,
            "failed",
            current_message_id=message_id,
            reason=error,
        )
        yield self._sse({
            "type": "run.status_changed",
            "runId": run.id,
            "sessionId": run.session_id,
            "status": run.status,
            "run": run_to_read(run).model_dump(by_alias=True, mode="json"),
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
        return list(rows.scalars().all())

    def _create_workspace_snapshot(self, workspace_path: str, label: str) -> str | None:
        try:
            return self._detector.create_snapshot(workspace_path, label).snapshot_id
        except Exception:
            return None

    def _workspace_changes_since(self, workspace_path: str, snapshot_id: str | None) -> list[dict]:
        if not snapshot_id:
            return []
        try:
            return self._detector.diff_from_snapshot(workspace_path, snapshot_id)
        except Exception:
            return []

    async def _latest_orchestrator_plan(self, session_id: str) -> dict | None:
        return await OrchestratorPlanService(self.db).latest_draft(session_id)

    async def has_latest_orchestrator_plan(self, session_id: str) -> bool:
        return await self._latest_orchestrator_plan(session_id) is not None

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

    async def _mark_plan_status(
        self,
        *,
        session_id: str,
        plan_id: str,
        status: str,
        action_message_id: str,
    ) -> None:
        if not plan_id:
            return
        try:
            await OrchestratorPlanService(self.db).update_status(plan_id, status)
        except OrchestratorPlanNotFoundError:
            return
        rows = await self.db.execute(
            select(DBMessage)
            .where(DBMessage.session_id == session_id, DBMessage.role == "assistant")
            .order_by(DBMessage.created_at.desc(), DBMessage.id.desc())
            .limit(30)
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
            if not isinstance(plan, dict) or str(plan.get("plan_id") or "") != plan_id:
                continue
            plan["status"] = status
            plan_meta["normalizedPlan"] = plan
            plan_meta["status"] = status
            plan_meta["resolvedByMessageId"] = action_message_id
            metadata["orchestratorPlan"] = plan_meta
            message.metadata_json = json.dumps(metadata, ensure_ascii=False)
            await self.db.commit()
            return

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
        return {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description or "",
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

    @staticmethod
    async def _broadcast_ws(session_id: str, payload: dict) -> None:
        try:
            from ..infrastructure.realtime import manager as ws_manager
            await ws_manager.broadcast(session_id, payload)
        except Exception:
            pass
