from sqlalchemy import Column, String, DateTime, ForeignKey

from ..database import Base
from ..core.timezone import china_now


def _utcnow():
    return china_now()


class SessionMember(Base):
    __tablename__ = "session_members"

    session_id = Column(String, ForeignKey("sessions.id"), primary_key=True)
    agent_config_id = Column(String, ForeignKey("agent_configs.id"), primary_key=True)
    joined_at = Column(DateTime, nullable=False, default=_utcnow)
