from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from ..database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False, default="新对话")
    agent_config_id = Column(String, ForeignKey("agent_configs.id"), nullable=True)
    agent_name = Column(String, nullable=True)  # 兼容旧数据，待迁移完成后删除
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    agent_config = relationship("AgentConfig")
