"""Realtime publishing adapter.

Application modules use this seam to publish session-scoped realtime events
without depending on API route modules.
"""

from __future__ import annotations

import asyncio
import json
from typing import Protocol

from fastapi import WebSocket


class RealtimePublisher(Protocol):
    async def broadcast(self, session_id: str, event: dict) -> None:
        ...


class ConnectionManager:
    def __init__(self):
        self._sessions: dict[str, set[WebSocket]] = {}

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self._sessions.setdefault(session_id, set()).add(ws)

    async def disconnect(self, session_id: str, ws: WebSocket):
        if session_id in self._sessions:
            self._sessions[session_id].discard(ws)
            if not self._sessions[session_id]:
                del self._sessions[session_id]

    async def broadcast(self, session_id: str, event: dict):
        connections = self._sessions.get(session_id, set())
        dead = []
        for ws in connections:
            try:
                await ws.send_text(json.dumps(event, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(session_id, ws)

    async def send_personal(self, ws: WebSocket, event: dict):
        try:
            await ws.send_text(json.dumps(event, ensure_ascii=False))
        except Exception:
            pass

    async def heartbeat_loop(self, session_id: str, ws: WebSocket):
        try:
            while ws in self._sessions.get(session_id, set()):
                await asyncio.sleep(30)
                try:
                    await ws.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
        except asyncio.CancelledError:
            pass


manager = ConnectionManager()
