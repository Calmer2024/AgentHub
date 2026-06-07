"""会话标题自动生成服务。"""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..models import AgentConfig, Session as DBSession
from .schemas import SessionRead
from .system_llm import SystemLLMUnavailableError, system_llm


DEFAULT_TITLES = {"新对话", "群聊"}
MAX_TITLE_CHARS = 24


class SessionTitleService:
    """在首轮对话完成后，为默认标题会话生成可读短标题。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def maybe_generate_title(
        self,
        *,
        session_id: str,
        user_content: str,
        assistant_content: str = "",
    ) -> SessionRead | None:
        session = await self.db.get(DBSession, session_id)
        if not session or not await self._should_generate(session):
            return None

        title = await self._generate_title(user_content, assistant_content)
        if not title:
            return None

        session.title = title
        session.updated_at = china_now()
        await self.db.commit()
        await self.db.refresh(session)
        return SessionRead.model_validate(session)

    async def _should_generate(self, session: DBSession) -> bool:
        current = (session.title or "").strip()
        if current in DEFAULT_TITLES:
            return True

        if session.agent_config_id:
            agent = await self.db.get(AgentConfig, session.agent_config_id)
            if agent and current == (agent.name or "").strip():
                return True

        return False

    async def _generate_title(self, user_content: str, assistant_content: str) -> str:
        fallback = fallback_title(user_content)
        if not system_llm.is_configured():
            return fallback
        try:
            response = await system_llm.chat(
                system_prompt=(
                    "你是 AgentHub 的会话标题生成器。"
                    "请根据用户目标和助手回应生成中文短标题。"
                    "只输出标题本身，不要引号、编号、标点装饰或解释。"
                    "标题不超过 12 个中文字符，能概括任务对象和动作。"
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"用户消息:\n{user_content[:1200]}\n\n"
                        f"助手回应摘要:\n{assistant_content[:1200]}\n\n"
                        "请输出短标题。"
                    ),
                }],
            )
            generated = clean_title(response.content)
            return generated or fallback
        except (SystemLLMUnavailableError, Exception):
            return fallback


def fallback_title(content: str) -> str:
    clean = clean_title(content)
    return clean or "新任务"


def clean_title(value: str) -> str:
    text = " ".join(str(value or "").split())
    text = re.sub(r"^[\"'“”‘’`#\-\s]+|[\"'“”‘’`#\-\s]+$", "", text)
    text = re.sub(r"^(标题|会话标题|题目)\s*[:：]\s*", "", text)
    text = text.strip("。.!！?？,，;；:：")
    if not text:
        return ""
    return text[:MAX_TITLE_CHARS]
