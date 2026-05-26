from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Boolean, DateTime

from ..database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False, default="")
    system_prompt = Column(String, nullable=False, default="你是一个有帮助的 AI 助手。")
    provider = Column(String, nullable=False, default="deepseek")
    model = Column(String, nullable=False, default="deepseek-v4-flash")
    temperature = Column(Float, nullable=False, default=0.7)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
