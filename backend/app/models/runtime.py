from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class Sandbox(Base):
    __tablename__ = "sandboxes"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    status = Column(String, nullable=False, default="creating")
    image = Column(String, nullable=False)
    runner_node_id = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    external_id = Column(String, nullable=True)
    region = Column(String, nullable=True)
    resource_limits_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    stopped_at = Column(DateTime, nullable=True)
    disposed_at = Column(DateTime, nullable=True)


class RuntimeRun(Base):
    __tablename__ = "runtime_runs"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agent_configs.id"), nullable=False)
    sandbox_id = Column(String, ForeignKey("sandboxes.id"), nullable=True)
    runtime_mode = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    queued_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    sync_completed_at = Column(DateTime, nullable=True)
    error_summary = Column(Text, nullable=True)


class RuntimeLog(Base):
    __tablename__ = "runtime_logs"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runtime_runs.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
    stream = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class Secret(Base):
    __tablename__ = "secrets"

    id = Column(String, primary_key=True)
    scope = Column(String, nullable=False)
    owner_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    encrypted_value = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class CliCredentialConfig(Base):
    __tablename__ = "cli_credential_configs"
    __table_args__ = (
        UniqueConstraint("scope", "owner_id", "cli_tool", name="uq_cli_credential_scope_owner_tool"),
    )

    id = Column(String, primary_key=True)
    scope = Column(String, nullable=False)
    owner_id = Column(String, nullable=False)
    cli_tool = Column(String, nullable=False)
    provider_type = Column(String, nullable=False)
    provider_id = Column(String, nullable=False)
    provider_name = Column(String, nullable=False)
    base_url = Column(Text, nullable=True)
    model = Column(String, nullable=True)
    auth_env_key = Column(String, nullable=False)
    secret_names_json = Column(Text, nullable=False, default="[]")
    config_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class QuotaUsage(Base):
    __tablename__ = "quota_usages"

    id = Column(String, primary_key=True)
    subject_type = Column(String, nullable=False)
    subject_id = Column(String, nullable=False)
    quota_type = Column(String, nullable=False)
    used = Column(Integer, nullable=False, default=0)
    limit_value = Column(Integer, nullable=False)
    window_started_at = Column(DateTime, nullable=False, default=_utcnow)


class RunnerNode(Base):
    __tablename__ = "runner_nodes"

    id = Column(String, primary_key=True)
    provider = Column(String, nullable=False)
    region = Column(String, nullable=True)
    status = Column(String, nullable=False)
    capacity_json = Column(Text, nullable=False, default="{}")
    last_heartbeat_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class WorkspaceVolume(Base):
    __tablename__ = "workspace_volumes"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    storage_provider = Column(String, nullable=False)
    storage_uri = Column(Text, nullable=False)
    status = Column(String, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
