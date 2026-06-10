from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class Comment(Base):
    __tablename__ = "comments"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=False)
    author_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True)
    uploaded_by = Column(String, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    storage_uri = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class ArtifactReference(Base):
    __tablename__ = "artifact_references"

    id = Column(String, primary_key=True)
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    artifact_id = Column(String, ForeignKey("artifacts.id"), nullable=False)
    artifact_version_id = Column(String, nullable=True)
    relation = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class AgentTemplateSession(Base):
    __tablename__ = "agent_template_sessions"

    id = Column(String, primary_key=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False, default="draft")
    draft_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class GitSyncJob(Base):
    __tablename__ = "git_sync_jobs"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    mode = Column(String, nullable=False)
    remote = Column(Text, nullable=False)
    branch = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    commit_sha = Column(String, nullable=True)
    error_summary = Column(Text, nullable=True)
    logs_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
