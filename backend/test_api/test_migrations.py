"""迁移验证测试 —— 确认 lifespan 执行了全部迁移且 schema 完整。"""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_all_migrations_applied(test_client):
    """lifespan 触发后，全部迁移都记录在 _migrations_history。"""
    from app.database import AsyncSessionLocal
    from migrations.migration_runner import MIGRATIONS_DIR

    async with AsyncSessionLocal() as s:
        r = await s.execute(text("SELECT COUNT(*) FROM _migrations_history"))
        count = r.scalar()
        expected = len([f for f in MIGRATIONS_DIR.iterdir() if f.suffix == ".sql"])
        assert count == expected, f"预期 {expected} 条迁移记录，实际 {count}"


@pytest.mark.asyncio
async def test_fts_virtual_table_exists(test_client):
    """FTS5 虚拟表 messages_fts 已创建。"""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        r = await s.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
        ))
        assert r.scalar() is not None, "messages_fts 虚拟表缺失"


@pytest.mark.asyncio
async def test_fts_triggers_created(test_client):
    """FTS5 同步触发器已创建。"""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        r = await s.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))
        triggers = {row[0] for row in r.fetchall()}
        for name in ("messages_fts_insert", "messages_fts_delete", "messages_fts_update"):
            assert name in triggers, f"触发器 {name} 缺失"

        r = await s.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='messages_fts_update'"
        ))
        assert "AFTER UPDATE OF content" in (r.scalar() or "")


@pytest.mark.asyncio
async def test_new_columns_exist(test_client):
    """Phase 3 新增列已通过迁移添加。"""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        r = await s.execute(text("PRAGMA table_info('messages')"))
        msg_cols = {row[1] for row in r.fetchall()}
        assert "parent_message_id" in msg_cols
        assert "is_pinned" in msg_cols
        assert "content_type" in msg_cols
        assert "source_type" in msg_cols
        assert "source_id" in msg_cols
        assert "source_name" in msg_cols
        assert "metadata_json" in msg_cols

        r = await s.execute(text("PRAGMA table_info('artifacts')"))
        art_cols = {row[1] for row in r.fetchall()}
        assert "version" in art_cols
        assert "parent_artifact_id" in art_cols
        assert "project_id" in art_cols
        assert "file_path" in art_cols
        assert "preview_id" in art_cols

        r = await s.execute(text("PRAGMA table_info('sessions')"))
        session_cols = {row[1] for row in r.fetchall()}
        assert "project_id" in session_cols
        assert "is_pinned" in session_cols
        assert "archived_at" in session_cols
        assert "unread_count" in session_cols
        assert "last_read_at" in session_cols
        assert "is_muted" in session_cols

        r = await s.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
        ))
        assert r.scalar() is not None

        r = await s.execute(text("PRAGMA table_info('agent_configs')"))
        agent_cols = {row[1] for row in r.fetchall()}
        assert "primary_skill" in agent_cols
        assert "auxiliary_skills" in agent_cols
        assert "context_policy" in agent_cols
        assert "rules" in agent_cols


@pytest.mark.asyncio
async def test_default_agent_seeded(test_client):
    """lifespan 创建的默认 Agent 存在。"""
    r = await test_client.get("/api/agents")
    assert r.status_code == 200
    agents = r.json()
    assert len(agents) >= 1, "lifespan 应种子默认 AgentConfig"


@pytest.mark.asyncio
async def test_event_bus_running(test_client):
    """EventBus 已在 lifespan 中启动。"""
    from app.main import _event_bus
    assert _event_bus._task is not None, "EventBus dispatcher 任务未启动"
