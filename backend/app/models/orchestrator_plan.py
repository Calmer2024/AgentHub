from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class OrchestratorPlanRecord(Base):
    __tablename__ = "orchestrator_plans"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    status = Column(String, nullable=False, default="draft")
    steps_json = Column(Text, nullable=False, default="[]")
    normalized_plan_json = Column(Text, nullable=False, default="{}")
    execution_id = Column(String, nullable=True)
    execution_snapshot_json = Column(Text, nullable=False, default="{}")
    agent_scope_json = Column(Text, nullable=False, default="[]")
    orchestrator_agent_id = Column(String, ForeignKey("agent_configs.id"), nullable=True)
    current_step_id = Column(String, nullable=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
