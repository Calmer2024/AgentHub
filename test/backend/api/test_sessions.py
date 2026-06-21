import pytest


@pytest.mark.asyncio
class TestCreateSession:
    async def test_create_with_title(self, test_client, test_agent):
        resp = await test_client.post("/api/sessions", json={
            "title": "我的会话", "agentConfigId": test_agent.id
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "我的会话"
        assert data["agentConfigId"] == test_agent.id
        assert "id" in data
        assert "createdAt" in data

    async def test_create_defaults(self, test_client):
        """传空 JSON 时自动使用 lifespan 种子的默认 Agent。"""
        resp = await test_client.post("/api/sessions", json={})
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "新对话"
        assert data["agentConfigId"] is not None  # lifespan 种子

    async def test_create_with_agent(self, test_client, test_agent):
        """指定 agentConfigId 创建会话。"""
        resp = await test_client.post("/api/sessions", json={
            "title": "X", "agentConfigId": test_agent.id,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["agentConfigId"] == test_agent.id


@pytest.mark.asyncio
class TestListSessions:
    async def test_empty_list(self, test_client):
        """事务隔离下初始无会话（lifespan 不创建会话）。"""
        resp = await test_client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(self, test_client, test_agent):
        await test_client.post("/api/sessions", json={"agentConfigId": test_agent.id})
        await test_client.post("/api/sessions", json={"agentConfigId": test_agent.id})
        resp = await test_client.get("/api/sessions")
        assert len(resp.json()) == 2


@pytest.mark.asyncio
class TestUpdateSession:
    async def test_switch_agent(self, test_client, test_session, db_session):
        from app.models import AgentConfig
        import uuid
        agent2 = AgentConfig(
            id=str(uuid.uuid4()),
            name="A2",
            description="",
            system_prompt="",
            agent_type="cli_wrapper",
            cli_tool="custom",
            executable="python",
            init_args="[]",
            env_vars="{}",
        )
        db_session.add(agent2)
        await db_session.commit()

        resp = await test_client.patch(f"/api/sessions/{test_session}", json={
            "agentConfigId": agent2.id
        })
        assert resp.status_code == 200
        assert resp.json()["agentConfigId"] == agent2.id

    async def test_switch_invalid_agent(self, test_client, test_session):
        resp = await test_client.patch(f"/api/sessions/{test_session}", json={
            "agentConfigId": "nonexistent-id"
        })
        assert resp.status_code == 400

    async def test_mute_and_mark_read(self, test_client, test_session, db_session):
        from app.models import Session as DBSession

        session = await db_session.get(DBSession, test_session)
        session.unread_count = 4
        await db_session.commit()

        muted = await test_client.patch(f"/api/sessions/{test_session}", json={"isMuted": True})
        assert muted.status_code == 200
        assert muted.json()["isMuted"] is True

        read = await test_client.post(f"/api/sessions/{test_session}/read")
        assert read.status_code == 200
        assert read.json()["unreadCount"] == 0
        assert read.json()["lastReadAt"] is not None


@pytest.mark.asyncio
class TestGroupMembers:
    async def test_add_and_remove_group_member(self, test_client, test_agent, db_session):
        from app.models import AgentConfig
        import uuid

        agent2 = AgentConfig(
            id=str(uuid.uuid4()),
            name="A2",
            description="",
            system_prompt="",
            agent_type="cli_wrapper",
            cli_tool="custom",
            executable="python",
            init_args="[]",
            env_vars="{}",
        )
        agent3 = AgentConfig(
            id=str(uuid.uuid4()),
            name="A3",
            description="",
            system_prompt="",
            agent_type="cli_wrapper",
            cli_tool="custom",
            executable="python",
            init_args="[]",
            env_vars="{}",
        )
        db_session.add_all([agent2, agent3])
        await db_session.commit()

        created = await test_client.post("/api/sessions", json={
            "title": "群管理",
            "mode": "group",
            "agentConfigIds": [test_agent.id, agent2.id],
        })
        assert created.status_code == 201
        session_id = created.json()["id"]

        added = await test_client.post(f"/api/sessions/{session_id}/members", json={
            "agentConfigId": agent3.id,
        })
        assert added.status_code == 200
        assert any(member["agentConfigId"] == agent3.id for member in added.json())

        removed = await test_client.delete(f"/api/sessions/{session_id}/members/{agent3.id}")
        assert removed.status_code == 200
        assert not any(member["agentConfigId"] == agent3.id for member in removed.json())

    async def test_group_member_minimum_is_enforced(self, test_client, test_agent, db_session):
        from app.models import AgentConfig
        import uuid

        agent2 = AgentConfig(
            id=str(uuid.uuid4()),
            name="A2",
            description="",
            system_prompt="",
            agent_type="cli_wrapper",
            cli_tool="custom",
            executable="python",
            init_args="[]",
            env_vars="{}",
        )
        agent3 = AgentConfig(
            id=str(uuid.uuid4()),
            name="A3",
            description="",
            system_prompt="",
            agent_type="cli_wrapper",
            cli_tool="custom",
            executable="python",
            init_args="[]",
            env_vars="{}",
        )
        db_session.add_all([agent2, agent3])
        await db_session.commit()

        created = await test_client.post("/api/sessions", json={
            "title": "群管理",
            "mode": "group",
            "agentConfigIds": [test_agent.id, agent2.id, agent3.id],
        })
        session_id = created.json()["id"]

        members = (await test_client.get(f"/api/sessions/{session_id}/members")).json()
        for member in members[2:]:
            first_remove = await test_client.delete(
                f"/api/sessions/{session_id}/members/{member['agentConfigId']}",
            )
            assert first_remove.status_code == 200

        remaining = (await test_client.get(f"/api/sessions/{session_id}/members")).json()
        assert len(remaining) == 2
        blocked = await test_client.delete(f"/api/sessions/{session_id}/members/{remaining[0]['agentConfigId']}")
        assert blocked.status_code == 400

    async def test_member_management_rejects_single_chat(self, test_client, test_session, test_agent):
        resp = await test_client.post(f"/api/sessions/{test_session}/members", json={
            "agentConfigId": test_agent.id,
        })
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestForwardMessages:
    async def test_forward_messages(self, test_client, test_session, test_agent, db_session):
        from app.models import Message
        import uuid

        target = await test_client.post("/api/sessions", json={
            "title": "目标会话",
            "agentConfigId": test_agent.id,
        })
        assert target.status_code == 201
        message_id = str(uuid.uuid4())
        db_session.add(Message(
            id=message_id,
            session_id=test_session,
            role="assistant",
            content="请转发这条结论",
            content_type="text",
            agent_name="测试 Agent",
            source_type="agent",
            source_id=test_agent.id,
            source_name="测试 Agent",
        ))
        await db_session.commit()

        resp = await test_client.post("/api/sessions/forward", json={
            "messageIds": [message_id],
            "targetSessionIds": [target.json()["id"]],
        })

        assert resp.status_code == 201
        data = resp.json()
        assert len(data["messages"]) == 1
        forwarded = data["messages"][0]
        assert forwarded["sessionId"] == target.json()["id"]
        assert forwarded["role"] == "user"
        assert "转发自 测试 Agent" in forwarded["content"]
        assert forwarded["metadata"]["forwardSource"]["id"] == message_id
