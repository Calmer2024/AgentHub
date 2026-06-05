from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text

from ..database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False, default="")
    system_prompt = Column(String, nullable=False, default="")
    agent_type = Column(String, nullable=False, default="cli_wrapper")
    cli_tool = Column(String, nullable=False, default="custom")
    executable = Column(String, nullable=True)
    init_args = Column(Text, nullable=False, default="[]")
    env_vars = Column(Text, nullable=False, default="{}")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
