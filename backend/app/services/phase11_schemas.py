from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


PreviewSource = Literal["static", "build", "dev_server"]
PreviewStatus = Literal["creating", "ready", "expired", "revoked", "failed"]
DeliveryVisibility = Literal["public", "team", "private"]
DeploymentTarget = Literal["static_hosting", "third_party"]
DeploymentStatus = Literal["queued", "running", "published", "failed", "rolled_back"]
DeploymentStage = Literal["queued", "install", "build", "upload", "publish", "verify"]


class PreviewCreate(BaseModel):
    source: str = "static"
    artifact_version_id: str | None = Field(default=None, alias="artifactVersionId")
    ttl_seconds: int | None = Field(default=None, alias="ttlSeconds")
    visibility: str = "private"

    model_config = {"populate_by_name": True}


class PreviewSessionRead(BaseModel):
    id: str
    artifact_id: str = Field(alias="artifactId")
    artifact_version_id: str | None = Field(default=None, alias="artifactVersionId")
    workspace_id: str = Field(alias="workspaceId")
    source: str
    status: str
    url: str
    visibility: str
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class PreviewRevokeRequest(BaseModel):
    reason: str | None = None


class PreviewRevokeRead(BaseModel):
    status: str


class DeploymentCreate(BaseModel):
    artifact_id: str = Field(alias="artifactId")
    artifact_version_id: str = Field(alias="artifactVersionId")
    target: str = "static_hosting"
    visibility: str = "private"

    model_config = {"populate_by_name": True}


class DeploymentRead(BaseModel):
    id: str
    artifact_id: str = Field(alias="artifactId")
    artifact_version_id: str = Field(alias="artifactVersionId")
    project_id: str = Field(alias="projectId")
    target: str
    visibility: str
    status: str
    stage: str
    url: str | None = None
    error_summary: str | None = Field(default=None, alias="errorSummary")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class DeploymentLogsRead(BaseModel):
    chunks: list["DeploymentLogChunkRead"]

    model_config = {"populate_by_name": True}


class DeploymentLogChunkRead(BaseModel):
    sequence: int
    stream: str
    text: str
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class DeploymentRetryRequest(BaseModel):
    from_stage: str | None = Field(default=None, alias="fromStage")

    model_config = {"populate_by_name": True}


class DeploymentRollbackRequest(BaseModel):
    target_deployment_id: str = Field(alias="targetDeploymentId")

    model_config = {"populate_by_name": True}
