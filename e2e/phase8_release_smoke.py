"""Phase 8 release-candidate API smoke.

Requires backend on http://127.0.0.1:8000. The default path uses a local
Python fixture CLI. Set AGENTHUB_PHASE8_REAL_CLI=1 to also run a configured
Claude Code agent against a temporary project workspace.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from urllib.error import HTTPError


BASE = os.environ.get("AGENTHUB_API_BASE", "http://127.0.0.1:8000/api").rstrip("/")


def request_json(path: str, payload: dict | None = None, method: str | None = None, timeout: int = 60):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method or ("POST" if payload is not None else "GET"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method or 'GET'} {path} failed: HTTP {exc.code} {detail}") from exc


def request_bytes(path: str, timeout: int = 60) -> bytes:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as resp:
        return resp.read()


def write_project_file(project_id: str, path: str, content: str) -> None:
    request_json(
        f"/projects/{project_id}/files",
        {"path": path, "content": content},
        method="PUT",
    )


def delete(path: str) -> None:
    req = urllib.request.Request(f"{BASE}{path}", method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
    except Exception:
        pass


def create_fixture_cli() -> Path:
    script = Path(__file__).resolve().parent / ".phase8_fixture_cli.py"
    script.write_text(
        "import os, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "sys.stdout.write('phase8 fixture cli received: ' + data[:80])\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )
    return script


def create_fixture_agent() -> str:
    script = create_fixture_cli()
    agent = request_json("/agents", {
        "name": f"Phase8 Fixture CLI {int(time.time())}",
        "description": "Phase 8 release smoke fixture",
        "systemPrompt": "你是 Phase 8 验收用本地 CLI Agent。",
        "rules": "",
        "agentType": "cli_wrapper",
        "cliTool": "custom",
        "executable": sys.executable,
        "initArgs": [str(script)],
        "envVars": {},
        "toolset": ["workspace_editing"],
        "contextPolicy": "workspace_coding",
        "avatar": "preset:blue",
    }, timeout=30)
    return str(agent["id"])


def run_build_preview_export(project: dict) -> str:
    project_id = str(project["id"])
    write_project_file(
        project_id,
        "build_phase8.py",
        "from pathlib import Path\n"
        "Path('dist').mkdir(exist_ok=True)\n"
        "Path('dist/index.html').write_text('<!doctype html><main>Phase8 RC</main>', encoding='utf-8')\n"
        "print('phase8 rc build ready')\n",
    )
    write_project_file(project_id, "src/input.txt", "phase8 source")
    build = request_json(
        f"/projects/{project_id}/builds",
        {
            "command": f'"{sys.executable}" build_phase8.py',
            "artifactPath": "dist",
        },
        timeout=120,
    )
    assert build["status"] == "succeeded", build
    build_id = str(build["buildId"])

    logs = request_json(f"/projects/{project_id}/builds/{build_id}/logs")
    assert any("phase8 rc build ready" in item["text"] for item in logs["chunks"]), logs

    preview = request_json(
        f"/projects/{project_id}/previews",
        {"source": "build", "buildId": build_id, "path": "index.html"},
    )
    with urllib.request.urlopen(f"http://127.0.0.1:8000{preview['url']}", timeout=30) as resp:
        assert "Phase8 RC" in resp.read().decode("utf-8")

    source_zip = request_bytes(f"/projects/{project_id}/exports/source")
    with zipfile.ZipFile(io.BytesIO(source_zip)) as archive:
        assert any(name.endswith("src/input.txt") for name in archive.namelist())

    build_zip = request_bytes(f"/projects/{project_id}/exports/builds/{build_id}")
    with zipfile.ZipFile(io.BytesIO(build_zip)) as archive:
        assert any(name.endswith("index.html") for name in archive.namelist())
    return build_id


def run_context_and_orchestrator(project: dict, agent_id: str) -> None:
    session = request_json("/sessions", {
        "title": f"Phase8 RC {int(time.time())}",
        "mode": "single",
        "projectId": project["id"],
        "agentConfigId": agent_id,
    })
    session_id = str(session["id"])

    context = request_json(
        f"/sessions/{urllib.parse.quote(session_id)}/context-pack?purpose=send",
        method="GET",
    )
    assert context["sessionId"] == session_id
    assert any(block["type"] == "messages" for block in context["blocks"])

    plan_id = f"phase8_rc_{int(time.time())}"
    execution = request_json("/orchestrator/plans/execute", {
        "sessionId": session_id,
        "normalizedPlan": {
            "plan_id": plan_id,
            "status": "draft",
            "tasks": [{
                "task_id": "T1",
                "title": "Phase 8 resume smoke",
                "goal": "验证调度计划恢复契约",
                "required_skills": ["workspace_editing"],
                "assigned_agent_id": agent_id,
                "assigned_agent_name": "Phase8 Fixture CLI",
                "depends_on": [],
                "expected_outputs": ["resume"],
                "acceptance_criteria": ["resume endpoint returns running"],
                "needs_approval": True,
            }],
        },
    })
    resumed = request_json(
        f"/orchestrator/plans/{urllib.parse.quote(plan_id)}/resume",
        {"approvalId": "phase8-smoke", "message": "继续"},
    )
    assert resumed["status"] == "running", resumed
    assert resumed["currentStepId"] == "T1", resumed

    execution_id = execution["executionId"]
    for _ in range(40):
        current = request_json(f"/orchestrator/executions/{urllib.parse.quote(execution_id)}")
        if current["status"] in {"completed", "failed", "cancelled"}:
            return
        time.sleep(0.1)


def run_real_claude_if_requested(project: dict) -> None:
    if os.environ.get("AGENTHUB_PHASE8_REAL_CLI") != "1":
        print("real Claude Code demo skipped; set AGENTHUB_PHASE8_REAL_CLI=1 to enable")
        return
    agents = request_json("/agents")
    claude = next(
        (
            agent for agent in agents
            if agent.get("cliTool") == "claude_code" and agent.get("isActive") is True
        ),
        None,
    )
    if not claude:
        raise RuntimeError("AGENTHUB_PHASE8_REAL_CLI=1 but no active claude_code agent was found")
    session = request_json("/sessions", {
        "title": f"Phase8 Claude Demo {int(time.time())}",
        "mode": "single",
        "projectId": project["id"],
        "agentConfigId": claude["id"],
    })
    events = read_sse(
        f"/sessions/{session['id']}/chat",
        {"content": "请在当前 workspace 创建 phase8-claude-demo.txt，内容为 phase8 claude ok。"},
    )
    assert events, "Claude Code SSE stream produced no events"
    file_data = request_json(
        f"/projects/{project['id']}/files?path=phase8-claude-demo.txt",
        method="GET",
    )
    assert "phase8 claude ok" in file_data["content"]


def read_sse(path: str, payload: dict, timeout: int = 300) -> list[dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    events: list[dict] = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            events.append(event)
            if event.get("done") is True and not event.get("agentId"):
                break
    return events


def main() -> int:
    project = request_json("/projects", {"name": f"phase8-rc-{int(time.time())}"})
    agent_id = create_fixture_agent()
    try:
        build_id = run_build_preview_export(project)
        run_context_and_orchestrator(project, agent_id)
        run_real_claude_if_requested(project)
        print(f"phase8 release smoke passed: project={project['id']} build={build_id}")
        return 0
    finally:
        delete(f"/agents/{urllib.parse.quote(agent_id)}")
        delete(f"/projects/{urllib.parse.quote(str(project['id']))}?deleteFiles=true")


if __name__ == "__main__":
    sys.exit(main())
