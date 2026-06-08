from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    team_id = Column(String, ForeignKey("teams.id"), nullable=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
