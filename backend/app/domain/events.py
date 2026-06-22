"""Domain event publishing contracts."""

from __future__ import annotations

from typing import Any, Protocol


ORCHESTRATOR_TASK_STARTED = "orchestrator.task.started"
ORCHESTRATOR_TASK_COMPLETED = "orchestrator.task.completed"


class DomainEventPublisher(Protocol):
    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        """Publish a domain event by semantic name."""
