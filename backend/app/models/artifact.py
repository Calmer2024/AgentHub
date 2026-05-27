from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey

from ..database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    type = Column(String, nullable=False)  # "code_diff" | "web_preview" | "document"
    title = Column(String, nullable=False, default="")
    content = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="rendering")  # "rendering" | "ready" | "error"
    created_at = Column(DateTime, nullable=False, default=_utcnow)
