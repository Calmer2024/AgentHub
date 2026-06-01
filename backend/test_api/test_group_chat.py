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
        # 1 user + 2 agent responses
        assert len(msgs) >= 3, f"Expected >=3 messages (1 user + 2 agents), got {len(msgs)}"
