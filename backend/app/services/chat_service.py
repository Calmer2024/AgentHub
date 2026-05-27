"""聊天服务接口定义。

Phase 3 Module 1 只定义抽象接口。完整实现在 Module A (Smart Collaboration) 中提供。
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class ChatService(ABC):

    @abstractmethod
    async def send_message_stream(
        self,
        session_id: str,
        content: str,
        mentions: list[str] | None = None,
        parent_message_id: str | None = None,
    ) -> AsyncIterator[str]:
        ...
