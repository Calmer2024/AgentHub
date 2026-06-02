import uuid
import json
import pytest


@pytest.mark.asyncio
class TestGroupSession:
    async def test_create_group_session(self, test_client, test_agent, db_session):
        from app.models import AgentConfig
        agent2 = AgentConfig(id=str(uuid.uuid4()), name="A2", provider="deepseek", model="d")
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
        from app.models import AgentConfig
        agent2 = AgentConfig(id=str(uuid.uuid4()), name="A2", provider="deepseek", model="d")
        db_session.add(agent2)
        await db_session.commit()

        res = await test_client.post("/api/sessions", json={
            "mode": "group", "agentConfigIds": [test_agent.id, agent2.id],
        })
        sid = res.json()["id"]

        res2 = await test_client.get(f"/api/sessions/{sid}/members")
        assert res2.status_code == 200
        members = res2.json()
        assert len(members) == 2

    async def test_single_mode_still_works(self, test_client, test_agent):
        res = await test_client.post("/api/sessions", json={
            "agentConfigId": test_agent.id, "mode": "single"
        })
        assert res.status_code == 201
        assert res.json()["mode"] == "single"

    # === 新增：群聊消息发送测试 (覆盖 AgentExecutor._execute_single 路径) ===

    async def test_group_chat_sse_returns_200(self, test_client, test_agent, db_session):
        """群聊发送消息 → AgentExecutor 路径 → 200 响应。"""
        from app.models import AgentConfig
        agent2 = AgentConfig(id=str(uuid.uuid4()), name="A2", provider="deepseek", model="d")
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
        from app.models import AgentConfig
        agent2 = AgentConfig(id=str(uuid.uuid4()), name="A2", provider="deepseek", model="d")
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

    async def test_group_chat_mock_agent_produces_tokens(self, test_client, test_agent, db_session):
        """MockAgent 在群聊模式下应产出完整 token 流。"""
        from app.models import AgentConfig
        agent2 = AgentConfig(id=str(uuid.uuid4()), name="A2", provider="deepseek", model="d")
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

        # MockAgent 对每个 Agent 产生 ["Hello", ", ", "World", "!"]
        assert len(agent_tokens) == 2, f"Expected 2 agents to produce tokens, got {len(agent_tokens)}"
        for aid, text in agent_tokens.items():
            assert "Hello" in text, f"Agent {aid[:6]} missing 'Hello' in: {text[:50]}"
            assert "World" in text, f"Agent {aid[:6]} missing 'World' in: {text[:50]}"

    async def test_group_chat_no_agent_crash(self, test_client, test_agent, db_session):
        """所有 SSE 事件必须是合法 JSON，done 事件不早于 task_completed 之前截断。"""
        from app.models import AgentConfig
        agent2 = AgentConfig(id=str(uuid.uuid4()), name="A2", provider="deepseek", model="d")
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
        assert not had_error, "Group chat should not produce global error with MockAgent"

    async def test_group_chat_messages_persisted(self, test_client, test_agent, db_session):
        """群聊完成后，Agent 消息应持久化到数据库。"""
        from app.models import AgentConfig
        agent2 = AgentConfig(id=str(uuid.uuid4()), name="A2", provider="deepseek", model="d")
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
        from app.models import AgentConfig, Message
        from app.domain.orchestrator_v2 import OrchestratorV2

        agent2 = AgentConfig(id=str(uuid.uuid4()), name="A2", provider="deepseek", model="d")
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
        from app.models import AgentConfig
        agents = [
            AgentConfig(id=str(uuid.uuid4()), name="架构师", provider="deepseek", model="d",
                        description="架构 设计 方案", system_prompt="擅长架构设计"),
            AgentConfig(id=str(uuid.uuid4()), name="前端", provider="deepseek", model="d",
                        description="React 前端 UI", system_prompt="擅长前端开发"),
            AgentConfig(id=str(uuid.uuid4()), name="后端", provider="deepseek", model="d",
                        description="Python 后端 API 数据库", system_prompt="擅长后端开发"),
            AgentConfig(id=str(uuid.uuid4()), name="审查员", provider="deepseek", model="d",
                        description="审查 测试 安全", system_prompt="擅长代码审查"),
        ]
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
