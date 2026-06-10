"""会话级 CLI 进程运行时。

本模块只负责“一会话一常驻进程”的生命周期：维护 stdin/stdout 长连接、
按 turn 串行写入 prompt、读取到 turn 边界后交还控制权，并在进程死掉后
按同一会话配置自动拉起新进程。
"""

from __future__ import annotations

import asyncio
import os
import signal
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable

from ..core.agent_env import clean_cli_agent_env
from ..core.process_utils import hidden_subprocess_kwargs
from ..event_bus.event_types import EventType
from .cli_runtime import (
    CliExecutableNotFound,
    CliProcessNotFound,
    CliSubprocessNotSupported,
    ProcessChunk,
    resolve_cli_command,
)


@dataclass(frozen=True)
class CliSessionProcessConfig:
    session_id: str
    agent_id: str
    executable: str
    args: list[str]
    env_vars: dict[str, str]
    cwd: str
    stdin_mode: str = "pipe"
    runtime_key: str | None = None


@dataclass
class SessionProcessHandle:
    process_id: str
    runtime_key: str
    session_id: str
    agent_id: str
    executable: str
    cwd: str
    process: asyncio.subprocess.Process
    command: list[str]
    output_queue: asyncio.Queue[tuple[str, str | None]]
    pump_tasks: list[asyncio.Task]
    waiting_prompt: str | None = None
    turn_line_buffer: str = ""
    turn_active: bool = False
    completed_published: bool = False
    last_reused: bool = False
    last_recovered: bool = False

    def snapshot(self) -> dict:
        return {
            "processId": self.process_id,
            "sessionId": self.session_id,
            "runtimeKey": self.runtime_key,
            "agentId": self.agent_id,
            "executable": self.executable,
            "cwd": self.cwd,
            "mode": "session",
            "persistent": True,
            "pid": self.process.pid,
            "argv": self.command,
            "waitingPrompt": self.waiting_prompt,
            "turnActive": self.turn_active,
            "reused": self.last_reused,
            "recovered": self.last_recovered,
            "returnCode": self.process.returncode,
        }


class CliSessionProcessRuntime:
    """管理一会话一个常驻 CLI 进程。"""

    def __init__(self):
        self._handles_by_process: dict[str, SessionProcessHandle] = {}
        self._process_by_runtime_key: dict[str, str] = {}
        self._locks_by_runtime_key: dict[str, asyncio.Lock] = {}

    def active_snapshots(self, session_id: str | None = None) -> list[dict]:
        if session_id is None:
            return [handle.snapshot() for handle in self._handles_by_process.values()]
        return [
            handle.snapshot()
            for handle in self._handles_by_process.values()
            if handle.session_id == session_id or handle.runtime_key == session_id
        ]

    async def stream_turn(
        self,
        *,
        config: CliSessionProcessConfig,
        prompt: str,
        event_bus=None,
        silence_timeout_seconds: float = 300,
        turn_completed: Callable[[str], bool] | None = None,
    ) -> AsyncIterator[ProcessChunk]:
        workspace = Path(config.cwd)
        if not workspace.exists() or not workspace.is_dir():
            yield ProcessChunk("", event_type="error", error="workspace not found")
            return

        runtime_key = _runtime_key(config)
        lock = self._locks_by_runtime_key.setdefault(runtime_key, asyncio.Lock())
        async with lock:
            command = resolve_cli_command(config.executable, config.args)
            handle, reused, recovered = await self._ensure_process(
                config=config,
                command=command,
                workspace=workspace,
                event_bus=event_bus,
            )
            handle.last_reused = reused
            handle.last_recovered = recovered
            yield ProcessChunk(
                handle.process_id,
                event_type="started",
                command=handle.command,
                cwd=handle.cwd,
                pid=handle.process.pid,
                persistent=True,
                reused=reused,
                recovered=recovered,
            )

            if handle.process.returncode is not None:
                exit_code = handle.process.returncode
                await self._cleanup_handle(handle, unblock=True)
                yield ProcessChunk(
                    handle.process_id,
                    event_type="completed",
                    exit_code=exit_code,
                    persistent=True,
                )
                return
            if not handle.process.stdin:
                await self._cleanup_handle(handle, unblock=True)
                yield ProcessChunk(
                    handle.process_id,
                    event_type="error",
                    error="CLI 进程 stdin 不可用",
                    persistent=True,
                )
                return

            self._drain_available(handle.output_queue)
            handle.turn_line_buffer = ""
            handle.turn_active = True
            try:
                try:
                    if prompt:
                        handle.process.stdin.write(prompt.encode("utf-8", errors="replace"))
                        await handle.process.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    await self._cleanup_handle(handle, unblock=True)
                    handle, _, _ = await self._ensure_process(
                        config=config,
                        command=command,
                        workspace=workspace,
                        event_bus=event_bus,
                        recovered_override=True,
                    )
                    handle.last_reused = False
                    handle.last_recovered = True
                    yield ProcessChunk(
                        handle.process_id,
                        event_type="started",
                        command=handle.command,
                        cwd=handle.cwd,
                        pid=handle.process.pid,
                        persistent=True,
                        recovered=True,
                    )
                    if not handle.process.stdin:
                        yield ProcessChunk(
                            handle.process_id,
                            event_type="error",
                            error="CLI 进程 stdin 不可用",
                            persistent=True,
                        )
                        return
                    self._drain_available(handle.output_queue)
                    handle.turn_active = True
                    handle.process.stdin.write(prompt.encode("utf-8", errors="replace"))
                    await handle.process.stdin.drain()

                async for chunk in self._read_turn(
                    handle,
                    silence_timeout_seconds,
                    event_bus,
                    turn_completed,
                ):
                    yield chunk
                    if chunk.event_type in {
                        "turn_completed",
                        "timeout",
                        "completed",
                        "error",
                    }:
                        return
            finally:
                handle.waiting_prompt = None
                handle.turn_line_buffer = ""
                handle.turn_active = False

    async def reply(self, process_id: str, reply: str) -> None:
        handle = self._handles_by_process.get(process_id)
        if not handle or handle.process.returncode is not None or not handle.process.stdin:
            raise CliProcessNotFound(process_id)
        if reply not in {"y", "n"}:
            raise ValueError("reply must be 'y' or 'n'")
        handle.process.stdin.write(f"{reply}\n".encode("utf-8"))
        await handle.process.stdin.drain()
        handle.waiting_prompt = None

    async def terminate(self, process_id: str) -> None:
        handle = self._handles_by_process.get(process_id)
        if not handle or handle.process.returncode is not None:
            return
        await self._terminate_handle(handle)

    async def terminate_session(self, session_id: str) -> int:
        process_ids = [
            handle.process_id
            for handle in list(self._handles_by_process.values())
            if handle.session_id == session_id or handle.runtime_key == session_id
        ]
        for process_id in process_ids:
            await self.terminate(process_id)
        return len(process_ids)

    async def _ensure_process(
        self,
        *,
        config: CliSessionProcessConfig,
        command: list[str],
        workspace: Path,
        event_bus,
        recovered_override: bool | None = None,
    ) -> tuple[SessionProcessHandle, bool, bool]:
        runtime_key = _runtime_key(config)
        process_id = self._process_by_runtime_key.get(runtime_key)
        handle = self._handles_by_process.get(process_id or "")
        if (
            handle
            and handle.process.returncode is None
            and self._same_signature(handle, config=config, command=command, cwd=str(workspace))
        ):
            return handle, True, False

        recovered = bool(handle and handle.process.returncode is not None)
        if recovered_override is not None:
            recovered = recovered_override
        if handle:
            if handle.process.returncode is None:
                await self._terminate_handle(handle)
            else:
                await self._cleanup_handle(handle, unblock=True)

        process = await self._spawn_process(
            command=command,
            workspace=workspace,
            env_vars=config.env_vars,
            stdin_mode=config.stdin_mode,
            executable=config.executable,
        )
        output_queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()
        new_handle = SessionProcessHandle(
            process_id=f"cli_{uuid.uuid4().hex}",
            runtime_key=runtime_key,
            session_id=config.session_id,
            agent_id=config.agent_id,
            executable=config.executable,
            cwd=str(workspace),
            process=process,
            command=command,
            output_queue=output_queue,
            pump_tasks=[
                asyncio.create_task(self._pump(process.stdout, "stdout", output_queue)),
                asyncio.create_task(self._pump(process.stderr, "stderr", output_queue)),
            ],
        )
        self._handles_by_process[new_handle.process_id] = new_handle
        self._process_by_runtime_key[runtime_key] = new_handle.process_id
        await self._publish_process_started(new_handle, event_bus, recovered=recovered)
        return new_handle, False, recovered

    async def _spawn_process(
        self,
        *,
        command: list[str],
        workspace: Path,
        env_vars: dict[str, str],
        stdin_mode: str,
        executable: str,
    ) -> asyncio.subprocess.Process:
        env = self._build_env(env_vars)
        env.setdefault("NO_COLOR", "1")
        env.setdefault("TERM", "dumb")
        try:
            return await asyncio.create_subprocess_exec(
                *command,
                cwd=str(workspace),
                env=env,
                stdin=_resolve_stdin(stdin_mode),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **hidden_subprocess_kwargs(),
            )
        except NotImplementedError as exc:
            raise CliSubprocessNotSupported(_subprocess_not_supported_message()) from exc
        except FileNotFoundError as exc:
            raise CliExecutableNotFound(executable) from exc

    async def _read_turn(
        self,
        handle: SessionProcessHandle,
        silence_timeout_seconds: float,
        event_bus,
        turn_completed: Callable[[str], bool] | None,
    ) -> AsyncIterator[ProcessChunk]:
        closed: set[str] = set()
        while len(closed) < 2:
            try:
                stream, text = await asyncio.wait_for(
                    handle.output_queue.get(),
                    timeout=silence_timeout_seconds,
                )
            except TimeoutError:
                await self._publish(event_bus, EventType.AGENT_PROCESS_TIMEOUT, {
                    "sessionId": handle.session_id,
                    "agentId": handle.agent_id,
                    "processId": handle.process_id,
                    "reason": "silence",
                    "persistent": True,
                })
                await self._terminate_handle(handle)
                yield ProcessChunk(
                    handle.process_id,
                    event_type="timeout",
                    error="CLI 进程已超时（长时间无响应）",
                    persistent=True,
                )
                return

            if text is None:
                closed.add(stream)
                continue

            yield ProcessChunk(
                handle.process_id,
                text=text,
                stream=stream,
                persistent=True,
            )
            if stream == "stdout" and self._turn_is_completed(handle, text, turn_completed):
                yield ProcessChunk(
                    handle.process_id,
                    event_type="turn_completed",
                    persistent=True,
                )
                return

        exit_code = handle.process.returncode
        if exit_code is None:
            exit_code = await handle.process.wait()
        await self._cleanup_handle(handle, unblock=False)
        await self._publish_process_completed(handle, event_bus, exit_code=exit_code)
        yield ProcessChunk(
            handle.process_id,
            event_type="completed",
            exit_code=exit_code,
            persistent=True,
        )

    async def _terminate_handle(self, handle: SessionProcessHandle) -> None:
        if handle.process.returncode is None:
            if os.name == "nt":
                handle.process.terminate()
            else:
                handle.process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(handle.process.wait(), timeout=5)
            except TimeoutError:
                handle.process.kill()
                await handle.process.wait()
        await self._cleanup_handle(handle, unblock=True)

    async def _cleanup_handle(self, handle: SessionProcessHandle, *, unblock: bool) -> None:
        if self._handles_by_process.get(handle.process_id) is handle:
            self._handles_by_process.pop(handle.process_id, None)
        if self._process_by_runtime_key.get(handle.runtime_key) == handle.process_id:
            self._process_by_runtime_key.pop(handle.runtime_key, None)
        if handle.runtime_key not in self._process_by_runtime_key:
            lock = self._locks_by_runtime_key.get(handle.runtime_key)
            if lock and not lock.locked():
                self._locks_by_runtime_key.pop(handle.runtime_key, None)
        if unblock:
            await handle.output_queue.put(("stdout", None))
            await handle.output_queue.put(("stderr", None))
        for task in handle.pump_tasks:
            if not task.done():
                task.cancel()

    async def _publish_process_started(
        self,
        handle: SessionProcessHandle,
        event_bus,
        *,
        recovered: bool,
    ) -> None:
        await self._publish(event_bus, EventType.AGENT_PROCESS_STARTED, {
            "sessionId": handle.session_id,
            "agentId": handle.agent_id,
            "processId": handle.process_id,
            "pid": handle.process.pid,
            "executable": handle.command[0],
            "argv": handle.command,
            "cwd": handle.cwd,
            "persistent": True,
            "recovered": recovered,
        })

    async def _publish_process_completed(
        self,
        handle: SessionProcessHandle,
        event_bus,
        *,
        exit_code: int | None,
    ) -> None:
        if handle.completed_published:
            return
        handle.completed_published = True
        await self._publish(event_bus, EventType.AGENT_PROCESS_COMPLETED, {
            "sessionId": handle.session_id,
            "agentId": handle.agent_id,
            "processId": handle.process_id,
            "exitCode": exit_code,
            "persistent": True,
        })

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
    def _drain_available(queue: asyncio.Queue[tuple[str, str | None]]) -> None:
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    @staticmethod
    def _same_signature(
        handle: SessionProcessHandle,
        *,
        config: CliSessionProcessConfig,
        command: list[str],
        cwd: str,
    ) -> bool:
        return (
            handle.agent_id == config.agent_id
            and handle.executable == config.executable
            and (
                handle.command == command
                or _sessionless_command(handle.command) == _sessionless_command(command)
            )
            and handle.cwd == cwd
        )

    def _turn_is_completed(
        self,
        handle: SessionProcessHandle,
        text: str,
        turn_completed: Callable[[str], bool] | None,
    ) -> bool:
        if turn_completed is None:
            return False
        handle.turn_line_buffer += text
        while "\n" in handle.turn_line_buffer:
            line, handle.turn_line_buffer = handle.turn_line_buffer.split("\n", 1)
            if turn_completed(line):
                return True
        candidate = handle.turn_line_buffer.strip()
        return bool(candidate and turn_completed(candidate))

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


cli_session_process_runtime = CliSessionProcessRuntime()


def _resolve_stdin(stdin_mode: str):
    if stdin_mode == "inherit":
        return None
    return asyncio.subprocess.PIPE


def _runtime_key(config: CliSessionProcessConfig) -> str:
    return config.runtime_key or config.session_id


def _subprocess_not_supported_message() -> str:
    if os.name == "nt":
        return (
            "当前 Python asyncio 事件循环不支持启动 CLI 子进程。"
            "Windows 下请使用支持 subprocess 的 Proactor 事件循环启动后端，"
            "并避免 uvicorn --reload/Selector loop 启动方式。"
        )
    return "当前 Python asyncio 事件循环不支持启动 CLI 子进程。"


def _sessionless_command(command: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(command):
        arg = command[index]
        if arg in {"-r", "--resume", "--session-id"}:
            index += 2 if index + 1 < len(command) else 1
            continue
        if arg.startswith("--resume=") or arg.startswith("--session-id="):
            index += 1
            continue
        result.append(arg)
        index += 1
    return result
