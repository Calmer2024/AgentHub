
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from ..database import Base
from ..core.timezone import china_now


def _utcnow():
    return china_now()


class ApprovalCheckpoint(Base):
    __tablename__ = "approval_checkpoints"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    task_id = Column(String, ForeignKey("run_tasks.id"), nullable=False)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    message_id = Column(String, ForeignKey("messages.id"), nullable=True)
    artifact_id = Column(String, ForeignKey("artifacts.id"), nullable=True)
    artifact_version = Column(Integer, nullable=True)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="pending_review")
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    decided_at = Column(DateTime, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")
