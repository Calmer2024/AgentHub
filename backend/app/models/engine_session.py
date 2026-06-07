from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class EngineSession(Base):
    """AgentHub 会话到 CLI 底层 Engine 会话的持久映射。"""

    __tablename__ = "engine_sessions"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    agent_config_id = Column(String, ForeignKey("agent_configs.id"), nullable=False)
    cli_tool = Column(String, nullable=False)
    workspace_path = Column(String, nullable=False)
    engine_session_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
