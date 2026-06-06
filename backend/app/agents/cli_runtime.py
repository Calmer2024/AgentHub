"""CLI 进程运行时：只负责真实进程 I/O 与生命周期。"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from ..core.agent_env import clean_cli_agent_env
from ..event_bus.event_types import EventType
from .cli_stream import PromptInterceptor, StreamSanitizer


class CliExecutableNotFound(FileNotFoundError):
    pass


class CliSubprocessNotSupported(RuntimeError):
    pass


class CliProcessNotFound(LookupError):
    pass


@dataclass
class ManagedCliProcess:
    process_id: str
    session_id: str
    agent_id: str
    executable: str
    cwd: str
    process: asyncio.subprocess.Process
    waiting_prompt: str | None = None

    def snapshot(self) -> dict:
        return {
            "processId": self.process_id,
            "sessionId": self.session_id,
            "agentId": self.agent_id,
            "executable": self.executable,
            "cwd": self.cwd,
            "pid": self.process.pid,
            "waitingPrompt": self.waiting_prompt,
            "returnCode": self.process.returncode,
        }


@dataclass
class ProcessChunk:
    process_id: str
    text: str = ""
    stream: str = "stdout"
    event_type: str = "chunk"
    exit_code: int | None = None
    error: str | None = None
    command: list[str] | None = None
    cwd: str | None = None
    pid: int | None = None


class CliProcessManager:
    """Spawn, stream, reply to, and terminate CLI processes."""

    def __init__(self):
        self._processes: dict[str, ManagedCliProcess] = {}
        self._session_processes: dict[str, set[str]] = {}

    def active_snapshots(self, session_id: str | None = None) -> list[dict]:
        if session_id is None:
            return [p.snapshot() for p in self._processes.values()]
        ids = self._session_processes.get(session_id, set())
        return [self._processes[pid].snapshot() for pid in ids if pid in self._processes]

    async def stream(
        self,
        *,
        session_id: str,
        agent_id: str,
        executable: str,
        args: list[str],
        env_vars: dict[str, str],
        cwd: str,
        prompt: str,
        close_stdin_after_prompt: bool = False,
        stdin_mode: str = "pipe",
        event_bus=None,
        silence_timeout_seconds: float = 300,
    ) -> AsyncIterator[ProcessChunk]:
        workspace = Path(cwd)
        if not workspace.exists() or not workspace.is_dir():
            yield ProcessChunk("", event_type="error", error="workspace not found")
            return

        process_id = f"cli_{uuid.uuid4().hex}"
        env = self._build_env(env_vars)
        env.setdefault("NO_COLOR", "1")
        env.setdefault("TERM", "dumb")
        command = resolve_cli_command(executable, args)

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(workspace),
                env=env,
                stdin=_resolve_stdin(stdin_mode),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except NotImplementedError as exc:
            raise CliSubprocessNotSupported(_subprocess_not_supported_message()) from exc
        except FileNotFoundError as exc:
            raise CliExecutableNotFound(executable) from exc

        handle = ManagedCliProcess(
            process_id=process_id,
            session_id=session_id,
            agent_id=agent_id,
            executable=executable,
            cwd=str(workspace),
            process=process,
        )
        self._processes[process_id] = handle
        self._session_processes.setdefault(session_id, set()).add(process_id)

        await self._publish(event_bus, EventType.AGENT_PROCESS_STARTED, {
            "sessionId": session_id,
            "agentId": agent_id,
            "processId": process_id,
            "pid": process.pid,
            "executable": command[0],
            "argv": command,
            "cwd": str(workspace),
        })
        yield ProcessChunk(
            process_id,
            event_type="started",
            command=command,
            cwd=str(workspace),
            pid=process.pid,
        )

        try:
            if process.stdin and prompt:
                process.stdin.write(prompt.encode("utf-8", errors="replace"))
                await process.stdin.drain()
            if process.stdin:
                if close_stdin_after_prompt:
                    process.stdin.close()

            async for chunk in self._read_until_exit(
                handle, silence_timeout_seconds, event_bus,
            ):
                yield chunk
        finally:
            exit_code = process.returncode
            if exit_code is None:
                try:
                    exit_code = await asyncio.wait_for(process.wait(), timeout=2)
                except TimeoutError:
                    await self.terminate(process_id)
                    exit_code = process.returncode
            self._processes.pop(process_id, None)
            self._session_processes.get(session_id, set()).discard(process_id)
            if not self._session_processes.get(session_id):
                self._session_processes.pop(session_id, None)
            await self._publish(event_bus, EventType.AGENT_PROCESS_COMPLETED, {
                "sessionId": session_id,
                "agentId": agent_id,
                "processId": process_id,
                "exitCode": exit_code,
            })
            yield ProcessChunk(process_id, event_type="completed", exit_code=exit_code)

    async def reply(self, process_id: str, reply: str) -> None:
        handle = self._processes.get(process_id)
        if not handle or handle.process.returncode is not None or not handle.process.stdin:
            raise CliProcessNotFound(process_id)
        if reply not in {"y", "n"}:
            raise ValueError("reply must be 'y' or 'n'")
        handle.process.stdin.write(f"{reply}\n".encode("utf-8"))
        await handle.process.stdin.drain()
        handle.waiting_prompt = None

    async def terminate(self, process_id: str) -> None:
        handle = self._processes.get(process_id)
        if not handle or handle.process.returncode is not None:
            return
        if os.name == "nt":
            handle.process.terminate()
        else:
            handle.process.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(handle.process.wait(), timeout=5)
        except TimeoutError:
            handle.process.kill()
            await handle.process.wait()

    async def terminate_session(self, session_id: str) -> int:
        process_ids = list(self._session_processes.get(session_id, set()))
        for process_id in process_ids:
            await self.terminate(process_id)
        return len(process_ids)

    async def _read_until_exit(
        self,
        handle: ManagedCliProcess,
        silence_timeout_seconds: float,
        event_bus,
    ) -> AsyncIterator[ProcessChunk]:
        queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()
        pumps = [
            asyncio.create_task(self._pump(handle.process.stdout, "stdout", queue)),
            asyncio.create_task(self._pump(handle.process.stderr, "stderr", queue)),
        ]
        closed: set[str] = set()

        try:
            while len(closed) < 2:
                try:
                    stream, text = await asyncio.wait_for(
                        queue.get(), timeout=silence_timeout_seconds,
                    )
                except TimeoutError:
                    await self._publish(event_bus, EventType.AGENT_PROCESS_TIMEOUT, {
                        "sessionId": handle.session_id,
                        "agentId": handle.agent_id,
                        "processId": handle.process_id,
                        "reason": "silence",
                    })
                    await self.terminate(handle.process_id)
                    yield ProcessChunk(
                        handle.process_id,
                        event_type="timeout",
                        error="CLI 进程已超时（长时间无响应）",
                    )
                    return
                if text is None:
                    closed.add(stream)
                    continue
                yield ProcessChunk(handle.process_id, text=text, stream=stream)
        finally:
            for task in pumps:
                task.cancel()

    @staticmethod
    async def _pump(reader, name: str, queue: asyncio.Queue) -> None:
        if reader is None:
            await queue.put((name, None))
            return
        while True:
            data = await reader.read(1024)
            if not data:
                break
            await queue.put((name, data.decode("utf-8", errors="replace")))
        await queue.put((name, None))

    @staticmethod
    async def _publish(event_bus, event_type: EventType, payload: dict) -> None:
        if not event_bus:
            return
        try:
            await event_bus.publish(event_type, payload)
        except Exception:
            pass

    @staticmethod
    def _build_env(env_vars: dict[str, str]) -> dict[str, str]:
        env = os.environ.copy()
        for key, value in clean_cli_agent_env(env_vars).items():
            if value:
                env[str(key)] = str(value)
        return env


cli_process_manager = CliProcessManager()


def _subprocess_not_supported_message() -> str:
    if os.name == "nt":
        return (
            "当前 Python asyncio 事件循环不支持启动 CLI 子进程。"
            "Windows 下请使用支持 subprocess 的 Proactor 事件循环启动后端，"
            "并避免 uvicorn --reload/Selector loop 启动方式。"
        )
    return "当前 Python asyncio 事件循环不支持启动 CLI 子进程。"


def resolve_cli_command(executable: str, args: list[str]) -> list[str]:
    resolved = shutil.which(executable) or executable
    suffix = Path(resolved).suffix.lower()
    if os.name == "nt" and suffix in {".cmd", ".bat"}:
        return ["cmd.exe", "/d", "/c", resolved, *args]
    if os.name == "nt" and suffix == ".ps1":
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            resolved,
            *args,
        ]
    return [resolved, *args]


def _resolve_stdin(stdin_mode: str):
    if stdin_mode == "inherit":
        return None
    return asyncio.subprocess.PIPE
