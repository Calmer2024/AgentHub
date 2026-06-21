"""Phase 4 message actions/search API tests."""

import json
import uuid
from pathlib import Path

import pytest

from sqlalchemy import select

from app.models import Message, Project, Session as DBSession


@pytest.mark.asyncio
class TestPhase4MessageActions:
    async def test_reply_persists_parent_message_id(self, test_client, db_session, test_session):
        parent = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="assistant",
            content="这是原消息",
            agent_name="测试 Agent",
            source_type="agent",
            source_name="测试 Agent",
        )
        db_session.add(parent)
        await db_session.commit()

        resp = await test_client.post(
            f"/api/messages/{parent.id}/reply",
            json={"content": "引用回复"},
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "引用回复"
        assert data["parentMessageId"] == parent.id
        assert data["metadata"]["replyReference"]["id"] == parent.id
        assert data["metadata"]["replyReference"]["content"] == "这是原消息"

    async def test_pin_and_unpin_message(self, test_client, db_session, test_session):
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="user",
            content="关键约束",
            source_type="user",
            source_name="用户",
        )
        db_session.add(msg)
        await db_session.commit()

        pin_resp = await test_client.post(f"/api/messages/{msg.id}/pin")
        assert pin_resp.status_code == 200
        pin_data = pin_resp.json()
        assert (pin_data.get("is_pinned") or pin_data.get("isPinned")) is True

        list_resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        pinned = [m for m in list_resp.json() if m["id"] == msg.id][0]
        assert pinned["isPinned"] is True

        unpin_resp = await test_client.delete(f"/api/messages/{msg.id}/pin")
        assert unpin_resp.status_code == 200
        unpin_data = unpin_resp.json()
        assert (unpin_data.get("is_pinned") if "is_pinned" in unpin_data else unpin_data.get("isPinned")) is False

    async def test_regenerate_replaces_assistant_content_and_keeps_version(
        self, test_client, db_session, test_session,
    ):
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "第一轮"},
        )
        list_resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        assistant = [m for m in list_resp.json() if m["role"] == "assistant"][0]

        resp = await test_client.post(f"/api/messages/{assistant['id']}/regenerate")
        assert resp.status_code == 200
        full = ""
        done = False
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                full += data.get("token") or ""
                done = bool(data.get("done"))

        assert done
        assert full == "Hello, World!"

        after = await test_client.get(f"/api/sessions/{test_session}/messages")
        updated = [m for m in after.json() if m["id"] == assistant["id"]][0]
        assert updated["content"] == "Hello, World!"
        assert updated["metadata"]["versions"][0]["content"] == assistant["content"]

    async def test_single_chat_uses_pinned_context(
        self, test_client, db_session, test_session,
    ):
        pinned = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="user",
            content="必须保留的 Pin 背景",
            source_type="user",
            source_name="用户",
            is_pinned="1",
        )
        db_session.add(pinned)
        await db_session.commit()

        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "现在回答"},
        )
        assert resp.status_code == 200
        async for _line in resp.aiter_lines():
            pass

        prompt_text = await _read_cli_stdin(db_session, test_session)
        assert "[Pinned message]" in prompt_text
        assert "必须保留的 Pin 背景" in prompt_text

    async def test_reply_context_is_visible_to_agent(
        self, test_client, db_session, test_session,
    ):
        """引用不是只存 parentMessageId，Agent 输入中必须能看到被引用内容。"""
        parent = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="assistant",
            content="被引用的关键结论：使用事件溯源",
            agent_name="测试 Agent",
            source_type="agent",
            source_name="测试 Agent",
        )
        db_session.add(parent)
        await db_session.commit()

        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "基于我引用的这条继续展开", "parentMessageId": parent.id},
        )
        assert resp.status_code == 200
        async for _line in resp.aiter_lines():
            pass

        prompt_text = await _read_cli_stdin(db_session, test_session)
        assert "用户引用了以下历史消息" in prompt_text
        assert "被引用的关键结论：使用事件溯源" in prompt_text

        after = await test_client.get(f"/api/sessions/{test_session}/messages")
        sent = [m for m in after.json() if m["parentMessageId"] == parent.id][0]
        assert sent["metadata"]["replyReference"]["id"] == parent.id
        assert sent["metadata"]["replyReference"]["content"] == "被引用的关键结论：使用事件溯源"


@pytest.mark.asyncio
class TestPhase4MessageSearch:
    async def test_search_chinese_keyword_returns_highlight(self, test_client, db_session, test_session):
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=test_session,
            role="user",
            content="这里记录一个中文关键词：向量数据库",
            source_type="user",
            source_name="用户",
        )
        db_session.add(msg)
        await db_session.commit()

        resp = await test_client.get(
            "/api/messages/search",
            params={"session_id": test_session, "q": "向量数据库"},
        )

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["id"] == msg.id
        assert "<mark>向量数据库</mark>" in results[0]["highlight"]

    async def test_search_empty_result(self, test_client, test_session):
        resp = await test_client.get(
            "/api/messages/search",
            params={"session_id": test_session, "q": "不存在的关键词"},
        )

        assert resp.status_code == 200
        assert resp.json() == []


async def _read_cli_stdin(db_session, session_id: str) -> str:
    result = await db_session.execute(
        select(Project.workspace_path)
        .join(DBSession, DBSession.project_id == Project.id)
        .where(DBSession.id == session_id)
    )
    workspace_path = result.scalar_one()
    path = Path(workspace_path) / ".agenthub-cli-stdin.txt"
    assert path.exists()
    return path.read_text(encoding="utf-8")
