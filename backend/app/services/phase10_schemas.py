"""Phase 10 Sandbox Runner 与云端 Agent Runtime 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RuntimeMode = Literal["local", "cloud"]
SandboxStatus = Literal[
    "creating",
    "provisioning",
    "ready",
    "running",
    "syncing",
    "stopping",
    "stopped",
    "failed",
    "disposed",
]
RuntimeRunStatus = Literal[
    "queued",
    "running",
    "waiting_input",
    "syncing",
    "cancelling",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
]
SecretScope = Literal["user", "team", "project"]


class SandboxCreate(BaseModel):
    workspace_id: str = Field(alias="workspaceId")
    image: str = "agenthub/default-cli:phase10"
    ttl_seconds: int | None = Field(default=None, alias="ttlSeconds")

    model_config = {"populate_by_name": True}


class SandboxRead(BaseModel):
    id: str
    workspace_id: str = Field(alias="workspaceId")
    status: str
    image: str
    runner_node_id: str | None = Field(default=None, alias="runnerNodeId")
    provider: str | None = None
    external_id: str | None = Field(default=None, alias="externalId")
    region: str | None = None
    resource_limits: dict = Field(default_factory=dict, alias="resourceLimits")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    stopped_at: datetime | None = Field(default=None, alias="stoppedAt")
    disposed_at: datetime | None = Field(default=None, alias="disposedAt")

    model_config = {"populate_by_name": True, "from_attributes": True}


class SandboxStopRequest(BaseModel):
    reason: str | None = None


class SandboxStopRead(BaseModel):
    id: str
    status: str


class SessionRunCreate(BaseModel):
    agent_id: str = Field(alias="agentId")
    message_id: str | None = Field(default=None, alias="messageId")
    content: str | None = None
    runtime: RuntimeMode = "local"

    model_config = {"populate_by_name": True}


class SessionRunQueuedRead(BaseModel):
    run_id: str = Field(alias="runId")
    sandbox_id: str | None = Field(default=None, alias="sandboxId")
    status: str
    runtime: RuntimeMode

    model_config = {"populate_by_name": True}


class RuntimeLogChunkRead(BaseModel):
    sequence: int
    stream: str
    text: str
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class RuntimeLogsRead(BaseModel):
    run_id: str = Field(alias="runId")
    chunks: list[RuntimeLogChunkRead]

    model_config = {"populate_by_name": True}


class SecretCreate(BaseModel):
    name: str
    value: str
    scope: SecretScope = "user"
    owner_id: str | None = Field(default=None, alias="ownerId")

    model_config = {"populate_by_name": True}


class SecretRefRead(BaseModel):
    id: str
    name: str
    scope: str
    owner_id: str = Field(alias="ownerId")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class QuotaSummaryRead(BaseModel):
    subject_type: str = Field(alias="subjectType")
    subject_id: str = Field(alias="subjectId")
    concurrent_runs_limit: int = Field(alias="concurrentRunsLimit")
    concurrent_runs_used: int = Field(alias="concurrentRunsUsed")
    runtime_seconds_limit: int = Field(alias="runtimeSecondsLimit")
    memory_mb_limit: int = Field(alias="memoryMbLimit")
    disk_mb_limit: int = Field(alias="diskMbLimit")
    network: str

    model_config = {"populate_by_name": True}


class RuntimeImageRead(BaseModel):
    id: str
    label: str
    image: str
    provider: str
    default: bool = False
    tools: list[str] = Field(default_factory=list)
    created_at: datetime | None = Field(default=None, alias="createdAt")

    model_config = {"populate_by_name": True}


class RuntimeImageListRead(BaseModel):
    items: list[RuntimeImageRead]


class RunnerNodeRead(BaseModel):
    id: str
    provider: str
    region: str | None = None
    status: str
    capacity: dict = Field(default_factory=dict)
    last_heartbeat_at: datetime | None = Field(default=None, alias="lastHeartbeatAt")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class RunnerNodeListRead(BaseModel):
    items: list[RunnerNodeRead]
