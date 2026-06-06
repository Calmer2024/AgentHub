from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from ..database import Base
from ..core.timezone import china_now


def _utcnow():
    return china_now()


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False, default="新对话")
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    agent_config_id = Column(String, ForeignKey("agent_configs.id"), nullable=True)
    agent_name = Column(String, nullable=True)
    mode = Column(String, nullable=False, default="single")
    is_active = Column(String, nullable=False, default="1")  # "1"=active, "0"=soft-deleted
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    agent_config = relationship("AgentConfig")
    project = relationship("Project", back_populates="sessions")
