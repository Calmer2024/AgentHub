"""Phase 4 real HTTP acceptance test.

Starts a uvicorn process with a temporary SQLite database and a local MockAgent,
then exercises the user-visible Phase 4 flow over http://127.0.0.1.
"""

from __future__ import annotations

import asyncio
import json
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


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
TMP = Path(tempfile.gettempdir())


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _write_mock_app() -> Path:
    path = TMP / f"agenthub_phase4_mock_{uuid.uuid4().hex}.py"
    path.write_text(textwrap.dedent("""
        from app.main import app
        from app.agents.base import BaseAgentAdapter, AgentCapability, AgentResponse
        from app.agents.registry import agent_registry

        class MockAgent(BaseAgentAdapter):
            @property
            def capability(self):
                return AgentCapability(name="mock", supports_streaming=True, max_context_tokens=100000)

            async def chat(self, messages, system_prompt, on_token=None, model=None, tools=None):
                return AgentResponse(content="Mock response")

            async def chat_stream(self, messages, system_prompt, model=None, tools=None):
                for token in ["Mock", " response"]:
                    yield token

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


async def _consume_sse(response: httpx.Response) -> list[dict]:
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


async def main() -> int:
    port = _free_port()
    db_path = TMP / f"agenthub_phase4_acceptance_{uuid.uuid4().hex}.db"
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
            single = await client.post(f"{base_url}/api/sessions", json={
                "title": "Phase4 real",
                "mode": "single",
                "agentConfigId": agent_id,
            })
            single.raise_for_status()
            sid = single.json()["id"]

            chat = await client.post(
                f"{base_url}/api/sessions/{sid}/chat",
                json={"content": "记录中文关键词：向量数据库"},
            )
            chat.raise_for_status()
            await _consume_sse(chat)

            messages = (await client.get(f"{base_url}/api/sessions/{sid}/messages")).json()
            user_msg = next(m for m in messages if m["role"] == "user")
            assistant_msg = next(m for m in messages if m["role"] == "assistant")

            reply = await client.post(
                f"{base_url}/api/messages/{assistant_msg['id']}/reply",
                json={"content": "引用回复"},
            )
            reply.raise_for_status()
            assert reply.json()["parentMessageId"] == assistant_msg["id"]

            pin = await client.post(f"{base_url}/api/messages/{user_msg['id']}/pin")
            pin.raise_for_status()
            refreshed = (await client.get(f"{base_url}/api/sessions/{sid}/messages")).json()
            assert next(m for m in refreshed if m["id"] == user_msg["id"])["isPinned"] is True

            search = await client.get(f"{base_url}/api/messages/search", params={
                "session_id": sid,
                "q": "向量数据库",
            })
            search.raise_for_status()
            assert search.json() and search.json()[0]["highlight"]

            regen = await client.post(f"{base_url}/api/messages/{assistant_msg['id']}/regenerate")
            regen.raise_for_status()
            assert any(e.get("done") for e in await _consume_sse(regen))

            unpin = await client.delete(f"{base_url}/api/messages/{user_msg['id']}/pin")
            unpin.raise_for_status()

            agent2 = await client.post(f"{base_url}/api/agents", json={
                "name": "Phase4 B",
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
            })
            agent2.raise_for_status()
            group = await client.post(f"{base_url}/api/sessions", json={
                "title": "Phase4 group",
                "mode": "group",
                "agentConfigIds": [agent_id, agent2.json()["id"]],
            })
            group.raise_for_status()
            group_chat = await client.post(
                f"{base_url}/api/sessions/{group.json()['id']}/chat",
                json={"content": "Hello group"},
            )
            group_chat.raise_for_status()
            types = [e.get("type") for e in await _consume_sse(group_chat)]
            assert "orchestrator.task_started" in types
            assert "orchestrator.task_completed" in types

        print("Phase 4 real acceptance passed")
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
