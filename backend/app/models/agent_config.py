from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text

from ..database import Base
from ..core.timezone import china_now


def _utcnow():
    return china_now()


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(String, primary_key=True)
    owner_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False, default="")
    system_prompt = Column(String, nullable=False, default="")
    rules = Column(Text, nullable=False, default="")
    agent_type = Column(String, nullable=False, default="cli_wrapper")
    cli_tool = Column(String, nullable=False, default="custom")
    executable = Column(String, nullable=True)
    init_args = Column(Text, nullable=False, default="[]")
    env_vars = Column(Text, nullable=False, default="{}")
    primary_skill = Column(String, nullable=False, default="general_coding")
    auxiliary_skills = Column(Text, nullable=False, default="[]")
    toolset = Column(Text, nullable=False, default="[]")
    context_policy = Column(String, nullable=False, default="workspace_coding")
    avatar = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
