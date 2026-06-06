import uuid
import json
import sys
import asyncio
from pathlib import Path
import pytest
from sqlalchemy import select

from app.models import AgentConfig, Message
from app.agents.cli_events import CliEvent

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def make_test_cli_agent(name: str = "测试 Agent") -> AgentConfig:
    cli = BACKEND_ROOT / ".test-bin" / "fixture_cli.py"
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.write_text(
        "import os, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "with open('.agenthub-cli-stdin.txt', 'w', encoding='utf-8') as f:\n"
        "    f.write(data)\n"
        "sys.stdout.write('\\x1b[32mHello\\x1b[0m, World!')\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )
    return AgentConfig(
        id=str(uuid.uuid4()),
        name=name,
        description="测试 CLI Agent",
        system_prompt="你是一个测试助手。",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable=sys.executable,
        init_args=json.dumps([str(cli)]),
        env_vars="{}",
    )


async def wait_execution_completed(test_client, execution_id: str, attempts: int = 20) -> dict:
    latest = None
    for _ in range(attempts):
        response = await test_client.get(f"/api/orchestrator/executions/{execution_id}")
        assert response.status_code == 200
        latest = response.json()
        if latest["status"] in {"completed", "failed"}:
            return latest
        await asyncio.sleep(0.05)
    assert latest is not None
    return latest


@pytest.mark.asyncio
class TestGroupSession:
    async def test_create_group_session(self, test_client, test_agent, db_session):
        agent2 = make_test_cli_agent("A2")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "title": "群聊测试",
            "mode": "group",
            "agentConfigIds": [test_agent.id, agent2.id],
        })
        assert res.status_code == 201
        data = res.json()
        assert data["mode"] == "group"

    async def test_get_members(self, test_client, test_agent, db_session):
        agent2 = make_test_cli_agent("A2")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]

        res2 = await test_client.get(f"/api/sessions/{sid}/members")
        assert res2.status_code == 200
        members = res2.json()
        assert len(members) == 3
        names = {member["agentName"] for member in members}
        assert {"A2", test_agent.name, "Orchestrator 调度器"}.issubset(names)

    async def test_single_mode_still_works(self, test_client, test_agent):
        res = await test_client.post("/api/sessions", json={
            "agentConfigId": test_agent.id, "mode": "single"
        })
        assert res.status_code == 201
        assert res.json()["mode"] == "single"

    # === 新增：群聊消息发送测试 (覆盖 AgentExecutor._execute_single 路径) ===

    async def test_group_chat_sse_returns_200(self, test_client, test_agent, db_session):
        """群聊发送消息 → AgentExecutor 路径 → 200 响应。"""
        agent2 = make_test_cli_agent("A2")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "帮我写一个函数"},
        )
        assert resp.status_code == 200

    async def test_group_chat_has_orchestrator_events(self, test_client, test_agent, db_session):
        """群聊 SSE 必须包含 orchestrator.route 和 orchestrator.task_started 事件。"""
        agent2 = make_test_cli_agent("A2")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "帮我写代码"},
        )
        events = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                d = json.loads(line[6:])
                t = d.get("type", "")
                if t:
                    events.append(t)
                if d.get("done") and d.get("agentId"):
                    events.append("agent.done")

        assert "orchestrator.route" in events
        assert "orchestrator.task_started" in events
        assert "orchestrator.task_completed" in events
        assert "agent.start" in events
        assert "agent.done" in events
        assert not any(e.startswith("orchestrator.summary_") for e in events)

    async def test_group_chat_cli_agents_produce_tokens(self, test_client, test_agent, db_session):
        """测试 CLI Agent 在群聊模式下通过 subprocess 产出完整 token 流。"""
        agent2 = make_test_cli_agent("A2")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "Hello"},
        )
        agent_tokens: dict[str, str] = {}
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                d = json.loads(line[6:])
                if d.get("agentId") and d.get("token") and not d.get("done"):
                    aid = d["agentId"]
                    agent_tokens[aid] = agent_tokens.get(aid, "") + d["token"]

        # 测试 CLI 脚本对每个 Agent 输出 "Hello, World!"。
        assert len(agent_tokens) == 2, f"Expected 2 agents to produce tokens, got {len(agent_tokens)}"
        for aid, text in agent_tokens.items():
            assert "Hello" in text, f"Agent {aid[:6]} missing 'Hello' in: {text[:50]}"
            assert "World" in text, f"Agent {aid[:6]} missing 'World' in: {text[:50]}"

    async def test_group_chat_no_agent_crash(self, test_client, test_agent, db_session):
        """所有 SSE 事件必须是合法 JSON，done 事件不早于 task_completed 之前截断。"""
        agent2 = make_test_cli_agent("A2")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "hi"},
        )
        event_count = 0
        had_error = False
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                # 每行必须是合法 JSON — 不能因内部异常导致格式错误
                d = json.loads(line[6:])
                event_count += 1
                if d.get("type") == "error":
                    had_error = True

        assert event_count > 0, "SSE stream produced zero events"
        assert not had_error, "Group chat should not produce global error with test CLI fixture"

    async def test_group_chat_messages_persisted(self, test_client, test_agent, db_session):
        """群聊完成后，Agent 消息应持久化到数据库。"""
        agent2 = make_test_cli_agent("A2")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]

        await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "Hello"},
        )

        # 等待 SSE 流完成后查询消息
        resp = await test_client.get(f"/api/sessions/{sid}/messages")
        assert resp.status_code == 200
        msgs = resp.json()
        assert len(msgs) >= 3, f"Expected user + simple parallel agents, got {len(msgs)}"
        assert not any(m.get("sourceType") == "orchestrator" for m in msgs)
        assert not any(m.get("contentType") == "orchestrator_summary" for m in msgs)

    async def test_group_chat_passes_pinned_ids_to_orchestrator(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        """Phase 4: 群聊也必须把 Pin 消息接入 Orchestrator ContextAssembly。"""
        from app.models import Message
        from app.domain.orchestrator_v2 import OrchestratorV2

        agent2 = make_test_cli_agent("A2")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]
        pinned = Message(
            id=str(uuid.uuid4()),
            session_id=sid,
            role="user",
            content="必须保留的背景",
            source_type="user",
            source_name="用户",
            is_pinned="1",
        )
        db_session.add(pinned)
        await db_session.commit()

        seen: list[list[str]] = []
        original_run = OrchestratorV2.run

        async def spy_run(self, req):
            seen.append(list(req.pinned_message_ids))
            return await original_run(self, req)

        monkeypatch.setattr(OrchestratorV2, "run", spy_run)

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "Hello"},
        )
        assert resp.status_code == 200
        async for _line in resp.aiter_lines():
            pass

        assert seen and pinned.id in seen[0]

    async def test_group_chat_dag_sse_protocol(self, test_client, test_agent, db_session):
        """复杂多阶段请求应返回 DAG task_started + phase_change 协议。"""
        agents = [
            make_test_cli_agent("架构师"),
            make_test_cli_agent("前端"),
            make_test_cli_agent("后端"),
            make_test_cli_agent("审查员"),
        ]
        agents[0].description = "架构 设计 方案"
        agents[0].system_prompt = "擅长架构设计"
        agents[1].description = "React 前端 UI"
        agents[1].system_prompt = "擅长前端开发"
        agents[2].description = "Python 后端 API 数据库"
        agents[2].system_prompt = "擅长后端开发"
        agents[3].description = "审查 测试 安全"
        agents[3].system_prompt = "擅长代码审查"
        db_session.add_all(agents)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [a.id for a in agents],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "先设计登录系统再前后端实现最后审查"},
        )

        task_started = None
        phase_events = []
        summary_events = []
        token_with_role = False
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if data.get("type") == "orchestrator.task_started":
                task_started = data
            if data.get("type") == "orchestrator.phase_change":
                phase_events.append(data)
            if data.get("type", "").startswith("orchestrator.summary_"):
                summary_events.append(data["type"])
            if data.get("agentId") and data.get("token") and not data.get("done"):
                token_with_role = "role" in data and "phase" in data and "messageId" in data

        assert task_started is not None
        assert "dag" in task_started
        assert "plan_summary" in task_started
        assert "先由@架构师规划" in task_started["plan_summary"]
        assert [p["phase"] for p in task_started["dag"]["phases"]] == [0, 1, 2]
        assert task_started["dag"]["phases"][1]["mode"] == "parallel"
        assert any(e["phase"] == 1 and e["status"] == "running" for e in phase_events)
        assert any(e["phase"] == 2 and e["status"] == "completed" for e in phase_events)
        assert "orchestrator.summary_started" in summary_events
        assert "orchestrator.summary_delta" in summary_events
        assert "orchestrator.summary_completed" in summary_events
        assert token_with_role

    async def test_mention_orchestrator_returns_draft_plan_only(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        async def fake_stream(self, **kwargs):
            yield CliEvent(
                "agent.output",
                "proc-1",
                chunk=json.dumps({
                    "tasks": [
                        {
                            "task_id": "T1",
                            "title": "需求澄清",
                            "goal": "明确业务边界",
                            "required_skills": ["requirements"],
                            "assigned_agent_id": test_agent.id,
                            "assigned_agent_name": test_agent.name,
                            "depends_on": [],
                        }
                    ]
                }, ensure_ascii=False),
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-1", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id, orchestrator.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 做员工报销系统", "mentions": [orchestrator.id]},
        )

        event_types = []
        agent_tokens = ""
        done_message_id = None
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            event_types.append(data.get("type", ""))
            if data.get("agentId") == orchestrator.id and data.get("token"):
                agent_tokens += data["token"]
            if data.get("done"):
                done_message_id = data.get("messageId")

        assert "agent.start" in event_types
        assert "agent.output" in event_types
        assert "orchestrator.route" not in event_types
        assert "orchestrator.task_started" not in event_types
        assert "需求澄清" in agent_tokens

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        saved = next(message for message in messages if message["id"] == done_message_id)
        assert saved["agentName"] == "Orchestrator 调度器"
        assert saved["sourceType"] == "agent"
        assert saved["metadata"]["orchestratorPlan"]["ok"] is True

    async def test_text_mention_orchestrator_name_with_space_returns_draft_plan_only(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        async def fake_stream(self, **kwargs):
            yield CliEvent(
                "agent.output",
                "proc-1",
                chunk=json.dumps({
                    "tasks": [
                        {
                            "task_id": "T1",
                            "title": "生成调度计划",
                            "goal": "输出 draft plan",
                            "required_skills": ["orchestrator_planner"],
                            "assigned_agent_id": test_agent.id,
                            "assigned_agent_name": test_agent.name,
                            "depends_on": [],
                        }
                    ]
                }, ensure_ascii=False),
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-1", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id, orchestrator.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 做员工报销系统"},
        )

        event_types = []
        token = ""
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                event_types.append(data.get("type", ""))
                if data.get("agentName") == "Orchestrator 调度器":
                    token += data.get("token", "")

        assert "agent.start" in event_types
        assert "agent.output" in event_types
        assert "orchestrator.route" not in event_types
        assert "orchestrator.task_started" not in event_types
        assert "生成调度计划" in token

    async def test_orchestrator_followup_approve_action_creates_execution(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        prompts: list[str] = []
        outputs = [
            {
                "plan_id": "plan_followup_001",
                "tasks": [
                    {
                        "task_id": "T1",
                        "title": "实现后端",
                        "goal": "完成 API",
                        "required_skills": ["backend"],
                        "assigned_agent_id": test_agent.id,
                        "assigned_agent_name": test_agent.name,
                        "depends_on": [],
                    }
                ],
            },
            {
                "action": "approve_plan",
                "target_plan_id": "plan_followup_001",
                "reason": "用户明确确认执行",
            },
        ]

        async def fake_stream(self, **kwargs):
            prompts.append(kwargs["messages"][-1]["content"])
            payload = outputs[len(prompts) - 1]
            yield CliEvent(
                "agent.output",
                "proc-1",
                chunk=json.dumps(payload, ensure_ascii=False),
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-1", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id, orchestrator.id],
        })
        sid = res.json()["id"]

        await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 做员工报销系统", "mentions": [orchestrator.id]},
        )
        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 确认，开始执行", "mentions": [orchestrator.id]},
        )

        execution_event = None
        visible = ""
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if data.get("type") == "orchestrator.plan_execution_created":
                execution_event = data
            if data.get("agentName") == "Orchestrator 调度器":
                visible += data.get("token", "")

        assert execution_event is not None
        assert execution_event["planId"] == "plan_followup_001"
        assert execution_event["status"] == "running"
        assert "已确认计划 plan_followup_001" in visible
        assert "approve_plan" in prompts[1]
        assert "上一版 draft plan" in prompts[1]

        completed = await wait_execution_completed(test_client, execution_event["executionId"])
        assert completed["status"] == "completed"
        assert completed["tasks"][0]["resultMessageId"]

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        assert not any(message["contentType"] == "orchestrator_task_result" for message in messages)
        approval = messages[-1]
        assert approval["metadata"]["orchestratorAction"]["action"] == "approve_plan"
        assert approval["metadata"]["orchestratorExecution"]["status"] == "running"

        rows = await db_session.execute(
            select(Message).where(
                Message.session_id == sid,
                Message.content_type == "orchestrator_task_result",
            )
        )
        task_results = list(rows.scalars().all())
        assert len(task_results) == 1
        metadata = json.loads(task_results[0].metadata_json)
        assert metadata["orchestratorTaskResult"]["taskId"] == "T1"

    async def test_orchestrator_followup_revision_outputs_new_draft_plan(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        outputs = [
            {
                "plan_id": "plan_revision_001",
                "tasks": [
                    {
                        "task_id": "T1",
                        "title": "原计划",
                        "goal": "先做后端",
                        "required_skills": ["backend"],
                        "assigned_agent_id": test_agent.id,
                        "assigned_agent_name": test_agent.name,
                        "depends_on": [],
                    }
                ],
            },
            {
                "plan_id": "plan_revision_002",
                "tasks": [
                    {
                        "task_id": "T1",
                        "title": "修改后的计划",
                        "goal": "增加安全审查",
                        "required_skills": ["review"],
                        "assigned_agent_id": test_agent.id,
                        "assigned_agent_name": test_agent.name,
                        "depends_on": [],
                    }
                ],
            },
        ]
        call_count = 0

        async def fake_stream(self, **kwargs):
            nonlocal call_count
            payload = outputs[call_count]
            call_count += 1
            yield CliEvent(
                "agent.output",
                "proc-1",
                chunk=json.dumps(payload, ensure_ascii=False),
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-1", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id, orchestrator.id],
        })
        sid = res.json()["id"]

        await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 做员工报销系统", "mentions": [orchestrator.id]},
        )
        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 加一个安全审查后重新输出计划", "mentions": [orchestrator.id]},
        )

        event_types = []
        visible = ""
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            event_types.append(data.get("type", ""))
            if data.get("agentName") == "Orchestrator 调度器":
                visible += data.get("token", "")

        assert "orchestrator.plan_execution_created" not in event_types
        assert "修改后的计划" in visible

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        latest = messages[-1]
        assert latest["metadata"]["orchestratorPlan"]["normalizedPlan"]["plan_id"] == "plan_revision_002"
        assert "orchestratorExecution" not in latest["metadata"]
