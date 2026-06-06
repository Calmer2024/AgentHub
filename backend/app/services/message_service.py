"""消息服务接口定义。

Phase 3 Module 1 只定义抽象接口。完整 SQLAlchemy 实现在 Module A (Smart Collaboration) 中提供。
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .schemas import MessageCreate, MessageRead


class MessageService(ABC):

    @abstractmethod
    async def get_session_messages(
        self,
        session_id: str,
        limit: int = 50,
        before: str | None = None,
        include_internal: bool = False,
    ) -> list[MessageRead]:
        ...

    @abstractmethod
    async def reply_to_message(
        self, input: MessageCreate, parent_message_id: str
    ) -> MessageRead:
        ...

    @abstractmethod
    async def regenerate_message(self, message_id: str) -> AsyncIterator[str]:
        ...

    @abstractmethod
    async def pin_message(self, message_id: str) -> None:
        ...

    @abstractmethod
    async def unpin_message(self, message_id: str) -> None:
        ...

    @abstractmethod
    async def get_pinned_messages(self, session_id: str) -> list[MessageRead]:
        ...

    @abstractmethod
    async def search_messages(
        self, session_id: str, query: str, limit: int = 20
    ) -> list[MessageRead]:
        ...
