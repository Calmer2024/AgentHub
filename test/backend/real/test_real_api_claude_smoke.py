"""Real API-path Claude smoke for Phase 6.

Creates a temporary Project + Session + AgentConfig in the real app database,
then sends a chat through ChatServiceImpl using the installed local CLI.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import delete

from app.agents.cli_defaults import DEFAULT_CLI_AGENTS
from app.database import AsyncSessionLocal, Base, engine
from app.models import AgentConfig, Message, Project, Session
from app.services.chat_service_impl import ChatServiceImpl


async def main() -> int:
    if not shutil.which("claude"):
        print(json.dumps({"ok": False, "error": "claude not found"}, ensure_ascii=False))
        return 1

    workspace = Path(tempfile.mkdtemp(prefix="agenthub-api-claude-"))
    project_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    prompt = (
        "Create a file named api-claude-smoke.txt containing exactly "
        "AGENTHUB_API_CLAUDE_WORKSPACE"
    )

    await prepare_database()

    try:
        async with AsyncSessionLocal() as db:
            db.add(Project(
                id=project_id,
                name="real-api-claude-smoke",
                workspace_path=str(workspace),
                status="ready",
            ))
            db.add(AgentConfig(
                id=agent_id,
                name="Claude Code Real Smoke",
                description="Real Claude Code smoke",
                system_prompt="",
                agent_type="cli_wrapper",
                cli_tool="claude_code",
                executable="claude",
                init_args=json.dumps(DEFAULT_CLI_AGENTS["claude_code"]["init_args"]),
                env_vars="{}",
            ))
            db.add(Session(
                id=session_id,
                title="real-api-smoke",
                project_id=project_id,
                agent_config_id=agent_id,
                mode="single",
            ))
            await db.commit()

            events = []
            async for event in ChatServiceImpl(db).send_message_stream(session_id, prompt):
                events.append(event)

        target = workspace / "api-claude-smoke.txt"
        content = target.read_text(encoding="utf-8", errors="replace").strip() if target.exists() else ""
        result = {
            "ok": content == "AGENTHUB_API_CLAUDE_WORKSPACE",
            "workspace": str(workspace),
            "fileContent": content,
            "eventCount": len(events),
            "lastEvent": events[-1].strip() if events else "",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    finally:
        await cleanup_smoke_rows(session_id, project_id, agent_id)
        shutil.rmtree(workspace, ignore_errors=True)


async def prepare_database() -> None:
    async with engine.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
        from migrations.migration_runner import run as run_migrations
        await run_migrations(conn)


async def cleanup_smoke_rows(session_id: str, project_id: str, agent_id: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Message).where(Message.session_id == session_id))
        await db.execute(delete(Session).where(Session.id == session_id))
        await db.execute(delete(Project).where(Project.id == project_id))
        await db.execute(delete(AgentConfig).where(AgentConfig.id == agent_id))
        await db.commit()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
