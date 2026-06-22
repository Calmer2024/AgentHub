"""Infrastructure adapter for publishing domain events to the app event bus."""

from __future__ import annotations

from typing import Any

from ..domain.events import (
    ORCHESTRATOR_TASK_COMPLETED,
    ORCHESTRATOR_TASK_STARTED,
)
from ..event_bus import EventType


_EVENT_TYPE_BY_NAME = {
    ORCHESTRATOR_TASK_STARTED: EventType.ORCHESTRATOR_TASK_STARTED,
    ORCHESTRATOR_TASK_COMPLETED: EventType.ORCHESTRATOR_TASK_COMPLETED,
}


class EventBusDomainEventPublisher:
    """Translate domain event names to infrastructure EventType values."""

    def __init__(self, event_bus: Any):
        self._event_bus = event_bus

    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        event_type = _EVENT_TYPE_BY_NAME.get(event_name)
        if event_type is None:
            return
        await self._event_bus.publish(event_type, payload)


def domain_event_publisher_from_event_bus(event_bus: Any):
    if event_bus is None:
        return None
    if isinstance(event_bus, EventBusDomainEventPublisher):
        return event_bus
    return EventBusDomainEventPublisher(event_bus)
