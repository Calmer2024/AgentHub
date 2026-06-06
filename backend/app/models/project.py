from sqlalchemy import Column, DateTime, String, Text
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
    project_type = Column(String, nullable=False, default="existing")
    status = Column(String, nullable=False, default="creating")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    sessions = relationship("Session", back_populates="project")
    artifacts = relationship("Artifact", back_populates="project")
