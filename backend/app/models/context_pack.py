from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class ContextPackSnapshot(Base):
    __tablename__ = "context_pack_snapshots"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    purpose = Column(String, nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
