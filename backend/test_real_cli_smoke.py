"""Real local CLI smoke checks for Phase 6 CLI adapters.

This script intentionally talks to the user's installed CLI tools. It is not a
unit test.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from app.agents.cli_defaults import DEFAULT_CLI_AGENTS
from app.agents.cli_adapters import OpenCodeAdapter
from app.agents.cli_runtime import CliProcessManager
from app.agents.cli_runtime import resolve_cli_command
from app.models import AgentConfig


async def main() -> int:
    results = []
    results.append(await smoke_claude())
    results.append(await smoke_codex())
    results.append(await smoke_opencode())
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in results) else 1


async def smoke_claude() -> dict:
    executable = shutil.which("claude")
    if not executable:
        return {"name": "claude", "ok": False, "error": "not found"}
    workspace = Path(tempfile.mkdtemp(prefix="agenthub-claude-"))
    prompt = (
        "Create a file named claude-smoke.txt containing exactly "
        "AGENTHUB_CLAUDE_WORKSPACE"
    )
    result = await run_cli(
        executable="claude",
        args=DEFAULT_CLI_AGENTS["claude_code"]["init_args"],
        cwd=workspace,
        prompt=prompt + "\n",
        close_stdin=True,
        timeout=180,
    )
    file_path = workspace / "claude-smoke.txt"
    content = file_path.read_text(encoding="utf-8", errors="replace").strip() if file_path.exists() else ""
    result.update({
        "name": "claude",
        "version": await version("claude", "--version"),
        "workspace": str(workspace),
        "fileContent": content,
        "ok": result["exitCode"] == 0 and content == "AGENTHUB_CLAUDE_WORKSPACE",
    })
    return result


async def smoke_codex() -> dict:
    executable = shutil.which("codex")
    if not executable:
        return {"name": "codex", "ok": False, "error": "not found"}
    workspace = Path(tempfile.mkdtemp(prefix="agenthub-codex-"))
    prompt = (
        "Create a file named codex-smoke.txt containing exactly "
        "AGENTHUB_CODEX_WORKSPACE"
    )
    result = await run_cli(
        executable="codex",
        args=DEFAULT_CLI_AGENTS["codex"]["init_args"],
        cwd=workspace,
        prompt=prompt + "\n",
        close_stdin=True,
        timeout=180,
    )
    file_path = workspace / "codex-smoke.txt"
    content = file_path.read_text(encoding="utf-8", errors="replace").strip() if file_path.exists() else ""
    result.update({
        "name": "codex",
        "version": await version("codex", "--version"),
        "workspace": str(workspace),
        "fileContent": content,
        "ok": result["exitCode"] == 0 and content == "AGENTHUB_CODEX_WORKSPACE",
    })
    return result


async def smoke_opencode() -> dict:
    executable = shutil.which("opencode")
    if not executable:
        return {"name": "opencode", "ok": False, "error": "not found"}
    workspace_root = Path(__file__).parent / "data" / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="agenthub-opencode-", dir=workspace_root))
    agent = AgentConfig(
        id="opencode-real-smoke",
        name="OpenCode",
        description="",
        system_prompt="",
        agent_type="cli_wrapper",
        cli_tool="opencode",
        executable="opencode",
        init_args=json.dumps(DEFAULT_CLI_AGENTS["opencode"]["init_args"]),
        env_vars="{}",
    )
    adapter = OpenCodeAdapter()
    text = ""
    exit_code = None
    try:
        async with asyncio.timeout(180):
            async for event in adapter.stream(
                agent=agent,
                session_id="real-smoke-opencode",
                cwd=str(workspace),
                user_prompt="Print exactly AGENTHUB_OPENCODE_WORKSPACE and stop.",
            ):
                if event.type == "agent.output":
                    text += event.chunk
                if event.type == "agent.process.completed":
                    exit_code = event.exit_code
                if event.type == "error":
                    return {
                        "name": "opencode",
                        "version": await version("opencode", "--version"),
                        "workspace": str(workspace),
                        "exitCode": exit_code,
                        "outputPreview": text[-2000:],
                        "ok": False,
                        "error": event.error,
                    }
    except TimeoutError:
        return {
            "name": "opencode",
            "version": await version("opencode", "--version"),
            "workspace": str(workspace),
            "exitCode": exit_code,
            "outputPreview": text[-2000:],
            "ok": False,
            "error": "timeout",
        }
    return {
        "name": "opencode",
        "version": await version("opencode", "--version"),
        "workspace": str(workspace),
        "exitCode": exit_code,
        "outputPreview": text[-2000:],
        "ok": exit_code == 0 and "AGENTHUB_OPENCODE_WORKSPACE" in text,
    }


async def run_cli(
    *,
    executable: str,
    args: list[str],
    cwd: Path,
    prompt: str,
    close_stdin: bool,
    timeout: int,
) -> dict:
    manager = CliProcessManager()
    text = ""
    exit_code = None
    try:
        async with asyncio.timeout(timeout):
            async for chunk in manager.stream(
                session_id="real-smoke",
                agent_id=executable,
                executable=executable,
                args=args,
                env_vars={},
                cwd=str(cwd),
                prompt=prompt,
                close_stdin_after_prompt=close_stdin,
                silence_timeout_seconds=timeout,
            ):
                if chunk.text:
                    text += chunk.text
                if chunk.event_type == "completed":
                    exit_code = chunk.exit_code
    except TimeoutError:
        return {"exitCode": None, "outputPreview": text[-2000:], "error": "timeout"}
    return {"exitCode": exit_code, "outputPreview": text[-2000:]}


async def version(executable: str, arg: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *resolve_cli_command(executable, [arg]),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return (out or err).decode("utf-8", errors="replace").strip().splitlines()[0]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
