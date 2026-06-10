from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field


PreviewSource = Literal["static", "build", "dev_server"]
PreviewStatus = Literal["creating", "ready", "expired", "revoked", "failed"]
DeliveryVisibility = Literal["public", "team", "private"]
DeploymentTarget = Literal["static_hosting", "third_party"]
DeploymentStatus = Literal["queued", "running", "published", "failed", "rolled_back"]
DeploymentStage = Literal["queued", "install", "build", "package", "upload", "publish", "verify"]


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
    target_id: str | None = Field(default=None, alias="targetId")
    visibility: str = "private"

    model_config = {"populate_by_name": True}


class DeploymentRead(BaseModel):
    id: str
    artifact_id: str = Field(alias="artifactId")
    artifact_version_id: str = Field(alias="artifactVersionId")
    project_id: str = Field(alias="projectId")
    target_id: str | None = Field(default=None, alias="targetId")
    active_release_id: str | None = Field(default=None, alias="activeReleaseId")
    provider: str | None = None
    target: str
    visibility: str
    status: str
    stage: str
    url: str | None = None
    bundle_uri: str | None = Field(default=None, alias="bundleUri")
    provider_metadata: dict[str, Any] = Field(default_factory=dict, alias="providerMetadata")
    error_summary: str | None = Field(default=None, alias="errorSummary")
    published_at: datetime | None = Field(default=None, alias="publishedAt")
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


class DeploymentProviderRead(BaseModel):
    id: str
    name: str
    kind: str
    capabilities: list[str]
    status: str
    public_base_url: str = Field(alias="publicBaseUrl")
    requires_secret: bool = Field(default=False, alias="requiresSecret")

    model_config = {"populate_by_name": True}


class DeploymentProviderListRead(BaseModel):
    items: list[DeploymentProviderRead]

    model_config = {"populate_by_name": True}


class DeploymentTargetCreate(BaseModel):
    name: str
    provider: str = "static_site"
    scope: str = "user"
    owner_id: str | None = Field(default=None, alias="ownerId")
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class DeploymentTargetRead(BaseModel):
    id: str
    scope: str
    owner_id: str = Field(alias="ownerId")
    provider: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class DeploymentTargetListRead(BaseModel):
    items: list[DeploymentTargetRead]

    model_config = {"populate_by_name": True}
