import json

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
    target_id = Column(String, ForeignKey("deployment_targets.id"), nullable=True)
    active_release_id = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    target = Column(String, nullable=False)
    visibility = Column(String, nullable=False, default="private")
    status = Column(String, nullable=False, default="queued")
    stage = Column(String, nullable=False, default="queued")
    url = Column(Text, nullable=True)
    bundle_uri = Column(Text, nullable=True)
    provider_metadata_json = Column(Text, nullable=False, default="{}")
    error_summary = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    @property
    def provider_metadata(self) -> dict:
        try:
            value = json.loads(self.provider_metadata_json or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


class DeploymentTarget(Base):
    __tablename__ = "deployment_targets"

    id = Column(String, primary_key=True)
    scope = Column(String, nullable=False)
    owner_id = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    name = Column(String, nullable=False)
    config_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="active")
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    @property
    def config(self) -> dict:
        try:
            value = json.loads(self.config_json or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


class DeploymentRelease(Base):
    __tablename__ = "deployment_releases"

    id = Column(String, primary_key=True)
    deployment_id = Column(String, ForeignKey("deployments.id"), nullable=False)
    artifact_id = Column(String, ForeignKey("artifacts.id"), nullable=False)
    artifact_version_id = Column(String, nullable=False)
    target_id = Column(String, ForeignKey("deployment_targets.id"), nullable=False)
    bundle_uri = Column(Text, nullable=False)
    public_url = Column(Text, nullable=True)
    status = Column(String, nullable=False)
    provider_metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    @property
    def provider_metadata(self) -> dict:
        try:
            value = json.loads(self.provider_metadata_json or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


class DeploymentLog(Base):
    __tablename__ = "deployment_logs"

    id = Column(String, primary_key=True)
    deployment_id = Column(String, ForeignKey("deployments.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
    stream = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
