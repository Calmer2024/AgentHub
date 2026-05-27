import uuid
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
