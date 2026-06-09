from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class PreviewSession(Base):
    __tablename__ = "preview_sessions"

    id = Column(String, primary_key=True)
    artifact_id = Column(String, ForeignKey("artifacts.id"), nullable=False)
    artifact_version_id = Column(String, nullable=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    source = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ready")
    url = Column(Text, nullable=False)
    visibility = Column(String, nullable=False, default="private")
    auth_token = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(String, primary_key=True)
    artifact_id = Column(String, ForeignKey("artifacts.id"), nullable=False)
    artifact_version_id = Column(String, nullable=False)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    target = Column(String, nullable=False)
    visibility = Column(String, nullable=False, default="private")
    status = Column(String, nullable=False, default="queued")
    stage = Column(String, nullable=False, default="queued")
    url = Column(Text, nullable=True)
    error_summary = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class DeploymentLog(Base):
    __tablename__ = "deployment_logs"

    id = Column(String, primary_key=True)
    deployment_id = Column(String, ForeignKey("deployments.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
    stream = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
