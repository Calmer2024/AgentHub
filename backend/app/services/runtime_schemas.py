from datetime import datetime

from pydantic import BaseModel, Field


class RunRead(BaseModel):
    id: str
    session_id: str = Field(alias="sessionId")
    project_id: str | None = Field(default=None, alias="projectId")
    mode: str
    status: str
    current_message_id: str | None = Field(default=None, alias="currentMessageId")
    started_at: datetime = Field(alias="startedAt")
    updated_at: datetime = Field(alias="updatedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    cancel_reason: str | None = Field(default=None, alias="cancelReason")
    metadata: dict | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class TaskRead(BaseModel):
    id: str
    run_id: str = Field(alias="runId")
    session_id: str = Field(alias="sessionId")
    agent_id: str | None = Field(default=None, alias="agentId")
    message_id: str | None = Field(default=None, alias="messageId")
    name: str
    role: str | None = None
    phase: int | None = None
    status: str
    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    metadata: dict | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class ProcessRead(BaseModel):
    id: str
    run_id: str = Field(alias="runId")
    task_id: str | None = Field(default=None, alias="taskId")
    session_id: str = Field(alias="sessionId")
    agent_id: str | None = Field(default=None, alias="agentId")
    message_id: str | None = Field(default=None, alias="messageId")
    process_id: str = Field(alias="processId")
    pid: int | None = None
    executable: str | None = None
    cwd: str | None = None
    status: str
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    exit_code: int | None = Field(default=None, alias="exitCode")

    model_config = {"from_attributes": True, "populate_by_name": True}


class ApprovalCheckpointRead(BaseModel):
    id: str
    run_id: str = Field(alias="runId")
    task_id: str = Field(alias="taskId")
    session_id: str = Field(alias="sessionId")
    message_id: str | None = Field(default=None, alias="messageId")
    artifact_id: str | None = Field(default=None, alias="artifactId")
    artifact_version: int | None = Field(default=None, alias="artifactVersion")
    title: str
    summary: str
    status: str
    reason: str | None = None
    created_at: datetime = Field(alias="createdAt")
    decided_at: datetime | None = Field(default=None, alias="decidedAt")
    metadata: dict | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}
