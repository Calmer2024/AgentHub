from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Run(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    mode = Column(String, nullable=False, default="single")
    status = Column(String, nullable=False, default="queued")
    current_message_id = Column(String, ForeignKey("messages.id"), nullable=True)
    started_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    completed_at = Column(DateTime, nullable=True)
    cancel_reason = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")

    tasks = relationship("RunTask", back_populates="run", cascade="all, delete-orphan")
    processes = relationship("RunProcess", back_populates="run", cascade="all, delete-orphan")


class RunTask(Base):
    __tablename__ = "run_tasks"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agent_configs.id"), nullable=True)
    message_id = Column(String, ForeignKey("messages.id"), nullable=True)
    name = Column(String, nullable=False, default="primary")
    role = Column(String, nullable=True)
    phase = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="pending")
    depends_on_json = Column(Text, nullable=False, default="[]")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")

    run = relationship("Run", back_populates="tasks")
    processes = relationship("RunProcess", back_populates="task")


class RunProcess(Base):
    __tablename__ = "run_processes"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    task_id = Column(String, ForeignKey("run_tasks.id"), nullable=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agent_configs.id"), nullable=True)
    message_id = Column(String, ForeignKey("messages.id"), nullable=True)
    process_id = Column(String, nullable=False)
    pid = Column(Integer, nullable=True)
    executable = Column(String, nullable=True)
    cwd = Column(String, nullable=True)
    status = Column(String, nullable=False, default="running")
    started_at = Column(DateTime, nullable=False, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)
    exit_code = Column(Integer, nullable=True)

    run = relationship("Run", back_populates="processes")
    task = relationship("RunTask", back_populates="processes")
