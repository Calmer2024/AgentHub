"""Migration Runner 单元测试 —— 覆盖顺序执行、跳过已执行、历史表。

使用临时磁盘文件数据库（FTS5 在内存数据库中不受支持）。
所有操作在同一个 Connection 中完成以确保表可见。
"""
import os
import tempfile
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def conn():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite+aiosqlite:///{path}"
    eng = create_async_engine(db_url, echo=False)

    async with eng.connect() as connection:
        # 用原始 SQL 创建 Phase 2 基础表（不含新列）
        for ddl in _PHASE2_DDL:
            try:
                await connection.execute(text(ddl))
            except Exception:
                pass
        await connection.commit()
        yield connection

    await eng.dispose()
    os.unlink(path)


# Phase 2 schema — 不含 parent_message_id, is_pinned, version, parent_artifact_id
_PHASE2_DDL = [
    "CREATE TABLE IF NOT EXISTS sessions ("
    "  id VARCHAR PRIMARY KEY, title VARCHAR, agent_config_id VARCHAR,"
    "  agent_name VARCHAR, mode VARCHAR DEFAULT 'single',"
    "  is_active VARCHAR DEFAULT '1', created_at TIMESTAMP, updated_at TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS agent_configs ("
    "  id VARCHAR PRIMARY KEY, name VARCHAR, description VARCHAR,"
    "  system_prompt VARCHAR, provider VARCHAR, model VARCHAR,"
    "  temperature FLOAT DEFAULT 0.7, is_active BOOLEAN DEFAULT 1,"
    "  created_at TIMESTAMP, updated_at TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS messages ("
    "  id VARCHAR PRIMARY KEY, session_id VARCHAR, role VARCHAR,"
    "  content VARCHAR, agent_name VARCHAR, created_at TIMESTAMP,"
    "  FOREIGN KEY(session_id) REFERENCES sessions(id))",
    "CREATE TABLE IF NOT EXISTS artifacts ("
    "  id VARCHAR PRIMARY KEY, session_id VARCHAR, message_id VARCHAR,"
    "  type VARCHAR, title VARCHAR, content VARCHAR,"
    "  status VARCHAR DEFAULT 'rendering', created_at TIMESTAMP,"
    "  FOREIGN KEY(session_id) REFERENCES sessions(id),"
    "  FOREIGN KEY(message_id) REFERENCES messages(id))",
    "CREATE TABLE IF NOT EXISTS session_members ("
    "  session_id VARCHAR, agent_config_id VARCHAR, joined_at TIMESTAMP,"
    "  PRIMARY KEY(session_id, agent_config_id))",
]


class TestMigrationRunner:
    async def test_run_creates_history_table(self, conn):
        from migrations.migration_runner import run
        await run(conn)

        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations_history'"
        ))
        assert result.fetchone() is not None

    async def test_run_applies_all_migrations(self, conn):
        from migrations.migration_runner import MIGRATIONS_DIR, run
        await run(conn)

        result = await conn.execute(text("SELECT filename FROM _migrations_history ORDER BY filename"))
        executed = [row[0] for row in result.fetchall()]
        expected = [f.name for f in sorted(MIGRATIONS_DIR.iterdir()) if f.suffix == ".sql"]
        assert executed == expected
        assert executed[0] == "001_add_message_parent_id.sql"

    async def test_rerun_skips_already_executed(self, conn):
        from migrations.migration_runner import MIGRATIONS_DIR, run
        await run(conn)
        await run(conn)

        result = await conn.execute(text("SELECT COUNT(*) FROM _migrations_history"))
        count = result.fetchone()[0]
        expected_count = len([f for f in MIGRATIONS_DIR.iterdir() if f.suffix == ".sql"])
        assert count == expected_count

    async def test_migrations_add_expected_columns(self, conn):
        from migrations.migration_runner import run
        await run(conn)

        result = await conn.execute(text("PRAGMA table_info('messages')"))
        columns = {row[1] for row in result.fetchall()}
        assert "parent_message_id" in columns
        assert "is_pinned" in columns
        assert "content_type" in columns
        assert "source_type" in columns
        assert "source_id" in columns
        assert "source_name" in columns
        assert "metadata_json" in columns

        result = await conn.execute(text("PRAGMA table_info('artifacts')"))
        columns = {row[1] for row in result.fetchall()}
        assert "version" in columns
        assert "parent_artifact_id" in columns

    async def test_fts_virtual_table_created(self, conn):
        from migrations.migration_runner import run
        await run(conn)

        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
        ))
        assert result.fetchone() is not None

    async def test_fts_triggers_created(self, conn):
        from migrations.migration_runner import run
        await run(conn)

        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))
        triggers = {row[0] for row in result.fetchall()}
        assert "messages_fts_insert" in triggers
        assert "messages_fts_delete" in triggers
        assert "messages_fts_update" in triggers

        result = await conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='messages_fts_update'"
        ))
        trigger_sql = result.scalar() or ""
        assert "AFTER UPDATE OF content" in trigger_sql
