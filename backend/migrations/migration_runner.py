"""按编号顺序执行所有 .sql 迁移脚本，记录已执行的迁移。"""
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent


def _sorted_migration_files() -> list[Path]:
    files = [f for f in MIGRATIONS_DIR.iterdir() if f.suffix == ".sql"]
    files.sort(key=lambda f: f.name)
    return files


async def ensure_history_table(conn: AsyncConnection) -> None:
    await conn.execute(text(
        "CREATE TABLE IF NOT EXISTS _migrations_history ("
        "  filename VARCHAR PRIMARY KEY,"
        "  executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ")"
    ))
    await conn.commit()


async def run(conn: AsyncConnection) -> None:
    await ensure_history_table(conn)

    result = await conn.execute(text("SELECT filename FROM _migrations_history"))
    executed = {row[0] for row in result.fetchall()}

    for sql_file in _sorted_migration_files():
        if sql_file.name in executed:
            continue

        sql_content = sql_file.read_text(encoding="utf-8")
        statements = _split_statements(sql_content)

        logger.info("执行迁移: %s", sql_file.name)
        try:
            for stmt in statements:
                try:
                    await conn.execute(text(stmt))
                except Exception as stmt_exc:
                    if _is_already_exists_error(stmt_exc):
                        logger.info("迁移语句已存在（幂等跳过）: %s", sql_file.name)
                        await conn.rollback()
                        continue
                    raise
            await conn.execute(
                text("INSERT INTO _migrations_history (filename) VALUES (:name)"),
                {"name": sql_file.name},
            )
            await conn.commit()
            logger.info("迁移完成: %s", sql_file.name)
        except Exception as e:
            logger.exception("迁移失败: %s", sql_file.name)
            await conn.rollback()
            raise


def _is_already_exists_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(kw in msg for kw in [
        "duplicate column name",
        "already exists",
        "duplicate column",
    ])


def _split_statements(sql: str) -> list[str]:
    """按分号拆分 SQL 语句，正确处理 BEGIN...END 块内的分号。"""
    statements = []
    depth = 0
    start = 0
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch in ('\r', '\n', ' ', '\t'):
            i += 1
            continue
        if ch == ';' and depth == 0:
            stmt = sql[start:i].strip()
            if stmt and not stmt.startswith("--"):
                statements.append(stmt)
            start = i + 1
        elif _match_keyword(sql, i, "BEGIN"):
            depth += 1
            i += 4
        elif _match_keyword(sql, i, "END") and depth > 0:
            depth -= 1
            i += 2
        i += 1
    # 最后一个语句
    trailing = sql[start:].strip()
    if trailing and not trailing.startswith("--"):
        statements.append(trailing)
    return statements


def _match_keyword(sql: str, pos: int, keyword: str) -> bool:
    """检查 sql[pos:pos+len] 是否等于 keyword 且为完整单词（前后非字母）。"""
    end = pos + len(keyword)
    if sql[pos:end].upper() != keyword.upper():
        return False
    before_ok = pos == 0 or not sql[pos - 1].isalpha()
    after_ok = end >= len(sql) or not sql[end].isalpha()
    return before_ok and after_ok
