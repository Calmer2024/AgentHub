import json
import asyncio
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.agents.cli_events import CliEvent
from app.models import AgentConfig, Message, Project, Session
from app.services.orchestrator_execution import OrchestratorExecutionRegistry, execution_registry

BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"


async def _wait_execution_completed(test_client, execution_id: str, attempts: int = 20) -> dict:
    latest = None
    for _ in range(attempts):
        lookup = await test_client.get(f"/api/orchestrator/executions/{execution_id}")
        assert lookup.status_code == 200
        latest = lookup.json()
        if latest["status"] in {"completed", "failed"}:
            return latest
        await asyncio.sleep(0.05)
    assert latest is not None
    return latest


async def _wait_execution_status(
    test_client,
    execution_id: str,
    statuses: set[str],
    attempts: int = 30,
) -> dict:
    latest = None
    for _ in range(attempts):
        lookup = await test_client.get(f"/api/orchestrator/executions/{execution_id}")
        assert lookup.status_code == 200
        latest = lookup.json()
        if latest["status"] in statuses:
            return latest
        await asyncio.sleep(0.05)
    assert latest is not None
    return latest


def _agent(agent_id: str, name: str, primary_skill: str) -> AgentConfig:
    cli = _ensure_fixture_cli()
    return AgentConfig(
        id=agent_id,
        name=name,
        description=name,
        system_prompt="",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable=sys.executable,
        init_args=json.dumps([str(cli)]),
        env_vars="{}",
        primary_skill=primary_skill,
        auxiliary_skills=json.dumps(["workspace_editing"], ensure_ascii=False),
        context_policy="workspace_coding",
        is_active=True,
    )


def _ensure_fixture_cli() -> Path:
    script = BACKEND_ROOT / ".test-bin" / "orchestrator_task_fixture.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "import os, re, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "cwd = os.getcwd().replace('\\\\', '/')\n"
        "match = re.search(r'当前任务工作包目录: (.+)', data)\n"
        "task_dir = match.group(1).strip().strip('`') if match else os.getcwd()\n"
        "os.makedirs(task_dir, exist_ok=True)\n"
        "with open(os.path.join(task_dir, 'HANDOFF.md'), 'w', encoding='utf-8') as f:\n"
        "    f.write('# 任务交接\\n\\n已在任务工作包内写入交接副本。\\n')\n"
        "os.makedirs('docs', exist_ok=True)\n"
        "with open(os.path.join('docs', 'orchestrator-deliverable.md'), 'w', encoding='utf-8') as f:\n"
        "    f.write('# 正式交付文档\\n\\n已写入项目 docs 目录。\\n')\n"
        "sys.stdout.buffer.write(f'真实任务输出：cwd={cwd}；正式文档写入 docs/；交接副本写入任务工作包。'.encode('utf-8'))\n"
        "sys.stdout.buffer.flush()\n",
        encoding="utf-8",
    )
    return script


async def _seed_session_with_agents(db_session):
    workspace_path = BACKEND_ROOT / ".test-workspaces" / str(uuid.uuid4())
    workspace_path.mkdir(parents=True, exist_ok=True)
    project = Project(
        id=str(uuid.uuid4()),
        name="调度执行测试项目",
        workspace_path=str(workspace_path),
        status="ready",
    )
    frontend = _agent("agent_frontend_exec", "前端专家", "frontend_engineer")
    backend = _agent("agent_backend_exec", "后端专家", "backend_engineer")
    session = Session(
        id=str(uuid.uuid4()),
        title="调度执行测试会话",
        project_id=project.id,
        mode="group",
    )
    db_session.add_all([project, frontend, backend, session])
    await db_session.commit()
    return session.id


def _valid_plan() -> dict:
    return {
        "plan_id": "plan_exec_001",
        "status": "draft",
        "execution_policy": {
            "mode": "plan_only",
            "requires_approval_before_execution": True,
        },
        "tasks": [
            {
                "task_id": "T1",
                "title": "实现后端 API",
                "goal": "完成基础接口",
                "required_skills": ["backend_engineer"],
                "assigned_agent_id": "agent_backend_exec",
                "assigned_agent_name": "后端专家",
                "assignment_reason": "匹配后端能力",
                "depends_on": [],
                "expected_outputs": ["api"],
                "acceptance_criteria": ["接口可调用"],
            },
            {
                "task_id": "T2",
                "title": "实现前端页面",
                "goal": "完成列表页面",
                "required_skills": ["frontend_engineer"],
                "assigned_agent_id": "agent_frontend_exec",
                "assigned_agent_name": "前端专家",
                "assignment_reason": "匹配前端能力",
                "depends_on": ["T1"],
                "expected_outputs": ["ui"],
                "acceptance_criteria": ["页面可用"],
            },
        ],
    }


@pytest.mark.asyncio
async def test_execute_plan_starts_async_scheduler_then_completes(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    session = await db_session.get(Session, session_id)
    assert session is not None
    project = await db_session.get(Project, session.project_id)
    assert project is not None
    project_workspace = Path(project.workspace_path)

    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": _valid_plan(),
    })

    assert res.status_code == 200
    data = res.json()
    assert data["executionId"].startswith("exec_")
    assert data["sessionId"] == session_id
    assert data["planId"] == "plan_exec_001"
    assert data["status"] == "running"
    assert data["startedAt"] is not None
    assert data["completedAt"] is None
    assert [task["status"] for task in data["tasks"]] == ["pending", "pending"]
    assert data["tasks"][1]["dependsOn"] == ["T1"]
    assert data["validation"]["ok"] is True

    completed = await _wait_execution_completed(test_client, data["executionId"])
    assert completed["executionId"] == data["executionId"]
    assert completed["status"] == "completed", completed["events"][-1]
    assert completed["completedAt"] is not None
    assert [task["status"] for task in completed["tasks"]] == ["completed", "completed"]
    assert completed["tasks"][0]["runnerType"] == "cli"
    assert completed["tasks"][0]["visibleMessageId"]
    assert "真实任务输出" in completed["tasks"][0]["summary"]
    task_workspace = Path(completed["tasks"][0]["taskWorkspacePath"])
    task_parts = task_workspace.parts
    assert ".agenthub" in task_parts
    agenthub_index = task_parts.index(".agenthub")
    assert task_parts[agenthub_index:agenthub_index + 5] == (
        ".agenthub", "executions", data["executionId"], "tasks", "T1",
    )
    assert task_workspace.name == "T1"
    assert (task_workspace / "TASK.md").exists()
    assert (task_workspace / "HANDOFF.md").exists()
    assert (project_workspace / "docs" / "orchestrator-deliverable.md").exists()
    assert completed["tasks"][1]["runnerType"] == "cli"
    assert completed["tasks"][1]["visibleMessageId"]
    assert all(task["resultMessageId"] for task in completed["tasks"])
    assert completed["tasks"][0]["upstreamResults"] == []
    assert completed["tasks"][1]["upstreamResults"] == [{
        "taskId": "T1",
        "title": "实现后端 API",
        "summary": completed["tasks"][0]["summary"],
        "resultMessageId": completed["tasks"][0]["resultMessageId"],
        "assignedAgentId": "agent_backend_exec",
        "assignedAgentName": "后端专家",
    }]

    rows = await db_session.execute(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.content_type == "orchestrator_task_result",
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    task_messages = list(rows.scalars().all())
    assert len(task_messages) == 2
    metadata = json.loads(task_messages[0].metadata_json)
    result = metadata["orchestratorTaskResult"]
    assert result["executionId"] == data["executionId"]
    assert result["planId"] == "plan_exec_001"
    assert result["taskId"] == "T1"
    assert result["assignedAgentId"] == "agent_backend_exec"
    assert result["runnerType"] == "cli"
    assert result["visibleMessageId"] == completed["tasks"][0]["visibleMessageId"]
    second_metadata = json.loads(task_messages[1].metadata_json)
    second_result = second_metadata["orchestratorTaskResult"]
    assert second_result["taskId"] == "T2"
    assert second_result["upstreamResults"][0]["taskId"] == "T1"
    assert second_result["upstreamResults"][0]["resultMessageId"] == completed["tasks"][0]["resultMessageId"]

    visible_messages = (await test_client.get(f"/api/sessions/{session_id}/messages")).json()
    assert not any(message["contentType"] == "orchestrator_task_result" for message in visible_messages)
    visible = next(
        message for message in visible_messages
        if message["id"] == completed["tasks"][0]["visibleMessageId"]
    )
    assert visible["metadata"]["executionTrace"]["status"] == "completed"
    assert visible["metadata"]["executionTrace"]["workspacePath"] == str(project_workspace)
    assert visible["metadata"]["orchestratorTaskMessage"]["taskId"] == "T1"
    assert visible["metadata"]["taskWorkspacePath"] == str(task_workspace)
    assert visible["metadata"]["orchestratorTaskMessage"]["taskWorkspacePath"] == str(task_workspace)


@pytest.mark.asyncio
async def test_interview_task_blocks_downstream_until_user_confirms(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    plan = _valid_plan()
    plan["tasks"][0].update({
        "title": "产品经理需求访谈",
        "goal": "先向用户澄清业务目标和预约规则",
        "interaction_policy": "ask_user_until_confirmed",
        "handoff_policy": "manual_confirm",
        "awaits_user_input": True,
        "blocks_downstream_until": "user_confirms",
    })

    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": plan,
    })
    assert res.status_code == 200
    execution_id = res.json()["executionId"]

    waiting = await _wait_execution_status(test_client, execution_id, {"awaiting_user_input", "failed"})
    assert waiting["status"] == "awaiting_user_input", waiting["events"][-1]
    assert waiting["tasks"][0]["status"] == "awaiting_user_input"
    assert waiting["tasks"][1]["status"] == "pending"
    assert waiting["tasks"][0]["interactionPolicy"] == "ask_user_until_confirmed"

    visible_messages = (await test_client.get(f"/api/sessions/{session_id}/messages")).json()
    interview_message = next(
        message for message in visible_messages
        if message["id"] == waiting["tasks"][0]["visibleMessageId"]
    )
    assert interview_message["metadata"]["awaitingUserInput"] is True
    assert interview_message["metadata"]["groupDialog"]["status"] == "awaiting_user_input"
    assert interview_message["metadata"]["groupDialog"]["executionId"] == execution_id
    assert interview_message["metadata"]["groupDialog"]["taskId"] == "T1"

    confirm = await test_client.post(
        f"/api/orchestrator/executions/{execution_id}/tasks/T1/confirm",
        json={"note": "需求已确认，进入前端实现。"},
    )
    assert confirm.status_code == 200

    completed = await _wait_execution_completed(test_client, execution_id)
    assert completed["status"] == "completed", completed["events"][-1]
    assert [task["status"] for task in completed["tasks"]] == ["completed", "completed"]
    assert completed["tasks"][1]["visibleMessageId"]


@pytest.mark.asyncio
async def test_confirmed_interview_handoff_includes_latest_dialog_context(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    plan = _valid_plan()
    plan["tasks"][0].update({
        "title": "明确预约后端需求与边界",
        "goal": "先向用户澄清业务目标和预约规则",
        "interaction_policy": "ask_user_until_confirmed",
        "handoff_policy": "manual_confirm",
        "awaits_user_input": True,
        "blocks_downstream_until": "user_confirms",
    })

    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": plan,
    })
    assert res.status_code == 200
    execution_id = res.json()["executionId"]

    waiting = await _wait_execution_status(test_client, execution_id, {"awaiting_user_input", "failed"})
    assert waiting["status"] == "awaiting_user_input"

    metadata = {
        "groupDialog": {
            "mode": "direct_dialog",
            "status": "awaiting_user_input",
            "activeAgentId": "agent_backend_exec",
            "activeAgentName": "后端专家",
            "source": "orchestrator_task",
            "executionId": execution_id,
            "taskId": "T1",
        }
    }
    db_session.add_all([
        Message(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role="user",
            content=(
                "不是正式预约成功，而是预约意向已提交；周一休息不约；"
                "Demo 不做通知、不登录，手机号完整展示。"
            ),
            source_type="user",
            source_name="用户",
        ),
        Message(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role="assistant",
            content=(
                "最终口径：后端只接收并保存预约表单；管理页公开展示完整手机号；"
                "不做门店通知；周一不可预约；最早预约当前时间 2 小时后。"
            ),
            agent_name="后端专家",
            source_type="agent",
            source_id="agent_backend_exec",
            source_name="后端专家",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        ),
    ])
    await db_session.commit()

    confirm = await test_client.post(
        f"/api/orchestrator/executions/{execution_id}/tasks/T1/confirm",
        json={"note": "后端专家 访谈节点已由用户确认"},
    )
    assert confirm.status_code == 200

    completed = await _wait_execution_completed(test_client, execution_id)
    assert completed["status"] == "completed", completed["events"][-1]
    t1 = completed["tasks"][0]
    t2 = completed["tasks"][1]
    assert "周一休息不约" in t1["summary"]
    assert "不做门店通知" in t1["summary"]
    assert "手机号完整展示" in t2["upstreamResults"][0]["summary"]

    handoff = Path(t1["taskWorkspacePath"]) / "HANDOFF.md"
    assert handoff.exists()
    handoff_text = handoff.read_text(encoding="utf-8")
    assert "用户确认后的最终交接" in handoff_text
    assert "最早预约当前时间 2 小时后" in handoff_text


@pytest.mark.asyncio
async def test_interrupted_execution_can_resume_from_unfinished_task_only(db_session):
    class SlowSecondTaskRunner:
        def __init__(self):
            self.calls: list[str] = []
            self.t2_started = asyncio.Event()
            self.release_t2 = asyncio.Event()

        async def run(self, task, execution, upstream_results):
            task_id = task["taskId"]
            self.calls.append(task_id)
            if task_id == "T1":
                return "T1 已完成"
            self.t2_started.set()
            if self.calls.count("T2") == 1:
                await self.release_t2.wait()
            return "T2 已完成"

    runner = SlowSecondTaskRunner()
    registry = OrchestratorExecutionRegistry(task_runner=runner)
    execution = registry.create_execution(
        session_id=str(uuid.uuid4()),
        plan=_valid_plan(),
        active_agent_ids={"agent_backend_exec", "agent_frontend_exec"},
        auto_start=False,
    )
    registry._executions[execution["executionId"]]["runnerType"] = "mock"
    registry.start_execution(execution["executionId"])

    for _ in range(40):
        latest = registry.get_execution(execution["executionId"])
        assert latest is not None
        if latest["tasks"][0]["status"] == "completed" and latest["tasks"][1]["status"] == "running":
            break
        await asyncio.sleep(0.02)
    else:
        raise AssertionError("T2 did not start")

    interrupted = await registry.interrupt_execution(
        execution["executionId"],
        reason="测试中断",
    )
    assert interrupted is not None
    assert interrupted["status"] == "interrupted"
    assert [task["status"] for task in interrupted["tasks"]] == ["completed", "interrupted"]

    runner.release_t2.set()
    await asyncio.sleep(0.05)

    resumed = await registry.resume_execution(execution["executionId"])
    assert resumed is not None
    assert resumed["status"] == "running"

    for _ in range(40):
        latest = registry.get_execution(execution["executionId"])
        assert latest is not None
        if latest["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    else:
        raise AssertionError("resumed execution did not complete")

    latest = registry.get_execution(execution["executionId"])
    assert latest is not None
    assert latest["status"] == "completed"
    assert [task["status"] for task in latest["tasks"]] == ["completed", "completed"]
    assert runner.calls.count("T1") == 1
    assert runner.calls.count("T2") == 2


@pytest.mark.asyncio
async def test_resume_execution_restores_persisted_running_snapshot(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    execution = execution_registry.create_execution(
        session_id=session_id,
        plan=_valid_plan(),
        active_agent_ids={"agent_backend_exec", "agent_frontend_exec"},
        auto_start=False,
    )
    execution_id = execution["executionId"]
    snapshot = execution_registry.get_execution(execution_id)
    assert snapshot is not None
    snapshot["runnerType"] = "mock"
    snapshot["status"] = "running"
    snapshot["tasks"][0]["status"] = "completed"
    snapshot["tasks"][0]["summary"] = "T1 已完成"
    snapshot["tasks"][1]["status"] = "running"
    snapshot["tasks"][1]["runnerType"] = "mock"
    snapshot["updatedAt"] = "2026-06-09T00:00:00+00:00"

    control_message_id = str(uuid.uuid4())
    db_session.add(Message(
        id=control_message_id,
        session_id=session_id,
        role="assistant",
        content="执行面板",
        content_type="text",
        source_type="system",
        source_name="Scheduler",
        metadata_json=json.dumps({"orchestratorExecution": snapshot}, ensure_ascii=False),
    ))
    await db_session.commit()
    execution_registry._executions.pop(execution_id, None)

    resume = await test_client.post(f"/api/orchestrator/executions/{execution_id}/resume")
    assert resume.status_code == 200
    resumed = resume.json()
    assert resumed["status"] == "running"
    assert resumed["tasks"][0]["status"] == "completed"

    completed = await _wait_execution_completed(test_client, execution_id)
    assert completed["status"] == "completed", completed["events"][-1]
    assert [task["status"] for task in completed["tasks"]] == ["completed", "completed"]
    assert completed["tasks"][1]["summary"].startswith("T2 已完成")


@pytest.mark.asyncio
async def test_execute_plan_simulates_parallel_ready_tasks(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    plan = _valid_plan()
    plan["tasks"] = [
        {
            "task_id": "T1",
            "title": "后端建模",
            "goal": "完成领域模型",
            "required_skills": ["backend"],
            "assigned_agent_id": "agent_backend_exec",
            "assigned_agent_name": "后端专家",
            "depends_on": [],
        },
        {
            "task_id": "T2",
            "title": "前端草图",
            "goal": "完成页面草图",
            "required_skills": ["frontend"],
            "assigned_agent_id": "agent_frontend_exec",
            "assigned_agent_name": "前端专家",
            "depends_on": [],
        },
        {
            "task_id": "T3",
            "title": "联调验收",
            "goal": "完成验收",
            "required_skills": ["backend", "frontend"],
            "assigned_agent_id": "agent_backend_exec",
            "assigned_agent_name": "后端专家",
            "depends_on": ["T1", "T2"],
        },
    ]

    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": plan,
    })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "running"

    data = await _wait_execution_completed(test_client, data["executionId"])
    assert data["status"] == "completed", data["events"][-1]
    batch_events = [event for event in data["events"] if event["type"] == "scheduler_batch_running"]
    assert batch_events[0]["taskIds"] == ["T1", "T2"]
    assert batch_events[1]["taskIds"] == ["T3"]
    started_events = [event for event in data["events"] if event["type"] == "task_started"]
    assert [event["taskId"] for event in started_events[:2]] == ["T1", "T2"]
    assert [task["status"] for task in data["tasks"]] == ["completed", "completed", "completed"]
    assert [task["runnerType"] for task in data["tasks"]] == ["cli", "cli", "cli"]
    assert all(task["visibleMessageId"] for task in data["tasks"])
    t3 = next(task for task in data["tasks"] if task["taskId"] == "T3")
    assert [item["taskId"] for item in t3["upstreamResults"]] == ["T1", "T2"]


@pytest.mark.asyncio
async def test_execute_plan_rejects_missing_assigned_agent(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    plan = _valid_plan()
    plan["tasks"][0]["assigned_agent_id"] = None

    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": plan,
    })

    assert res.status_code == 400
    detail = res.json()["detail"]
    assert any("缺少 assigned_agent_id" in error for error in detail["errors"])


@pytest.mark.asyncio
async def test_execute_plan_rejects_invalid_dag(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    plan = _valid_plan()
    plan["tasks"][0]["depends_on"] = ["missing"]

    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": plan,
    })

    assert res.status_code == 400
    detail = res.json()["detail"]
    assert any("不存在的任务" in error for error in detail["errors"])


@pytest.mark.asyncio
async def test_get_execution_falls_back_to_persisted_message_snapshot(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    execution = execution_registry.create_execution(
        session_id=session_id,
        plan=_valid_plan(),
        active_agent_ids={"agent_frontend_exec", "agent_backend_exec"},
    )
    execution_id = execution["executionId"]
    db_session.add(Message(
        id=f"msg_approval_{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        role="assistant",
        content="已确认计划，创建执行。",
        content_type="text",
        agent_name="Orchestrator 调度器",
        source_type="agent",
        source_name="Orchestrator 调度器",
        metadata_json=json.dumps({"orchestratorExecution": execution}, ensure_ascii=False),
    ))
    await db_session.commit()
    execution_registry._executions.pop(execution_id, None)

    res = await test_client.get(f"/api/orchestrator/executions/{execution_id}")

    assert res.status_code == 200
    data = res.json()
    assert data["executionId"] == execution_id
    assert data["status"] == "interrupted"
    assert data["events"][-1]["type"] == "execution_interrupted"


@pytest.mark.asyncio
async def test_cancel_execution_marks_active_run_cancelled(test_client, db_session):
    session_id = await _seed_session_with_agents(db_session)
    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": session_id,
        "normalizedPlan": _valid_plan(),
    })
    assert res.status_code == 200
    execution_id = res.json()["executionId"]

    cancel = await test_client.post(f"/api/orchestrator/executions/{execution_id}/cancel")

    assert cancel.status_code == 200
    data = cancel.json()
    assert data["status"] == "cancelled"
    assert any(event["type"] == "execution_cancel_requested" for event in data["events"])
    assert any(event["type"] == "execution_cancelled" for event in data["events"])


@pytest.mark.asyncio
async def test_running_cli_task_visible_message_survives_refresh(test_client, db_session, monkeypatch):
    session_id = await _seed_session_with_agents(db_session)

    async def slow_stream(self, **kwargs):
        yield CliEvent("agent.process.started", "proc-slow")
        yield CliEvent("agent.output", "proc-slow", chunk="正在执行 T1...", chunk_type="text")
        await asyncio.sleep(5)

    from app.services.cli_agent_service import CliAgentService
    monkeypatch.setattr(CliAgentService, "stream", slow_stream)

    res = await test_client.post(
        "/api/orchestrator/plans/execute",
        json={"sessionId": session_id, "normalizedPlan": _valid_plan()},
    )
    assert res.status_code == 200
    execution_id = res.json()["executionId"]

    for _ in range(30):
        latest = (await test_client.get(f"/api/orchestrator/executions/{execution_id}")).json()
        if latest["tasks"][0]["status"] == "running":
            break
        await asyncio.sleep(0.02)
    latest = (await test_client.get(f"/api/orchestrator/executions/{execution_id}")).json()
    assert latest["tasks"][0]["status"] == "running"
    assert latest["tasks"][0]["visibleMessageId"]

    visible = None
    for _ in range(30):
        visible_messages = (await test_client.get(f"/api/sessions/{session_id}/messages")).json()
        visible = next(
            message for message in visible_messages
            if message["id"] == latest["tasks"][0]["visibleMessageId"]
        )
        if "正在执行 T1" in visible["content"]:
            break
        await asyncio.sleep(0.02)
    assert visible is not None
    assert visible["agentName"] == "后端专家"
    assert visible["agentRole"] == "executor"
    assert visible["taskName"] == "实现后端 API"
    assert visible["metadata"]["executionTrace"]["status"] == "running"
    assert "正在执行 T1" in visible["content"]

    cancel = await test_client.post(f"/api/orchestrator/executions/{execution_id}/cancel")
    assert cancel.status_code == 200
    cancelled = cancel.json()
    assert cancelled["status"] == "cancelled"

    visible_messages = (await test_client.get(f"/api/sessions/{session_id}/messages")).json()
    visible = next(
        message for message in visible_messages
        if message["id"] == latest["tasks"][0]["visibleMessageId"]
    )
    assert visible["metadata"]["executionTrace"]["status"] == "cancelled"
    assert visible["metadata"]["runStatus"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_registry_stops_scheduler_before_downstream_tasks():
    class SlowRunner:
        async def run(self, task, execution, upstream_results):
            await asyncio.sleep(5)
            return "should not finish"

    registry = OrchestratorExecutionRegistry(task_runner=SlowRunner())
    plan = _valid_plan()
    plan["runnerType"] = "mock"
    execution = registry.create_execution(
        session_id="session_cancel_unit",
        plan=plan,
        active_agent_ids={"agent_frontend_exec", "agent_backend_exec"},
    )
    cancelled = await registry.cancel_execution(execution["executionId"])

    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    assert cancelled["tasks"][0]["status"] in {"cancelled", "pending"}
    assert cancelled["tasks"][1]["status"] == "pending"
    await asyncio.sleep(0.05)
    latest = registry.get_execution(execution["executionId"])
    assert latest is not None
    assert latest["status"] == "cancelled"
    assert latest["tasks"][1]["status"] == "pending"


@pytest.mark.asyncio
async def test_execute_plan_rejects_unknown_session(test_client):
    res = await test_client.post("/api/orchestrator/plans/execute", json={
        "sessionId": "missing-session",
        "normalizedPlan": _valid_plan(),
    })

    assert res.status_code == 404
