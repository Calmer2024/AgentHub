"""Phase 4 end-to-end API acceptance over the ASGI app."""

import json

import pytest


@pytest.mark.asyncio
async def test_phase4_acceptance_single_and_group_flow(test_client, test_agent, db_session):
    """验收主链路：单聊发送 → 引用 → Pin → 搜索 → 重生成 → 群聊发送。"""
    from app.models import AgentConfig

    single = await test_client.post("/api/sessions", json={
        "title": "Phase4 单聊验收",
        "mode": "single",
        "agentConfigId": test_agent.id,
    })
    assert single.status_code == 201
    sid = single.json()["id"]

    chat = await test_client.post(f"/api/sessions/{sid}/chat", json={"content": "记录中文关键词：向量数据库"})
    assert chat.status_code == 200
    async for _line in chat.aiter_lines():
        pass

    messages = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
    user_msg = [m for m in messages if m["role"] == "user"][0]
    assistant_msg = [m for m in messages if m["role"] == "assistant"][0]

    reply = await test_client.post(f"/api/messages/{assistant_msg['id']}/reply", json={"content": "引用后继续讨论"})
    assert reply.status_code == 201
    assert reply.json()["parentMessageId"] == assistant_msg["id"]

    pin = await test_client.post(f"/api/messages/{user_msg['id']}/pin")
    assert pin.status_code == 200
    refreshed = (await test_client.get(f"/api/sessions/{sid}/messages")).json()
    assert [m for m in refreshed if m["id"] == user_msg["id"]][0]["isPinned"] is True

    search = await test_client.get("/api/messages/search", params={
        "session_id": sid,
        "q": "向量数据库",
    })
    assert search.status_code == 200
    assert search.json()[0]["highlight"]

    regen = await test_client.post(f"/api/messages/{assistant_msg['id']}/regenerate")
    assert regen.status_code == 200
    done = False
    async for line in regen.aiter_lines():
        if line.startswith("data: "):
            done = json.loads(line[6:]).get("done", False)
    assert done

    unpin = await test_client.delete(f"/api/messages/{user_msg['id']}/pin")
    assert unpin.status_code == 200

    agent2 = AgentConfig(id="phase4-agent-2", name="Phase4 B", provider="deepseek", model="d")
    db_session.add(agent2)
    await db_session.commit()
    group = await test_client.post("/api/sessions", json={
        "title": "Phase4 群聊验收",
        "mode": "group",
        "agentConfigIds": [test_agent.id, agent2.id],
    })
    assert group.status_code == 201
    group_chat = await test_client.post(
        f"/api/sessions/{group.json()['id']}/chat",
        json={"content": "Hello group"},
    )
    assert group_chat.status_code == 200
    events = []
    async for line in group_chat.aiter_lines():
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if data.get("type"):
                events.append(data["type"])
    assert "orchestrator.task_started" in events
    assert "orchestrator.task_completed" in events
