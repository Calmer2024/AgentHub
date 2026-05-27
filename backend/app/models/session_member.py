from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey

from ..database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SessionMember(Base):
    __tablename__ = "session_members"

    session_id = Column(String, ForeignKey("sessions.id"), primary_key=True)
    agent_config_id = Column(String, ForeignKey("agent_configs.id"), primary_key=True)
    joined_at = Column(DateTime, nullable=False, default=_utcnow)
