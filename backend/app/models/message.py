from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from ..database import Base
from ..core.timezone import china_now


def _utcnow():
    return china_now()


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False, default="")
    content_type = Column(String, nullable=False, default="text")
    agent_name = Column(String, nullable=True)
    source_type = Column(String, nullable=False, default="agent")
    source_id = Column(String, nullable=True)
    source_name = Column(String, nullable=True)
    metadata_json = Column(String, nullable=True)
    parent_message_id = Column(String, nullable=True)
    is_pinned = Column(String, nullable=False, default="0")
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    session = relationship("Session", back_populates="messages")
