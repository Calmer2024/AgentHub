from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from ..database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    type = Column(String, nullable=False)  # "code_diff" | "web_preview" | "document"
    title = Column(String, nullable=False, default="")
    content = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="rendering")  # "rendering" | "ready" | "error"
    version = Column(Integer, nullable=False, default=1)
    parent_artifact_id = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    preview_id = Column(String, nullable=True)
    source = Column(String, nullable=True)
    confidence = Column(String, nullable=True)
    task_id = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    project = relationship("Project", back_populates="artifacts")
