"""CLI 运行时门面。

业务层只通过这里查看、回复或终止 CLI 进程；短进程与会话级常驻进程
属于基础设施内部实现细节。
"""

from __future__ import annotations

from .cli_rpc_session_runtime import cli_rpc_session_runtime
from .cli_runtime import CliProcessNotFound, cli_process_manager
from .cli_session_runtime import cli_session_process_runtime


class CliRuntimeRegistry:
    def active_snapshots(self, session_id: str | None = None) -> list[dict]:
        return [
            *cli_process_manager.active_snapshots(session_id),
            *cli_session_process_runtime.active_snapshots(session_id),
            *cli_rpc_session_runtime.active_snapshots(session_id),
        ]

    async def reply(self, process_id: str, reply: str) -> None:
        try:
            await cli_process_manager.reply(process_id, reply)
            return
        except CliProcessNotFound:
            pass
        try:
            await cli_session_process_runtime.reply(process_id, reply)
            return
        except CliProcessNotFound:
            pass
        await cli_rpc_session_runtime.reply(process_id, reply)

    async def terminate(self, process_id: str) -> None:
        await cli_process_manager.terminate(process_id)
        await cli_session_process_runtime.terminate(process_id)
        await cli_rpc_session_runtime.terminate(process_id)

    async def terminate_session(self, session_id: str) -> int:
        oneshot = await cli_process_manager.terminate_session(session_id)
        session_processes = await cli_session_process_runtime.terminate_session(session_id)
        rpc_processes = await cli_rpc_session_runtime.terminate_session(session_id)
        return oneshot + session_processes + rpc_processes


cli_runtime_registry = CliRuntimeRegistry()
