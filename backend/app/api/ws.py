import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..models import Session as DBSession
from ..infrastructure.realtime import manager

router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str):
    async with AsyncSessionLocal() as db:
        session = await db.get(DBSession, session_id)
        if not session:
            await ws.close(code=4004, reason="Session not found")
            return

    await manager.connect(session_id, ws)

    heartbeat_task = asyncio.create_task(manager.heartbeat_loop(session_id, ws))

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "pong":
                    pass  # 心跳响应，仅保活
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await manager.disconnect(session_id, ws)
