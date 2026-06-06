import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

from .event_types import EventType

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    """事件总线接口，定义于 Infrastructure 层。"""

    async def publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        raise NotImplementedError

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    """基于 asyncio.Queue + dict 的内存事件总线。

    特性:
    - 发布者不关心订阅者是否存在（fire-and-forget）
    - 单个订阅者异常不影响其他订阅者（异常隔离）
    - 零外部依赖
    """

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[tuple[EventType, dict[str, Any]]] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._dispatcher())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        await self._queue.put((event_type, payload))

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        handlers = self._subscribers.get(event_type, [])
        try:
            handlers.remove(handler)
        except ValueError:
            pass

    async def _dispatcher(self) -> None:
        while True:
            event_type, payload = await self._queue.get()
            for handler in self._subscribers.get(event_type, []):
                try:
                    await handler(payload)
                except Exception:
                    logger.exception(
                        "事件处理异常: type=%s handler=%s", event_type, handler
                    )
            self._queue.task_done()
