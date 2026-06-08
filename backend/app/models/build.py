from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class BuildRun(Base):
    __tablename__ = "build_runs"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    status = Column(String, nullable=False, default="queued")
    command = Column(Text, nullable=False)
    install_command = Column(Text, nullable=True)
    artifact_path = Column(Text, nullable=True)
    exit_code = Column(Integer, nullable=True)
    error_summary = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class BuildLog(Base):
    __tablename__ = "build_logs"

    id = Column(String, primary_key=True)
    build_id = Column(String, ForeignKey("build_runs.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
    stream = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
