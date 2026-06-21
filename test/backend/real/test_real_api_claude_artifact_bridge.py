"""Real API-path Claude Code artifact bridge acceptance.

This is an opt-in smoke script. It uses the user's installed Claude Code CLI
through AgentHub's real ChatService path, then asserts that Phase 6F creates
artifacts from workspace writes before the final done event.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete

from app.agents.cli_defaults import DEFAULT_CLI_AGENTS
from app.database import AsyncSessionLocal, Base, engine
from app.models import AgentConfig, Artifact, Message, Project, Session
from app.services.artifact_service import ArtifactService
from app.services.chat_service_impl import ChatServiceImpl


async def main() -> int:
    if not shutil.which("claude"):
        print(json.dumps({"ok": False, "error": "claude not found"}, ensure_ascii=False))
        return 1

    workspace = Path(tempfile.mkdtemp(prefix="agenthub-api-claude-artifact-"))
    project_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    await prepare_database()

    try:
        async with AsyncSessionLocal() as db:
            db.add(Project(
                id=project_id,
                name="real-api-claude-artifact-bridge",
                workspace_path=str(workspace),
                status="ready",
            ))
            db.add(AgentConfig(
                id=agent_id,
                name="Claude Code Artifact Bridge Smoke",
                description="Real Claude Code artifact bridge smoke",
                system_prompt=(
                    "You are running in an automated acceptance test. "
                    "Follow the user's file creation instructions exactly. "
                    "Do not ask questions."
                ),
                agent_type="cli_wrapper",
                cli_tool="claude_code",
                executable="claude",
                init_args=json.dumps(DEFAULT_CLI_AGENTS["claude_code"]["init_args"]),
                env_vars="{}",
            ))
            db.add(Session(
                id=session_id,
                title="real-api-claude-artifact-bridge",
                project_id=project_id,
                agent_config_id=agent_id,
                mode="single",
            ))
            await db.commit()

            prompt = (
                "In the current workspace, create exactly these three files and then stop:\n"
                "1. index.html containing a complete HTML document with "
                "AGENTHUB_ARTIFACT_BRIDGE_HTML inside a <main> element.\n"
                "2. package.json containing a minimal JSON object with scripts.dev set to vite.\n"
                "3. src/App.tsx containing a default exported React component that renders "
                "AGENTHUB_ARTIFACT_BRIDGE_APP.\n"
                "Do not create extra source files unless needed for directories."
            )

            events = []
            async for event in ChatServiceImpl(db).send_message_stream(session_id, prompt):
                events.extend(_sse_payloads(event))

            artifacts = await ArtifactService(db).list_current_artifacts(session_id)

        result = build_result(
            workspace=workspace,
            project_id=project_id,
            session_id=session_id,
            events=events,
            artifacts=artifacts,
        )
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
        await db.execute(delete(Artifact).where(Artifact.session_id == session_id))
        await db.execute(delete(Message).where(Message.session_id == session_id))
        await db.execute(delete(Session).where(Session.id == session_id))
        await db.execute(delete(Project).where(Project.id == project_id))
        await db.execute(delete(AgentConfig).where(AgentConfig.id == agent_id))
        await db.commit()


def build_result(
    *,
    workspace: Path,
    project_id: str,
    session_id: str,
    events: list[dict[str, Any]],
    artifacts: list[Artifact],
) -> dict[str, Any]:
    event_types = [
        str(event.get("type") or ("done" if event.get("done") else "token"))
        for event in events
    ]
    done_index = len(event_types) - 1 if event_types else -1
    artifact_created_indexes = [
        index for index, event_type in enumerate(event_types)
        if event_type == "artifact.created"
    ]
    by_type = {artifact.type: artifact for artifact in artifacts}
    html = workspace / "index.html"
    package_json = workspace / "package.json"
    app = workspace / "src" / "App.tsx"
    web_preview = by_type.get("web_preview")
    file_tree = by_type.get("file_tree")
    code_diff = by_type.get("code_diff")

    checks = {
        "workspace_html_written": html.exists()
        and "AGENTHUB_ARTIFACT_BRIDGE_HTML" in html.read_text(encoding="utf-8", errors="replace"),
        "workspace_package_written": package_json.exists(),
        "workspace_app_written": app.exists()
        and "AGENTHUB_ARTIFACT_BRIDGE_APP" in app.read_text(encoding="utf-8", errors="replace"),
        "scan_started": "artifact.scan.started" in event_types,
        "artifact_created_before_done": bool(artifact_created_indexes)
        and done_index >= 0
        and max(artifact_created_indexes) < done_index,
        "scan_completed_before_done": "artifact.scan.completed" in event_types
        and event_types.index("artifact.scan.completed") < done_index,
        "web_preview_artifact": bool(web_preview)
        and web_preview.project_id == project_id
        and web_preview.session_id == session_id
        and web_preview.file_path == "index.html"
        and "AGENTHUB_ARTIFACT_BRIDGE_HTML" in web_preview.content,
        "file_tree_artifact": bool(file_tree)
        and "package.json" in file_tree.content
        and "src/App.tsx" in file_tree.content,
        "code_diff_artifact": bool(code_diff)
        and "--- a/index.html" in code_diff.content
        and "--- a/src/App.tsx" in code_diff.content,
    }
    return {
        "ok": all(checks.values()),
        "workspace": str(workspace),
        "eventTypes": event_types,
        "artifactSummary": [
            {
                "id": artifact.id,
                "type": artifact.type,
                "title": artifact.title,
                "messageId": artifact.message_id,
                "projectId": artifact.project_id,
                "filePath": artifact.file_path,
                "source": artifact.source,
                "version": artifact.version,
            }
            for artifact in artifacts
        ],
        "checks": checks,
    }


def _sse_payloads(raw_event: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for line in raw_event.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            payloads.append(json.loads(line[6:]))
        except json.JSONDecodeError:
            payloads.append({"type": "invalid_json", "raw": line[6:]})
    return payloads


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
