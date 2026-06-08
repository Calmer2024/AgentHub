from datetime import datetime

from pydantic import BaseModel, Field


class BuildCreate(BaseModel):
    command: str | None = None
    install_command: str | None = Field(default=None, alias="installCommand")
    artifact_path: str | None = Field(default=None, alias="artifactPath")

    model_config = {"populate_by_name": True}


class BuildQueuedRead(BaseModel):
    build_id: str = Field(alias="buildId")
    status: str

    model_config = {"populate_by_name": True}


class BuildRunRead(BaseModel):
    id: str
    project_id: str = Field(alias="projectId")
    status: str
    command: str
    install_command: str | None = Field(default=None, alias="installCommand")
    artifact_path: str | None = Field(default=None, alias="artifactPath")
    exit_code: int | None = Field(default=None, alias="exitCode")
    error_summary: str | None = Field(default=None, alias="errorSummary")
    created_at: datetime = Field(alias="createdAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class BuildListRead(BaseModel):
    items: list[BuildRunRead]

    model_config = {"populate_by_name": True}


class BuildLogChunkRead(BaseModel):
    sequence: int
    stream: str
    text: str
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class BuildLogsRead(BaseModel):
    chunks: list[BuildLogChunkRead]

    model_config = {"populate_by_name": True}


class ProjectPreviewCreate(BaseModel):
    source: str = "workspace"
    path: str | None = None
    build_id: str | None = Field(default=None, alias="buildId")

    model_config = {"populate_by_name": True}


class ProjectPreviewRead(BaseModel):
    preview_id: str = Field(alias="previewId")
    url: str
    source: str

    model_config = {"populate_by_name": True}


class ContextPackBlockRead(BaseModel):
    type: str
    title: str
    token_estimate: int = Field(alias="tokenEstimate")

    model_config = {"populate_by_name": True}


class ContextPackPreviewRead(BaseModel):
    id: str
    session_id: str = Field(alias="sessionId")
    purpose: str
    blocks: list[ContextPackBlockRead]
    warnings: list[str]

    model_config = {"populate_by_name": True}


class OrchestratorPlanResumeRequest(BaseModel):
    approval_id: str | None = Field(default=None, alias="approvalId")
    message: str | None = None

    model_config = {"populate_by_name": True}


class OrchestratorPlanStepRead(BaseModel):
    id: str
    title: str
    agent_id: str | None = Field(default=None, alias="agentId")
    status: str

    model_config = {"populate_by_name": True}


class OrchestratorPlanRead(BaseModel):
    id: str
    session_id: str = Field(alias="sessionId")
    status: str
    current_step_id: str | None = Field(default=None, alias="currentStepId")
    steps: list[OrchestratorPlanStepRead]

    model_config = {"populate_by_name": True}
