"""JSON-RPC 会话级 CLI 进程运行时。

本模块服务 Codex MCP server 和 OpenCode ACP 这类“常驻进程 + JSON-RPC”
协议。它只负责进程生命周期、请求/响应相关性、通知队列和 per-session
turn lock；具体工具名、prompt 参数和输出解析由 Adapter 提供。
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import signal
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Literal

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


RpcProtocol = Literal["mcp", "acp"]


@dataclass(frozen=True)
class CliRpcSessionConfig:
    session_id: str
    agent_id: str
    executable: str
    args: list[str]
    env_vars: dict[str, str]
    cwd: str
    protocol: RpcProtocol
    cli_tool: str
    runtime_key: str | None = None


@dataclass
class CliRpcTurnRequest:
    method: str
    params: dict
    metadata_event: dict | None = None
    resume_method: str | None = None
    resume_params: dict | None = None
    native_session_param: str | None = None


@dataclass
class RpcProcessHandle:
    process_id: str
    runtime_key: str
    session_id: str
    agent_id: str
    executable: str
    cwd: str
    protocol: RpcProtocol
    cli_tool: str
    process: asyncio.subprocess.Process
    command: list[str]
    reader_task: asyncio.Task
    stderr_task: asyncio.Task
    pending: dict[int, asyncio.Future] = field(default_factory=dict)
    notifications: asyncio.Queue[dict] = field(default_factory=asyncio.Queue)
    stderr_queue: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue)
    next_request_id: int = 1
    initialized: bool = False
    native_session_id: str | None = None
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
            "mode": "rpc_session",
            "protocol": self.protocol,
            "cliTool": self.cli_tool,
            "persistent": True,
            "pid": self.process.pid,
            "argv": self.command,
            "turnActive": self.turn_active,
            "nativeSessionId": self.native_session_id,
            "reused": self.last_reused,
            "recovered": self.last_recovered,
            "returnCode": self.process.returncode,
        }


class CliRpcSessionRuntime:
    """管理一会话一个 JSON-RPC CLI 子进程。"""

    def __init__(self):
        self._handles_by_process: dict[str, RpcProcessHandle] = {}
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
        config: CliRpcSessionConfig,
        request: CliRpcTurnRequest,
        event_bus=None,
        silence_timeout_seconds: float = 600,
    ) -> AsyncIterator[ProcessChunk]:
        workspace = Path(config.cwd)
        if not workspace.exists() or not workspace.is_dir():
            yield ProcessChunk("", event_type="error", error="workspace not found", persistent=True)
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
                await self._cleanup_handle(handle)
                yield ProcessChunk(
                    handle.process_id,
                    event_type="completed",
                    exit_code=exit_code,
                    persistent=True,
                )
                return

            handle.turn_active = True
            try:
                if request.metadata_event:
                    yield ProcessChunk(
                        handle.process_id,
                        text=json.dumps(request.metadata_event, ensure_ascii=False) + "\n",
                        persistent=True,
                    )

                call_task = asyncio.create_task(self._call_turn(handle, request))
                while True:
                    notify_task = asyncio.create_task(handle.notifications.get())
                    stderr_task = asyncio.create_task(handle.stderr_queue.get())
                    done, pending = await asyncio.wait(
                        {call_task, notify_task, stderr_task},
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=silence_timeout_seconds,
                    )
                    if not done:
                        notify_task.cancel()
                        stderr_task.cancel()
                        call_task.cancel()
                        await self._publish(event_bus, EventType.AGENT_PROCESS_TIMEOUT, {
                            "sessionId": handle.session_id,
                            "agentId": handle.agent_id,
                            "processId": handle.process_id,
                            "reason": "silence",
                            "persistent": True,
                            "protocol": handle.protocol,
                        })
                        await self._terminate_handle(handle)
                        yield ProcessChunk(
                            handle.process_id,
                            event_type="timeout",
                            error="CLI RPC 进程已超时（长时间无响应）",
                            persistent=True,
                        )
                        return

                    for task in pending:
                        if task is not call_task:
                            task.cancel()

                    if notify_task in done:
                        message = notify_task.result()
                        for event in self._events_from_notification(message):
                            yield ProcessChunk(
                                handle.process_id,
                                text=json.dumps(event, ensure_ascii=False) + "\n",
                                persistent=True,
                            )
                        continue

                    if stderr_task in done:
                        stderr_text = stderr_task.result()
                        if stderr_text:
                            yield ProcessChunk(
                                handle.process_id,
                                text=stderr_text,
                                stream="stderr",
                                persistent=True,
                            )
                        continue

                    if call_task in done:
                        result = call_task.result()
                        for event in self._events_from_result(handle, request, result):
                            yield ProcessChunk(
                                handle.process_id,
                                text=json.dumps(event, ensure_ascii=False) + "\n",
                                persistent=True,
                            )
                        yield ProcessChunk(
                            handle.process_id,
                            event_type="turn_completed",
                            persistent=True,
                        )
                        return
            except (BrokenPipeError, ConnectionResetError, RuntimeError) as exc:
                await self._cleanup_handle(handle)
                yield ProcessChunk(
                    handle.process_id,
                    event_type="error",
                    error=f"CLI RPC 进程通信失败：{exc}",
                    persistent=True,
                )
                return
            finally:
                handle.turn_active = False

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

    async def reply(self, process_id: str, reply: str) -> None:
        del reply
        if process_id in self._handles_by_process:
            raise ValueError("当前 RPC 运行时暂不支持交互式 y/n 回复")
        raise CliProcessNotFound(process_id)

    async def _ensure_process(
        self,
        *,
        config: CliRpcSessionConfig,
        command: list[str],
        workspace: Path,
        event_bus,
    ) -> tuple[RpcProcessHandle, bool, bool]:
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
        if handle:
            if handle.process.returncode is None:
                await self._terminate_handle(handle)
            else:
                await self._cleanup_handle(handle)

        process = await self._spawn_process(
            command=command,
            workspace=workspace,
            env_vars=config.env_vars,
            executable=config.executable,
        )
        new_handle = RpcProcessHandle(
            process_id=f"cli_{uuid.uuid4().hex}",
            runtime_key=runtime_key,
            session_id=config.session_id,
            agent_id=config.agent_id,
            executable=config.executable,
            cwd=str(workspace),
            protocol=config.protocol,
            cli_tool=config.cli_tool,
            process=process,
            command=command,
            reader_task=asyncio.create_task(asyncio.sleep(0)),
            stderr_task=asyncio.create_task(asyncio.sleep(0)),
        )
        new_handle.reader_task = asyncio.create_task(self._reader_loop(new_handle))
        new_handle.stderr_task = asyncio.create_task(self._stderr_loop(new_handle))
        self._handles_by_process[new_handle.process_id] = new_handle
        self._process_by_runtime_key[runtime_key] = new_handle.process_id
        await self._initialize(new_handle)
        await self._publish_process_started(new_handle, event_bus, recovered=recovered)
        return new_handle, False, recovered

    async def _spawn_process(
        self,
        *,
        command: list[str],
        workspace: Path,
        env_vars: dict[str, str],
        executable: str,
    ) -> asyncio.subprocess.Process:
        env = os.environ.copy()
        for key, value in clean_cli_agent_env(env_vars).items():
            if value:
                env[str(key)] = str(value)
        env.setdefault("NO_COLOR", "1")
        env.setdefault("TERM", "dumb")
        try:
            return await asyncio.create_subprocess_exec(
                *command,
                cwd=str(workspace),
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **hidden_subprocess_kwargs(),
            )
        except NotImplementedError as exc:
            raise CliSubprocessNotSupported(_subprocess_not_supported_message()) from exc
        except FileNotFoundError as exc:
            raise CliExecutableNotFound(executable) from exc

    async def _initialize(self, handle: RpcProcessHandle) -> None:
        if handle.initialized:
            return
        if handle.protocol == "mcp":
            await self._call(handle, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "AgentHub", "version": "0.1.0"},
            })
            await self._notify(handle, "notifications/initialized", {})
        else:
            await self._call(handle, "initialize", {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
                "clientInfo": {
                    "name": "agenthub",
                    "title": "AgentHub",
                    "version": "0.1.0",
                },
            })
            result = await self._call(handle, "session/new", {
                "cwd": handle.cwd,
                "mcpServers": [],
            })
            if isinstance(result, dict):
                handle.native_session_id = str(result.get("sessionId") or "") or None
        handle.initialized = True

    async def _call(self, handle: RpcProcessHandle, method: str, params: dict) -> dict | list | str | None:
        if not handle.process.stdin:
            raise RuntimeError("CLI RPC 进程 stdin 不可用")
        request_id = handle.next_request_id
        handle.next_request_id += 1
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        handle.pending[request_id] = future
        await self._write_message(handle, {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        })
        return await future

    async def _call_turn(self, handle: RpcProcessHandle, request: CliRpcTurnRequest) -> dict | list | str | None:
        method = request.method
        params = copy.deepcopy(request.params)
        if handle.native_session_id and request.resume_method:
            method = request.resume_method
            params = copy.deepcopy(request.resume_params or {})
        if handle.native_session_id and request.native_session_param:
            _set_nested_param(params, request.native_session_param, handle.native_session_id)
        return await self._call(handle, method, params)

    async def _notify(self, handle: RpcProcessHandle, method: str, params: dict) -> None:
        await self._write_message(handle, {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        })

    async def _write_message(self, handle: RpcProcessHandle, message: dict) -> None:
        if not handle.process.stdin:
            raise RuntimeError("CLI RPC 进程 stdin 不可用")
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        payload = raw + b"\n"
        handle.process.stdin.write(payload)
        await handle.process.stdin.drain()

    async def _reader_loop(self, handle: RpcProcessHandle) -> None:
        try:
            while True:
                message = await self._read_line_message(handle.process.stdout)
                if message is None:
                    break
                await self._dispatch_message(handle, message)
        except Exception as exc:
            for future in handle.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError(str(exc)))

    async def _dispatch_message(self, handle: RpcProcessHandle, message: dict) -> None:
        if "id" in message and ("result" in message or "error" in message):
            future = handle.pending.pop(message["id"], None)
            if not future or future.done():
                return
            if "error" in message:
                error = message.get("error") or {}
                future.set_exception(RuntimeError(str(error.get("message") or error)))
            else:
                future.set_result(message.get("result"))
            return

        if "id" in message and "method" in message:
            await self._handle_peer_request(handle, message)
            return

        await handle.notifications.put(message)

    async def _handle_peer_request(self, handle: RpcProcessHandle, message: dict) -> None:
        method = str(message.get("method") or "")
        result: object = {}
        if method == "session/request_permission":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            options = params.get("options") if isinstance(params.get("options"), list) else []
            selected = _select_permission_option(options)
            result = {"outcome": {"outcome": "selected", "optionId": selected}} if selected else {
                "outcome": {"outcome": "cancelled"}
            }
        elif method.startswith("fs/") or method.startswith("terminal/"):
            await self._write_message(handle, {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {
                    "code": -32601,
                    "message": f"AgentHub client capability not enabled: {method}",
                },
            })
            return
        await self._write_message(handle, {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": result,
        })

    @staticmethod
    async def _read_line_message(reader) -> dict | None:
        if reader is None:
            return None
        line = await reader.readline()
        if not line:
            return None
        return json.loads(line.decode("utf-8", errors="replace"))

    @staticmethod
    async def _stderr_loop(handle: RpcProcessHandle) -> None:
        reader = handle.process.stderr
        if reader is None:
            await handle.stderr_queue.put(None)
            return
        while True:
            data = await reader.read(1024)
            if not data:
                break
            await handle.stderr_queue.put(data.decode("utf-8", errors="replace"))
        await handle.stderr_queue.put(None)

    def _events_from_notification(self, message: dict) -> list[dict]:
        method = str(message.get("method") or "")
        params = message.get("params")
        if method == "session/update" and isinstance(params, dict):
            update = params.get("update")
            return [update] if isinstance(update, dict) else []
        return []

    def _events_from_result(
        self,
        handle: RpcProcessHandle,
        request: CliRpcTurnRequest,
        result: object,
    ) -> list[dict]:
        if handle.protocol == "mcp":
            return self._codex_events_from_result(handle, result)
        stop_reason = "end_turn"
        if isinstance(result, dict):
            stop_reason = str(result.get("stopReason") or stop_reason)
        events: list[dict] = []
        if handle.native_session_id:
            events.append({
                "type": "session.created",
                "sessionId": handle.native_session_id,
            })
        events.append({"type": "session.prompt.completed", "stopReason": stop_reason})
        return events

    @staticmethod
    def _codex_events_from_result(handle: RpcProcessHandle, result: object) -> list[dict]:
        events: list[dict] = []
        data = result if isinstance(result, dict) else {}
        structured = data.get("structuredContent") if isinstance(data.get("structuredContent"), dict) else {}
        thread_id = str(structured.get("threadId") or handle.native_session_id or "").strip()
        if thread_id:
            handle.native_session_id = thread_id
            events.append({"type": "thread.started", "thread_id": thread_id})
        content = structured.get("content")
        if not isinstance(content, str) or not content:
            content = _text_from_mcp_content(data.get("content"))
        if content:
            events.append({
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": content,
                },
            })
        events.append({"type": "turn.completed"})
        return events

    async def _terminate_handle(self, handle: RpcProcessHandle) -> None:
        if handle.process.returncode is None:
            if handle.protocol == "acp" and handle.native_session_id:
                try:
                    await self._notify(handle, "session/cancel", {"sessionId": handle.native_session_id})
                except Exception:
                    pass
            if os.name == "nt":
                handle.process.terminate()
            else:
                handle.process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(handle.process.wait(), timeout=5)
            except TimeoutError:
                handle.process.kill()
                await handle.process.wait()
        await self._cleanup_handle(handle)

    async def _cleanup_handle(self, handle: RpcProcessHandle) -> None:
        if self._handles_by_process.get(handle.process_id) is handle:
            self._handles_by_process.pop(handle.process_id, None)
        if self._process_by_runtime_key.get(handle.runtime_key) == handle.process_id:
            self._process_by_runtime_key.pop(handle.runtime_key, None)
        if handle.runtime_key not in self._process_by_runtime_key:
            lock = self._locks_by_runtime_key.get(handle.runtime_key)
            if lock and not lock.locked():
                self._locks_by_runtime_key.pop(handle.runtime_key, None)
        for future in handle.pending.values():
            if not future.done():
                future.cancel()
        for task in (handle.reader_task, handle.stderr_task):
            if not task.done():
                task.cancel()

    async def _publish_process_started(
        self,
        handle: RpcProcessHandle,
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
            "protocol": handle.protocol,
            "recovered": recovered,
        })

    @staticmethod
    async def _publish(event_bus, event_type: EventType, payload: dict) -> None:
        if not event_bus:
            return
        try:
            await event_bus.publish(event_type, payload)
        except Exception:
            pass

    @staticmethod
    def _same_signature(
        handle: RpcProcessHandle,
        *,
        config: CliRpcSessionConfig,
        command: list[str],
        cwd: str,
    ) -> bool:
        return (
            handle.agent_id == config.agent_id
            and handle.executable == config.executable
            and handle.command == command
            and handle.cwd == cwd
            and handle.protocol == config.protocol
            and handle.cli_tool == config.cli_tool
        )


cli_rpc_session_runtime = CliRpcSessionRuntime()


def _select_permission_option(options: list) -> str:
    for preferred in ("allow_always", "allow_once"):
        for option in options:
            if isinstance(option, dict) and option.get("kind") == preferred:
                return str(option.get("optionId") or "")
    return ""


def _runtime_key(config: CliRpcSessionConfig) -> str:
    return config.runtime_key or config.session_id


def _text_from_mcp_content(content: object) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(part for part in parts if part)


def _set_nested_param(params: dict, path: str, value: str) -> None:
    current = params
    parts = [part for part in path.split(".") if part]
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    if parts:
        current[parts[-1]] = value


def _subprocess_not_supported_message() -> str:
    if os.name == "nt":
        return (
            "当前 Python asyncio 事件循环不支持启动 CLI 子进程。"
            "Windows 下请使用支持 subprocess 的 Proactor 事件循环启动后端，"
            "并避免 uvicorn --reload/Selector loop 启动方式。"
        )
    return "当前 Python asyncio 事件循环不支持启动 CLI 子进程。"
