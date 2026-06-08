from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    provider = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ready")
    storage_uri = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", foreign_keys=[project_id])
    snapshots = relationship("WorkspaceSnapshot", back_populates="workspace", cascade="all, delete-orphan")
    imports = relationship("WorkspaceImport", back_populates="workspace", cascade="all, delete-orphan")
    restores = relationship("WorkspaceRestore", back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceSnapshot(Base):
    __tablename__ = "workspace_snapshots"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    label = Column(String, nullable=True)
    storage_uri = Column(Text, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    workspace = relationship("Workspace", back_populates="snapshots")


class WorkspaceImport(Base):
    __tablename__ = "workspace_imports"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    source = Column(String, nullable=False)
    status = Column(String, nullable=False)
    detail = Column(Text, nullable=False, default="")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)

    workspace = relationship("Workspace", back_populates="imports")


class WorkspaceRestore(Base):
    __tablename__ = "workspace_restores"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    snapshot_id = Column(String, ForeignKey("workspace_snapshots.id"), nullable=False)
    strategy = Column(String, nullable=False)
    status = Column(String, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)

    workspace = relationship("Workspace", back_populates="restores")
