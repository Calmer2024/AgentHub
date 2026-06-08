from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from ..database import Base
from ..core.timezone import china_now


def _utcnow():
    return china_now()


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    workspace_path = Column(String, nullable=False, unique=True)
    workspace_mode = Column(String, nullable=False, default="local")
    workspace_id = Column(String, ForeignKey("workspaces.id", use_alter=True), nullable=True)
    team_id = Column(String, ForeignKey("teams.id"), nullable=True)
    owner_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    project_type = Column(String, nullable=False, default="existing")
    status = Column(String, nullable=False, default="creating")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    sessions = relationship("Session", back_populates="project")
    artifacts = relationship("Artifact", back_populates="project")
    team = relationship("Team", back_populates="projects")
    workspace = relationship("Workspace", foreign_keys=[workspace_id], uselist=False)
