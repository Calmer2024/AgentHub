"""Application use case for sending a chat message.

This module owns runtime routing for a user message so API handlers can remain
thin interface adapters.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Project, Session as DBSession, User
from ..services.chat_service_impl import ChatServiceImpl
from ..services.cloud_agent_runtime import CloudAgentRuntimeService
from ..services.schemas import ChatRequest


@dataclass(frozen=True)
class SendMessageCommand:
    session: DBSession
    project: Project | None
    request: ChatRequest
    actor: User | None = None


class SendMessageUseCase:
    """Route a message to the appropriate runtime and return an SSE stream."""

    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus

    def execute(self, command: SendMessageCommand) -> AsyncIterator[str]:
        session = command.session
        data = command.request
        if command.project and command.project.workspace_mode == "cloud":
            runtime = CloudAgentRuntimeService(self.db, event_bus=self.event_bus)
            if session.mode == "group":
                return runtime.stream_group_chat(
                    session.id,
                    data.content,
                    actor=command.actor,
                    mentions=data.mentions,
                    parent_message_id=data.parent_message_id,
                    attachment_ids=data.attachment_ids,
                )
            return runtime.stream_chat(
                session.id,
                data.content,
                actor=command.actor,
                parent_message_id=data.parent_message_id,
                attachment_ids=data.attachment_ids,
            )

        return ChatServiceImpl(self.db, event_bus=self.event_bus).send_message_stream(
            session.id,
            data.content,
            data.mentions,
            parent_message_id=data.parent_message_id,
            chain_config=data.chain_config,
            attachment_ids=data.attachment_ids,
        )
