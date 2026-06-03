"""Phase 5 real HTTP acceptance test.

Starts uvicorn with a temporary SQLite database and exercises artifact
versioning, diff, and edit confirmation over the public REST API.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
TMP = Path(tempfile.gettempdir())


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _write_mock_app() -> Path:
    path = TMP / f"agenthub_phase5_mock_{uuid.uuid4().hex}.py"
    path.write_text(textwrap.dedent("""
        from app.main import app
        from app.agents.base import BaseAgentAdapter, AgentCapability, AgentResponse
        from app.agents.registry import agent_registry

        class MockAgent(BaseAgentAdapter):
            @property
            def capability(self):
                return AgentCapability(name="mock", supports_streaming=True, supports_tool_call=False)

            async def chat(self, messages, system_prompt, on_token=None, model=None, tools=None):
                return AgentResponse(content="return 'phase5 edited'")

            async def chat_stream(self, messages, system_prompt, model=None, tools=None):
                yield "Mock"

        mock = MockAgent()
        for provider in list(agent_registry._adapters):
            agent_registry._adapters[provider] = mock
    """), encoding="utf-8")
    return path


async def _wait_ready(client: httpx.AsyncClient, base_url: str) -> None:
    for _ in range(80):
        try:
            res = await client.get(f"{base_url}/")
            if res.status_code == 200:
                return
        except httpx.HTTPError:
            await asyncio.sleep(0.1)
    raise RuntimeError("server did not become ready")


def _seed_artifact(db_path: Path, session_id: str, agent_id: str) -> str:
    engine = create_engine(f"sqlite:///{db_path}")
    message_id = str(uuid.uuid4())
    artifact_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO messages (
                id, session_id, role, content, content_type, agent_name,
                source_type, source_id, source_name, is_pinned, created_at
            )
            VALUES (
                :id, :session_id, 'assistant', '生成了代码产物', 'text', 'Phase5 Agent',
                'agent', :agent_id, 'Phase5 Agent', '0', CURRENT_TIMESTAMP
            )
        """), {"id": message_id, "session_id": session_id, "agent_id": agent_id})
        conn.execute(text("""
            INSERT INTO artifacts (
                id, session_id, message_id, type, title, content, status,
                version, parent_artifact_id, created_at
            )
            VALUES (
                :id, :session_id, :message_id, 'code_diff', 'phase5.py',
                :content, 'ready', 1, NULL, CURRENT_TIMESTAMP
            )
        """), {
            "id": artifact_id,
            "session_id": session_id,
            "message_id": message_id,
            "content": "def phase5():\n    return 'original'\n",
        })
    return artifact_id


async def main() -> int:
    port = _free_port()
    db_path = TMP / f"agenthub_phase5_acceptance_{uuid.uuid4().hex}.db"
    app_module = _write_mock_app()
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": f"{BACKEND};{TMP}",
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        "DEEPSEEK_API_KEY": "sk-test-dummy-key-12345678",
        "OPENAI_API_KEY": "sk-test-dummy-key-12345678",
        "ANTHROPIC_API_KEY": "sk-ant-test-dummy-key-12345678",
        "GEMINI_API_KEY": "AIza-test-dummy-key-12345-abcd",
        "MINIMAX_API_KEY": "test-dummy-minimax-key-1234567890",
        "GLM_API_KEY": "test-dummy-glm-key-1234567890",
    })

    proc = subprocess.Popen(
        [str(BACKEND / "venv" / "Scripts" / "python.exe"), "-m", "uvicorn",
         f"{app_module.stem}:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(BACKEND),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            await _wait_ready(client, base_url)

            agents = (await client.get(f"{base_url}/api/agents")).json()
            agent_id = agents[0]["id"]
            session = await client.post(f"{base_url}/api/sessions", json={
                "title": "Phase5 real",
                "mode": "single",
                "agentConfigId": agent_id,
            })
            session.raise_for_status()
            session_id = session.json()["id"]
            artifact_id = _seed_artifact(db_path, session_id, agent_id)

            artifacts = await client.get(f"{base_url}/api/sessions/{session_id}/artifacts")
            artifacts.raise_for_status()
            assert artifacts.json()[0]["id"] == artifact_id
            assert artifacts.json()[0]["version"] == 1

            preview = await client.post(f"{base_url}/api/artifacts/{artifact_id}/edit", json={
                "selection": "return 'original'",
                "instruction": "改为 phase5 edited",
            })
            preview.raise_for_status()
            preview_data = preview.json()
            assert preview_data["newVersion"] is None
            assert "phase5 edited" in preview_data["proposedContent"]

            still_v1 = await client.get(f"{base_url}/api/artifacts/{artifact_id}/versions")
            still_v1.raise_for_status()
            assert [v["version"] for v in still_v1.json()] == [1]

            apply = await client.post(f"{base_url}/api/artifacts/{artifact_id}/edit", json={
                "selection": "return 'original'",
                "instruction": "确认应用",
                "apply": True,
                "proposedContent": preview_data["proposedContent"],
            })
            apply.raise_for_status()
            applied = apply.json()
            new_artifact_id = applied["artifact"]["id"]
            assert applied["newVersion"] == 2
            assert applied["artifact"]["parentArtifactId"] == artifact_id

            versions = await client.get(f"{base_url}/api/artifacts/{new_artifact_id}/versions")
            versions.raise_for_status()
            assert [v["version"] for v in versions.json()] == [1, 2]

            diff = await client.get(
                f"{base_url}/api/artifacts/{new_artifact_id}/diff",
                params={"v1": 1, "v2": 2},
            )
            diff.raise_for_status()
            assert "-    return 'original'" in diff.json()["diff"]
            assert "+    return 'phase5 edited'" in diff.json()["diff"]

            heads = await client.get(f"{base_url}/api/sessions/{session_id}/artifacts")
            heads.raise_for_status()
            assert [a["id"] for a in heads.json()] == [new_artifact_id]

        print("Phase 5 real acceptance passed")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        app_module.unlink(missing_ok=True)
        for suffix in ("", "-wal", "-shm"):
            _unlink_later(Path(str(db_path) + suffix))
        if proc.returncode not in (0, None):
            err = proc.stderr.read() if proc.stderr else ""
            if err:
                print(err, file=sys.stderr)


def _unlink_later(path: Path) -> None:
    for _ in range(5):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
