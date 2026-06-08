import uuid
import json
import sys
import asyncio
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy import select

from app.models import AgentConfig, EngineSession, Message, Session, SessionMember
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

    async def test_create_group_session_keeps_twelve_members(self, test_client, db_session):
        agents = [make_test_cli_agent(f"A{index}") for index in range(11)]
        db_session.add_all(agents)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group",
            "agentConfigIds": [agent.id for agent in agents],
        })

        assert res.status_code == 201
        sid = res.json()["id"]
        members = (await test_client.get(f"/api/sessions/{sid}/members")).json()
        assert len(members) == 12
        names = {member["agentName"] for member in members}
        assert {f"A{index}" for index in range(11)}.issubset(names)
        assert "Orchestrator 调度器" in names

    async def test_single_mode_still_works(self, test_client, test_agent):
        res = await test_client.post("/api/sessions", json={
            "agentConfigId": test_agent.id, "mode": "single"
        })
        assert res.status_code == 201
        assert res.json()["mode"] == "single"

    # === 群聊消息发送测试：无 @ 先进入可见 Orchestrator 调度器 ===

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

    async def test_group_chat_unmentioned_single_agent_uses_visible_orchestrator(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        """无 @ 的轻量执行请求先由真实调度器 Agent 判断，再只调用 1 个 Agent。"""
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        orchestrator_cli_calls = 0

        async def fake_stream(self, **kwargs):
            nonlocal orchestrator_cli_calls
            agent = kwargs["agent"]
            if (agent.primary_skill or "") == "orchestrator_planner":
                orchestrator_cli_calls += 1
                yield CliEvent("agent.process.started", "proc-steward")
                yield CliEvent(
                    "agent.output",
                    "proc-steward",
                    chunk=json.dumps({
                        "route_type": "single_agent",
                        "reply": f"我先交给 @{test_agent.name} 轻量处理。",
                        "reason": "这是单 Agent 可完成的轻量代码请求。",
                        "selected_agent_ids": [test_agent.id],
                        "task_brief": "写代码",
                        "confidence": 0.9,
                        "requires_approval": False,
                        "risk_level": "low",
                    }, ensure_ascii=False),
                    chunk_type="text",
                )
                yield CliEvent("agent.process.completed", "proc-steward", exit_code=0)
                return
            yield CliEvent("agent.output", "proc-2", chunk="Hello, World!", chunk_type="text")
            yield CliEvent("agent.process.completed", "proc-2", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id, orchestrator.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "帮我写代码"},
        )
        events = []
        agent_names = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                d = json.loads(line[6:])
                t = d.get("type", "")
                if t:
                    events.append(t)
                if t == "agent.start":
                    agent_names.append(d.get("agentName"))
                if d.get("done") and d.get("agentId"):
                    events.append("agent.done")

        assert "orchestrator.steward_decision" in events
        assert "orchestrator.route" in events
        assert "orchestrator.task_started" in events
        assert "orchestrator.task_completed" in events
        assert "agent.start" in events
        assert "agent.done" in events
        assert agent_names[0] == "Orchestrator 调度器"
        assert agent_names[1] == test_agent.name
        assert orchestrator_cli_calls == 1
        assert not any(e.startswith("orchestrator.summary_") for e in events)

    async def test_group_chat_generates_title_after_task_completed(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        """显式 @ 群聊任务完成之后仍会自动总结标题并推送给前端。"""
        class FakeSystemLLM:
            def is_configured(self):
                return True

            async def chat(self, **kwargs):
                return SimpleNamespace(content="登录页优化")

        from app.services import session_title_service
        monkeypatch.setattr(session_title_service, "system_llm", FakeSystemLLM())

        agent2 = make_test_cli_agent("A2")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "title": "群聊",
            "mode": "group",
            "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={
                "content": f"@{test_agent.name} @{agent2.name} 帮我优化登录页交互",
                "mentions": [test_agent.id, agent2.id],
            },
        )
        events = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        assert any(event.get("type") == "orchestrator.task_completed" for event in events)
        assert any(event.get("type") == "session.title_updated" for event in events)
        session = (await test_client.get(f"/api/sessions/{sid}")).json()
        assert session["title"] == "登录页优化"

    async def test_unmentioned_steward_cancel_does_not_start_selected_agent(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        """调度器判断阶段被停止后，即使后续吐出决策，也不能继续启动普通 Agent。"""
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        calls: list[str] = []

        async def fake_stream(self, **kwargs):
            agent = kwargs["agent"]
            calls.append(agent.name)
            if (agent.primary_skill or "") == "orchestrator_planner":
                yield CliEvent("agent.process.started", "proc-steward")

                from app.models import Run
                from app.services.run_service import RunService

                rows = await db_session.execute(
                    select(Run).where(Run.session_id == kwargs["session_id"]).order_by(Run.started_at.desc())
                )
                run = rows.scalars().first()
                assert run is not None
                await RunService(db_session).cancel_run(run.id, "测试停止调度器判断")

                yield CliEvent(
                    "agent.output",
                    "proc-steward",
                    chunk=json.dumps({
                        "route_type": "single_agent",
                        "reply": f"我先交给 @{test_agent.name} 轻量处理。",
                        "selected_agent_ids": [test_agent.id],
                        "task_brief": "写代码",
                    }, ensure_ascii=False),
                    chunk_type="text",
                )
                yield CliEvent("agent.process.completed", "proc-steward", exit_code=0)
                return
            yield CliEvent("agent.output", "proc-agent", chunk="不应执行", chunk_type="text")
            yield CliEvent("agent.process.completed", "proc-agent", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id, orchestrator.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "帮我写代码"},
        )
        event_types = []
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            event_types.append(data.get("type", ""))

        assert "orchestrator.steward_decision" not in event_types
        assert "orchestrator.route" not in event_types
        assert "orchestrator.task_started" not in event_types
        assert calls == ["Orchestrator 调度器"]

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        assert any(message["sourceName"] == "运行控制" for message in messages)
        assert not any(message["agentName"] == test_agent.name for message in messages)

    async def test_group_chat_explicit_mentions_produce_tokens(
        self, test_client, test_agent, db_session,
    ):
        """@ 指定多个 Agent 时，仍可直接通过 subprocess 产出完整 token 流。"""
        agent2 = make_test_cli_agent("A2")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={
                "content": f"@{test_agent.name} @{agent2.name} Hello",
                "mentions": [test_agent.id, agent2.id],
            },
        )
        agent_tokens: dict[str, str] = {}
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                d = json.loads(line[6:])
                if d.get("agentId") and d.get("token") and not d.get("done"):
                    aid = d["agentId"]
                    agent_tokens[aid] = agent_tokens.get(aid, "") + d["token"]

        assert len(agent_tokens) == 2, f"Expected 2 agents to produce tokens, got {len(agent_tokens)}"
        for aid, text in agent_tokens.items():
            assert "Hello" in text, f"Agent {aid[:6]} missing 'Hello' in: {text[:50]}"
            assert "World" in text, f"Agent {aid[:6]} missing 'World' in: {text[:50]}"

    async def test_group_chat_reuses_agent_scoped_cli_session_process_between_turns(
        self, test_client, db_session, test_session, monkeypatch,
    ):
        """群聊同一 Agent 多轮复用群聊内专属常驻进程与 Engine session。"""
        session = await db_session.get(Session, test_session)
        session.mode = "group"
        session.agent_config_id = None
        agent = AgentConfig(
            id=str(uuid.uuid4()),
            name="Claude 群聊 Agent",
            description="测试群聊常驻进程",
            system_prompt="",
            agent_type="cli_wrapper",
            cli_tool="claude_code",
            executable=sys.executable,
            init_args="[]",
            env_vars="{}",
        )
        db_session.add(agent)
        await db_session.flush()
        db_session.add(SessionMember(session_id=test_session, agent_config_id=agent.id))
        await db_session.commit()

        calls = []

        async def fake_stream(self, **kwargs):
            calls.append(kwargs)
            process_id = "proc-group-claude"
            yield CliEvent(
                "agent.process.started",
                process_id,
                metadata={
                    "persistentProcess": True,
                    "reused": len(calls) > 1,
                    "recovered": False,
                    "engineSessionMode": kwargs.get("engine_session_mode"),
                    "engineSessionId": kwargs.get("engine_session_id"),
                },
            )
            yield CliEvent(
                "agent.output",
                process_id,
                chunk=f"group-turn-{len(calls)}",
                chunk_type="text",
            )
            yield CliEvent(
                "agent.process.turn_completed",
                process_id,
                exit_code=0,
                metadata={"persistentProcess": True},
            )

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "@Claude 群聊 Agent 第一轮", "mentions": [agent.id]},
        )
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "@Claude 群聊 Agent 第二轮", "mentions": [agent.id]},
        )

        assert len(calls) == 2
        assert calls[0]["persistent_process"] is True
        assert calls[1]["persistent_process"] is True
        assert calls[0]["runtime_session_id"] == f"{test_session}:agent:{agent.id}"
        assert calls[1]["runtime_session_id"] == calls[0]["runtime_session_id"]
        assert calls[0]["engine_session_mode"] == "start"
        assert calls[0]["engine_session_id"]
        assert calls[1]["engine_session_mode"] == "resume"
        assert calls[1]["engine_session_id"] == calls[0]["engine_session_id"]

        engine_rows = (await db_session.execute(
            select(EngineSession).where(
                EngineSession.session_id == test_session,
                EngineSession.agent_config_id == agent.id,
            )
        )).scalars().all()
        assert len(engine_rows) == 1
        assert engine_rows[0].engine_session_id == calls[0]["engine_session_id"]

        messages = (await test_client.get(f"/api/sessions/{test_session}/messages")).json()
        assistant_messages = [
            message for message in messages
            if message["role"] == "assistant" and message["sourceId"] == agent.id
        ]
        assert len(assistant_messages) == 2
        metadata = assistant_messages[-1]["metadata"]
        assert metadata["engineRuntime"]["mode"] == "persistent_process"
        assert metadata["engineRuntime"]["processScope"] == "one_group_session_agent_one_process"
        assert metadata["engineRuntime"]["runtimeSessionId"] == calls[0]["runtime_session_id"]
        assert metadata["engineRuntime"]["processKeptAlive"] is True
        assert metadata["engineRuntime"]["reused"] is True
        assert metadata["engineSession"]["mode"] == "resume"
        assert metadata["engineSession"]["id"] == calls[0]["engine_session_id"]

    async def test_group_chat_no_agent_crash(self, test_client, test_agent, db_session):
        """所有 SSE 事件必须是合法 JSON，无 @ 普通消息至少有调度器可见回复。"""
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id, orchestrator.id],
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

    async def test_group_chat_context_only_message_persisted(self, test_client, test_agent, db_session, monkeypatch):
        """无 @ 背景补充由可见 Orchestrator 调度器回复，不落系统整理消息。"""
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add(agent2)
        db_session.add(orchestrator)
        await db_session.commit()

        cli_called = 0

        async def fake_stream(self, **kwargs):
            nonlocal cli_called
            cli_called += 1
            yield CliEvent(
                "agent.output",
                "proc-steward",
                chunk=json.dumps({
                    "route_type": "context_only",
                    "reply": "已记录到群聊上下文，我不会启动执行。",
                    "reason": "用户补充项目约束。",
                    "selected_agent_ids": [],
                    "task_brief": "记录中文文档约束",
                    "confidence": 0.92,
                    "requires_approval": False,
                    "risk_level": "low",
                }, ensure_ascii=False),
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-steward", exit_code=0)
            return

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id, orchestrator.id],
        })
        sid = res.json()["id"]

        await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "这个项目所有文档都用中文，先别急着写代码。"},
        )

        resp = await test_client.get(f"/api/sessions/{sid}/messages")
        assert resp.status_code == 200
        msgs = resp.json()
        assert len(msgs) == 2
        steward = msgs[-1]
        assert steward["sourceType"] == "agent"
        assert steward["agentName"] == "Orchestrator 调度器"
        assert steward["sourceName"] == "Orchestrator 调度器"
        assert steward["contentType"] == "text"
        assert steward["content"] == "已记录到群聊上下文，我不会启动执行。"
        assert steward["metadata"]["stewardDecision"]["routeType"] == "context_only"
        assert cli_called == 1
        assert not any(m["sourceName"] == "调度器管家" for m in msgs)
        assert not any(m.get("contentType") == "orchestrator_summary" for m in msgs)

    async def test_unmentioned_legacy_group_without_orchestrator_gets_default_steward(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        """旧群聊缺少 Orchestrator 成员时，无 @ 也必须自动补管家并可见回复。"""
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        async def fake_stream(self, **kwargs):
            agent = kwargs["agent"]
            assert (agent.primary_skill or "") == "orchestrator_planner"
            yield CliEvent(
                "agent.output",
                "proc-steward",
                chunk=json.dumps({
                    "route_type": "context_only",
                    "reply": "已记录到群聊上下文，我不会启动执行。",
                    "reason": "用户补充项目文档语言约束。",
                    "selected_agent_ids": [],
                    "task_brief": "记录所有文档使用中文",
                    "confidence": 0.95,
                    "requires_approval": False,
                    "risk_level": "low",
                }, ensure_ascii=False),
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-steward", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]

        from app.models import SessionMember
        rows = await db_session.execute(
            select(SessionMember).join(
                AgentConfig, SessionMember.agent_config_id == AgentConfig.id,
            ).where(
                SessionMember.session_id == sid,
                AgentConfig.primary_skill == "orchestrator_planner",
            )
        )
        members = list(rows.scalars().all())
        assert members
        for member in members:
            await db_session.delete(member)
        await db_session.commit()

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "你们记住，这个项目所有文档都用中文"},
        )

        event_types = []
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            event_types.append(data.get("type", ""))

        assert "orchestrator.steward_decision" in event_types
        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        assert len(messages) == 2
        steward = messages[-1]
        assert steward["agentName"] == "Orchestrator 调度器"
        assert steward["content"] == "已记录到群聊上下文，我不会启动执行。"
        assert steward["metadata"]["stewardDecision"]["routeType"] == "context_only"

    async def test_unmentioned_product_alignment_routes_to_product_manager(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        """用户随口找产品经理时，无 @ 先由调度器 Agent 可见分流。"""
        product = make_test_cli_agent("产品经理")
        product.primary_skill = "product_manager"
        product.description = "产品 需求 PRD 业务"
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([product, orchestrator])
        await db_session.commit()

        async def fake_stream(self, **kwargs):
            agent = kwargs["agent"]
            if (agent.primary_skill or "") == "orchestrator_planner":
                yield CliEvent(
                    "agent.output",
                    "proc-steward",
                    chunk=json.dumps({
                        "route_type": "single_agent",
                        "reply": "我先请 @产品经理 对齐范围和验收标准。",
                        "reason": "用户明确希望和产品经理对齐。",
                        "selected_agent_ids": [product.id],
                        "task_brief": "对齐家庭资产管理 demo 的需求范围",
                        "confidence": 0.95,
                        "requires_approval": False,
                        "risk_level": "low",
                    }, ensure_ascii=False),
                    chunk_type="text",
                )
                yield CliEvent("agent.process.completed", "proc-steward", exit_code=0)
                return
            yield CliEvent("agent.output", "proc-1", chunk="产品范围已对齐。", chunk_type="text")
            yield CliEvent("agent.process.completed", "proc-1", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, product.id, orchestrator.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "想实现家庭资产管理 demo，有产品经理吗？我想和产品经理对齐一下"},
        )

        event_types = []
        agent_names = []
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if data.get("type"):
                event_types.append(data["type"])
            if data.get("type") == "agent.start":
                agent_names.append(data.get("agentName"))

        assert "orchestrator.steward_decision" in event_types
        assert "orchestrator.route" in event_types
        assert agent_names[0] == "Orchestrator 调度器"
        assert "产品经理" in agent_names

        resp = await test_client.get(f"/api/sessions/{sid}/messages")
        assert resp.status_code == 200
        msgs = resp.json()
        assert msgs[1]["agentName"] == "Orchestrator 调度器"
        assert msgs[1]["content"] == "我先请 @产品经理 对齐范围和验收标准。"
        assert any(message["agentName"] == "产品经理" for message in msgs)

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
            json={"content": f"@{test_agent.name} Hello", "mentions": [test_agent.id]},
        )
        assert resp.status_code == 200
        async for _line in resp.aiter_lines():
            pass

        assert seen and pinned.id in seen[0]

    async def test_group_chat_mentioned_agents_run_directly_without_steward(
        self, test_client, test_agent, db_session,
    ):
        """@ 多个普通 Agent 时直连被点名 Agent，不经过管家或 draft plan。"""
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
            json={
                "content": "先设计登录系统再前后端实现最后审查",
                "mentions": [agent.id for agent in agents],
            },
        )

        task_started = None
        event_types = []
        agent_ids = set()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if data.get("type"):
                event_types.append(data["type"])
            if data.get("type") == "orchestrator.task_started":
                task_started = data
            if data.get("agentId") and data.get("token") and not data.get("done"):
                agent_ids.add(data["agentId"])

        assert task_started is not None
        assert "orchestrator.steward_decision" not in event_types
        assert "orchestrator.route" in event_types
        assert "dag" not in task_started
        assert len(agent_ids) == 4

    async def test_unmentioned_complex_task_returns_draft_plan_only(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        """复杂无 @ 请求只生成 draft plan，用户批准前不直接拉普通 Agent 执行。"""
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        outputs = [
            {
                "route_type": "draft_plan",
                "reply": "这个需求涉及前后端、数据库和测试，我先生成 draft plan，确认后再执行。",
                "reason": "多阶段高成本任务。",
                "selected_agent_ids": [],
                "task_brief": "实现员工报销系统",
                "confidence": 0.96,
                "requires_approval": True,
                "risk_level": "high",
            },
            {
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

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "实现一套员工报销系统，包括数据库、API、前端和测试。"},
        )

        event_types = []
        done_message_id = None
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            event_types.append(data.get("type", ""))
            if data.get("done"):
                done_message_id = data.get("messageId")

        assert "orchestrator.steward_decision" in event_types
        assert "agent.start" in event_types
        assert "orchestrator.route" not in event_types
        assert "orchestrator.task_started" not in event_types

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        steward = messages[1]
        saved = next(message for message in messages if message["id"] == done_message_id)
        assert steward["agentName"] == "Orchestrator 调度器"
        assert steward["sourceType"] == "agent"
        assert steward["metadata"]["stewardDecision"]["routeType"] == "draft_plan"
        assert steward["content"] == "这个需求涉及前后端、数据库和测试，我先生成 draft plan，确认后再执行。"
        assert saved["agentName"] == "Orchestrator 调度器"
        assert saved["metadata"]["orchestratorPlan"]["ok"] is True
        assert saved["metadata"]["orchestratorPlan"]["normalizedPlan"]["tasks"][0]["title"] == "需求澄清"
        assert call_count == 2

    async def test_unmentioned_mini_collab_generates_bounded_draft_plan(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        """管家选择多个 Agent 时复用 plan-first，不直接启动普通 Agent。"""
        architect = make_test_cli_agent("架构师")
        architect.primary_skill = "architect"
        writer = make_test_cli_agent("文档专家")
        writer.primary_skill = "technical_writer"
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([architect, writer, orchestrator])
        await db_session.commit()

        calls: list[tuple[str, str]] = []
        outputs = [
            {
                "route_type": "mini_collab",
                "reply": "我会先生成一份小型协作计划，确认后再让文档专家和架构师执行。",
                "reason": "用户要求文档和架构师两个角色顺序协作。",
                "selected_agent_ids": [writer.id, architect.id],
                "task_brief": "先写文档，再做简要设计",
                "confidence": 0.9,
                "requires_approval": True,
                "risk_level": "medium",
            },
            {
                "plan_id": "plan_mini_collab_001",
                "tasks": [
                    {
                        "task_id": "T1",
                        "title": "正式 PRD 输出",
                        "goal": "基于用户需求输出可交接的 PRD",
                        "required_skills": ["technical_writer", "product_manager"],
                        "assigned_agent_id": writer.id,
                        "assigned_agent_name": writer.name,
                        "assignment_reason": "文档专家负责正式 PRD 与交接文档。",
                        "depends_on": [],
                        "expected_outputs": ["PRD 文档", "给架构师的交接说明"],
                        "acceptance_criteria": ["覆盖目标、范围、非目标和验收标准"],
                    },
                    {
                        "task_id": "T2",
                        "title": "技术设计",
                        "goal": "基于 PRD 输出简要技术设计",
                        "required_skills": ["architect"],
                        "assigned_agent_id": architect.id,
                        "assigned_agent_name": architect.name,
                        "assignment_reason": "架构师基于 PRD 产出技术边界和模块设计。",
                        "depends_on": ["T1"],
                        "expected_outputs": ["技术设计文档"],
                        "acceptance_criteria": ["只基于 T1 交接内容设计，不重写 PRD"],
                    },
                ],
            },
        ]

        async def fake_stream(self, **kwargs):
            agent = kwargs["agent"]
            prompt = json.dumps(kwargs["messages"], ensure_ascii=False)
            calls.append((agent.name, prompt))
            if (agent.primary_skill or "") == "orchestrator_planner":
                yield CliEvent(
                    "agent.output",
                    "proc-steward",
                    chunk=json.dumps(outputs[len(calls) - 1], ensure_ascii=False),
                    chunk_type="text",
                )
                yield CliEvent("agent.process.completed", "proc-steward", exit_code=0)
                return
            if agent.name == "架构师":
                yield CliEvent("agent.output", "proc-a", chunk="架构输出 A", chunk_type="text")
                yield CliEvent("agent.process.completed", "proc-a", exit_code=0)
                return
            yield CliEvent("agent.output", "proc-b", chunk="文档输出 B", chunk_type="text")
            yield CliEvent("agent.process.completed", "proc-b", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group",
            "agentConfigIds": [architect.id, writer.id, orchestrator.id],
        })
        sid = res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "写个文档吧然后找架构师简要设计"},
        )

        event_types = []
        agent_names = []
        done_message_id = None
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            event_types.append(data.get("type", ""))
            if data.get("type") == "agent.start":
                agent_names.append(data.get("agentName"))
            if data.get("done"):
                done_message_id = data.get("messageId")

        assert "orchestrator.steward_decision" in event_types
        assert "orchestrator.route" not in event_types
        assert "orchestrator.task_started" not in event_types
        assert agent_names == ["Orchestrator 调度器", "Orchestrator 调度器"]
        assert [name for name, _ in calls] == ["Orchestrator 调度器", "Orchestrator 调度器"]
        assert "route_type=mini_collab" in calls[1][1]
        assert "不要直接启动多个 Agent 执行" in calls[1][1]
        assert "@文档专家" in calls[1][1]
        assert "@架构师" in calls[1][1]

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        steward = messages[1]
        saved = next(message for message in messages if message["id"] == done_message_id)
        assert steward["metadata"]["stewardDecision"]["routeType"] == "mini_collab"
        assert steward["content"] == "我会先生成一份小型协作计划，确认后再让文档专家和架构师执行。"
        plan = saved["metadata"]["orchestratorPlan"]["normalizedPlan"]
        assert [task["assigned_agent_name"] for task in plan["tasks"]] == ["文档专家", "架构师"]
        assert plan["tasks"][1]["depends_on"] == ["T1"]

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
        assert "agent.output" not in event_types
        assert "orchestrator.route" not in event_types
        assert "orchestrator.task_started" not in event_types
        assert agent_tokens == ""

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        saved = next(message for message in messages if message["id"] == done_message_id)
        assert saved["agentName"] == "Orchestrator 调度器"
        assert saved["sourceType"] == "agent"
        assert saved["metadata"]["orchestratorPlan"]["ok"] is True
        assert saved["metadata"]["orchestratorPlan"]["normalizedPlan"]["tasks"][0]["title"] == "需求澄清"

    async def test_orchestrator_plan_only_flags_workspace_writes(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        async def fake_stream(self, **kwargs):
            workspace = Path(kwargs["workspace_path"])
            (workspace / "plan_001.json").write_text("{}", encoding="utf-8")
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

        await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 做员工报销系统", "mentions": [orchestrator.id]},
        )

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        saved = next(message for message in messages if message["agentName"] == "Orchestrator 调度器")
        metadata = saved["metadata"]
        assert metadata["orchestratorPlan"]["ok"] is False
        assert any("plan-only 阶段写入" in error for error in metadata["orchestratorPlan"]["validation"]["errors"])
        assert metadata["orchestratorWorkspaceChanges"][0]["path"] == "plan_001.json"

    async def test_text_mention_orchestrator_name_without_mention_id_uses_steward(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        agent2 = make_test_cli_agent("A2")
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([agent2, orchestrator])
        await db_session.commit()

        calls: list[str] = []

        async def fake_stream(self, **kwargs):
            calls.append(kwargs["agent"].name)
            yield CliEvent(
                "agent.output",
                "proc-1",
                chunk=json.dumps({
                    "route_type": "context_only",
                    "reply": "我先记录这条消息；如果要点名调度器，请从 @ 列表选择。",
                    "reason": "正文出现 @Orchestrator 但请求体没有 mentions id。",
                    "selected_agent_ids": [],
                    "task_brief": "记录手输提及文本",
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

        assert calls == ["Orchestrator 调度器"]
        assert "orchestrator.steward_decision" in event_types
        assert "agent.start" in event_types
        assert "orchestrator.route" not in event_types
        assert "orchestrator.task_started" not in event_types
        assert "我先记录这条消息" in token

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        latest = messages[-1]
        assert latest["metadata"]["stewardDecision"]["routeType"] == "context_only"

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
            if len(prompts) > len(outputs):
                yield CliEvent(
                    "agent.output",
                    "proc-task",
                    chunk="真实任务输出：群聊任务已完成。",
                    chunk_type="text",
                )
                yield CliEvent("agent.process.completed", "proc-task", exit_code=0)
                return
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
        assert completed["tasks"][0]["runnerType"] == "cli"
        assert completed["tasks"][0]["visibleMessageId"]

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        assert not any(message["contentType"] == "orchestrator_task_result" for message in messages)
        assert any(message["id"] == completed["tasks"][0]["visibleMessageId"] for message in messages)
        approval = messages[-1]
        approval = next(message for message in messages if message["metadata"] and "orchestratorAction" in message["metadata"])
        assert approval["metadata"]["orchestratorAction"]["action"] == "approve_plan"
        assert approval["metadata"]["orchestratorExecution"]["status"] == "completed"
        assert approval["metadata"]["orchestratorExecution"]["tasks"][0]["visibleMessageId"]

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

    async def test_unmentioned_plan_approval_bypasses_steward_and_creates_execution(
        self, test_client, db_session, monkeypatch,
    ):
        """无 @ 跟进上一版 draft plan 时，交给调度器 Agent 判断，不走管家硬分流。"""
        writer = make_test_cli_agent("文档专家")
        writer.primary_skill = "technical_writer"
        architect = make_test_cli_agent("架构师")
        architect.primary_skill = "architect"
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([writer, architect, orchestrator])
        await db_session.commit()

        prompts: list[str] = []
        task_agent_names: list[str] = []

        async def fake_stream(self, **kwargs):
            agent = kwargs["agent"]
            prompt = kwargs["messages"][-1]["content"]
            prompts.append(prompt)
            if (agent.primary_skill or "") == "orchestrator_planner":
                if "上一版 draft plan" in prompt:
                    yield CliEvent(
                        "agent.output",
                        "proc-approve",
                        chunk=json.dumps({
                            "action": "approve_plan",
                            "target_plan_id": "plan_no_at_approval_001",
                            "reason": "用户无 @ 回复允许执行，表示批准上一版计划",
                        }, ensure_ascii=False),
                        chunk_type="text",
                    )
                    yield CliEvent("agent.process.completed", "proc-approve", exit_code=0)
                    return
                if "四档含义" in prompt:
                    yield CliEvent(
                        "agent.output",
                        "proc-steward",
                        chunk=json.dumps({
                            "route_type": "single_agent",
                            "reply": "错误路径：不应该进入管家分流。",
                            "selected_agent_ids": [writer.id],
                            "task_brief": "错误分流",
                        }, ensure_ascii=False),
                        chunk_type="text",
                    )
                    yield CliEvent("agent.process.completed", "proc-steward", exit_code=0)
                    return
                yield CliEvent(
                    "agent.output",
                    "proc-plan",
                    chunk=json.dumps({
                        "plan_id": "plan_no_at_approval_001",
                        "tasks": [
                            {
                                "task_id": "T1",
                                "title": "编写正式PRD文档",
                                "goal": "输出中文 PRD 文档",
                                "required_skills": ["technical_writer"],
                                "assigned_agent_id": writer.id,
                                "assigned_agent_name": writer.name,
                                "depends_on": [],
                                "expected_outputs": ["docs/ 下的 PRD Markdown"],
                                "acceptance_criteria": ["只输出 PRD，不代写技术设计"],
                            },
                            {
                                "task_id": "T2",
                                "title": "编写技术设计文档",
                                "goal": "基于 T1 PRD 输出技术设计",
                                "required_skills": ["architect"],
                                "assigned_agent_id": architect.id,
                                "assigned_agent_name": architect.name,
                                "depends_on": ["T1"],
                                "expected_outputs": ["docs/ 下的技术设计 Markdown"],
                                "acceptance_criteria": ["基于 T1 交接产物设计，不重写 PRD"],
                            },
                        ],
                    }, ensure_ascii=False),
                    chunk_type="text",
                )
                yield CliEvent("agent.process.completed", "proc-plan", exit_code=0)
                return

            task_agent_names.append(agent.name)
            yield CliEvent(
                "agent.output",
                f"proc-{agent.name}",
                chunk=f"{agent.name} 已完成自己的 DAG 节点。",
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", f"proc-{agent.name}", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group",
            "agentConfigIds": [writer.id, architect.id, orchestrator.id],
        })
        sid = res.json()["id"]

        await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 先写 PRD，再让架构师设计", "mentions": [orchestrator.id]},
        )
        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "这个排布可以，先按它走吧；注意第一步只产出 PRD，第二步再做设计，不要混在一起。"},
        )

        event_types = []
        execution_event = None
        visible = ""
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            event_types.append(data.get("type", ""))
            if data.get("type") == "orchestrator.plan_execution_created":
                execution_event = data
            if data.get("agentName") == "Orchestrator 调度器":
                visible += data.get("token", "")

        assert "orchestrator.steward_decision" not in event_types
        assert "orchestrator.route" not in event_types
        assert execution_event is not None
        assert execution_event["planId"] == "plan_no_at_approval_001"
        assert "已确认计划 plan_no_at_approval_001" in visible
        assert any("上一版 draft plan" in prompt for prompt in prompts)
        assert not any("四档含义" in prompt for prompt in prompts)

        completed = await wait_execution_completed(test_client, execution_event["executionId"])
        assert completed["status"] == "completed", completed["events"][-1]
        assert [task["taskId"] for task in completed["tasks"]] == ["T1", "T2"]
        assert [task["assignedAgentName"] for task in completed["tasks"]] == ["文档专家", "架构师"]
        assert task_agent_names == ["文档专家", "架构师"]

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        assert not any(message["metadata"].get("stewardDecision") for message in messages if message["metadata"])
        approval = next(message for message in messages if message["metadata"] and "orchestratorAction" in message["metadata"])
        assert approval["metadata"]["orchestratorAction"]["action"] == "approve_plan"

    async def test_orchestrator_followup_discard_closes_pending_plan(
        self, test_client, db_session, monkeypatch,
    ):
        """调度器判定用户放弃上一版 plan 后，后续无 @ 消息重新进入管家分流。"""
        writer = make_test_cli_agent("文档专家")
        writer.primary_skill = "technical_writer"
        architect = make_test_cli_agent("架构师")
        architect.primary_skill = "architect"
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([writer, architect, orchestrator])
        await db_session.commit()

        prompts: list[str] = []

        async def fake_stream(self, **kwargs):
            agent = kwargs["agent"]
            prompt = kwargs["messages"][-1]["content"]
            prompts.append(prompt)
            if (agent.primary_skill or "") == "orchestrator_planner":
                if "上一版 draft plan" in prompt:
                    yield CliEvent(
                        "agent.output",
                        "proc-discard",
                        chunk=json.dumps({
                            "action": "discard_plan",
                            "target_plan_id": "plan_discard_001",
                            "reason": "用户明确表示先不执行这版计划",
                        }, ensure_ascii=False),
                        chunk_type="text",
                    )
                    yield CliEvent("agent.process.completed", "proc-discard", exit_code=0)
                    return
                if "四档含义" in prompt:
                    yield CliEvent(
                        "agent.output",
                        "proc-steward",
                        chunk=json.dumps({
                            "route_type": "context_only",
                            "reply": "已记录到群聊上下文，我不会启动执行。",
                            "reason": "用户补充新的背景约束。",
                            "selected_agent_ids": [],
                            "task_brief": "记录后续偏好",
                            "confidence": 0.91,
                            "requires_approval": False,
                            "risk_level": "low",
                        }, ensure_ascii=False),
                        chunk_type="text",
                    )
                    yield CliEvent("agent.process.completed", "proc-steward", exit_code=0)
                    return
                yield CliEvent(
                    "agent.output",
                    "proc-plan",
                    chunk=json.dumps({
                        "plan_id": "plan_discard_001",
                        "tasks": [
                            {
                                "task_id": "T1",
                                "title": "编写 PRD",
                                "goal": "输出 PRD",
                                "required_skills": ["technical_writer"],
                                "assigned_agent_id": writer.id,
                                "assigned_agent_name": writer.name,
                                "depends_on": [],
                            },
                            {
                                "task_id": "T2",
                                "title": "技术设计",
                                "goal": "基于 PRD 输出设计",
                                "required_skills": ["architect"],
                                "assigned_agent_id": architect.id,
                                "assigned_agent_name": architect.name,
                                "depends_on": ["T1"],
                            },
                        ],
                    }, ensure_ascii=False),
                    chunk_type="text",
                )
                yield CliEvent("agent.process.completed", "proc-plan", exit_code=0)
                return
            yield CliEvent("agent.output", "proc-task", chunk="不应执行普通 Agent。", chunk_type="text")
            yield CliEvent("agent.process.completed", "proc-task", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group",
            "agentConfigIds": [writer.id, architect.id, orchestrator.id],
        })
        sid = res.json()["id"]

        await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 先写 PRD，再让架构师设计", "mentions": [orchestrator.id]},
        )
        discard_resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "这版先不走了，暂时取消这个计划。", "mentions": []},
        )

        discard_events = []
        visible = ""
        async for line in discard_resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            discard_events.append(data.get("type", ""))
            if data.get("agentName") == "Orchestrator 调度器":
                visible += data.get("token", "")

        assert "orchestrator.plan_execution_created" not in discard_events
        assert "orchestrator.plan_discarded" in discard_events
        assert "已放弃计划 plan_discard_001" in visible
        assert any("上一版 draft plan" in prompt for prompt in prompts)

        followup_resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "后面文档还是都用中文。", "mentions": []},
        )
        followup_events = []
        async for line in followup_resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            followup_events.append(data.get("type", ""))

        assert "orchestrator.steward_decision" in followup_events
        assert prompts[-1].count("四档含义") == 1
        assert "上一版 draft plan" not in prompts[-1]

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        plan_message = next(message for message in messages if message["metadata"] and "orchestratorPlan" in message["metadata"])
        assert plan_message["metadata"]["orchestratorPlan"]["normalizedPlan"]["status"] == "discarded"
        action_message = next(message for message in messages if message["metadata"] and "orchestratorPlanState" in message["metadata"])
        assert action_message["metadata"]["orchestratorPlanState"]["status"] == "discarded"

    async def test_orchestrator_approve_auto_assigns_missing_task_agent(
        self, test_client, test_agent, db_session, monkeypatch,
    ):
        backend_agent = make_test_cli_agent("后端专家")
        backend_agent.primary_skill = "backend_engineer"
        frontend_agent = make_test_cli_agent("前端专家")
        frontend_agent.primary_skill = "frontend_engineer"
        orchestrator = make_test_cli_agent("Orchestrator 调度器")
        orchestrator.primary_skill = "orchestrator_planner"
        orchestrator.context_policy = "planning_only"
        db_session.add_all([backend_agent, frontend_agent, orchestrator])
        await db_session.commit()

        prompts: list[str] = []
        outputs = [
            {
                "plan_id": "plan_missing_assignment_001",
                "tasks": [
                    {
                        "task_id": "T1",
                        "title": "后端开发",
                        "goal": "完成 API",
                        "required_skills": ["backend_engineer"],
                        "assigned_agent_id": backend_agent.id,
                        "assigned_agent_name": backend_agent.name,
                        "depends_on": [],
                    },
                    {
                        "task_id": "T2",
                        "title": "前后端联调",
                        "goal": "完成接口对接",
                        "required_skills": ["backend_engineer", "frontend_engineer"],
                        "assigned_agent_id": None,
                        "assigned_agent_name": None,
                        "depends_on": ["T1"],
                    },
                ],
            },
            {
                "action": "approve_plan",
                "target_plan_id": "plan_missing_assignment_001",
                "reason": "用户确认执行",
            },
        ]

        async def fake_stream(self, **kwargs):
            prompts.append(kwargs["messages"][-1]["content"])
            if len(prompts) > len(outputs):
                yield CliEvent(
                    "agent.output",
                    "proc-task",
                    chunk="真实任务输出：自动补分配后执行完成。",
                    chunk_type="text",
                )
                yield CliEvent("agent.process.completed", "proc-task", exit_code=0)
                return
            yield CliEvent(
                "agent.output",
                "proc-1",
                chunk=json.dumps(outputs[len(prompts) - 1], ensure_ascii=False),
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-1", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        res = await test_client.post("/api/sessions", json={
            "mode": "group",
            "agentConfigIds": [backend_agent.id, frontend_agent.id, orchestrator.id],
        })
        sid = res.json()["id"]

        await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 做员工报销系统", "mentions": [orchestrator.id]},
        )
        resp = await test_client.post(
            f"/api/sessions/{sid}/chat",
            json={"content": "@Orchestrator 调度器 开始执行", "mentions": [orchestrator.id]},
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
        assert "计划暂时无法进入执行" not in visible
        assert "已自动将 T2 分配给" in visible
        t2 = next(task for task in execution_event["tasks"] if task["taskId"] == "T2")
        assert t2["assignedAgentId"] in {backend_agent.id, frontend_agent.id}
        assert t2["assignedAgentName"]

        completed = await wait_execution_completed(test_client, execution_event["executionId"])
        assert completed["status"] == "completed", completed["events"][-1]
        completed_t2 = next(task for task in completed["tasks"] if task["taskId"] == "T2")
        assert completed_t2["assignedAgentId"] == t2["assignedAgentId"]

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        approval = next(message for message in messages if message["metadata"] and "orchestratorAction" in message["metadata"])
        fixups = approval["metadata"]["orchestratorAssignmentFixups"]
        assert fixups[0]["taskId"] == "T2"

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
        assert visible == ""

        messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
        latest = messages[-1]
        assert latest["metadata"]["orchestratorPlan"]["normalizedPlan"]["plan_id"] == "plan_revision_002"
        assert latest["metadata"]["orchestratorPlan"]["normalizedPlan"]["tasks"][0]["title"] == "修改后的计划"
        assert "orchestratorExecution" not in latest["metadata"]
