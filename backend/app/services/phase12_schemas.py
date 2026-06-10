from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


CommentTarget = Literal["message", "artifact", "deployment"]


class CommentCreate(BaseModel):
    target_type: CommentTarget = Field(alias="targetType")
    target_id: str = Field(alias="targetId")
    body: str

    model_config = {"populate_by_name": True}


class CommentRead(BaseModel):
    id: str
    project_id: str = Field(alias="projectId")
    target_type: str = Field(alias="targetType")
    target_id: str = Field(alias="targetId")
    author_user_id: str = Field(alias="authorUserId")
    body: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class CommentListRead(BaseModel):
    items: list[CommentRead]


class AttachmentRead(BaseModel):
    id: str
    project_id: str = Field(alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")
    filename: str
    mime_type: str = Field(alias="mimeType")
    size_bytes: int = Field(alias="sizeBytes")
    storage_uri: str = Field(alias="storageUri")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class MessageForwardRequest(BaseModel):
    target_session_ids: list[str] = Field(alias="targetSessionIds", min_length=1, max_length=10)
    include_artifacts: bool = Field(default=False, alias="includeArtifacts")

    model_config = {"populate_by_name": True}


class ArtifactReferenceRead(BaseModel):
    id: str
    source_type: str = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId")
    artifact_id: str = Field(alias="artifactId")
    artifact_version_id: str | None = Field(default=None, alias="artifactVersionId")
    relation: str
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class MessageForwardRead(BaseModel):
    messages: list[dict]
    artifact_references: list[ArtifactReferenceRead] = Field(alias="artifactReferences")

    model_config = {"populate_by_name": True}


class NotificationRead(BaseModel):
    id: str
    type: str
    resource_type: str = Field(alias="resourceType")
    resource_id: str = Field(alias="resourceId")
    title: str
    body: str | None = None
    read_at: datetime | None = Field(default=None, alias="readAt")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class NotificationListRead(BaseModel):
    items: list[NotificationRead]


class MobileSessionSummary(BaseModel):
    id: str
    project_id: str | None = Field(default=None, alias="projectId")
    title: str
    unread_count: int = Field(alias="unreadCount")
    latest_message_at: datetime | None = Field(default=None, alias="latestMessageAt")
    pending_approval_count: int = Field(alias="pendingApprovalCount")

    model_config = {"populate_by_name": True}


class MobileApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = None


class RenderedArtifactRead(BaseModel):
    artifact_id: str = Field(alias="artifactId")
    format: str
    render_id: str = Field(alias="renderId")
    content: str
    file_name: str = Field(alias="fileName")
    preview_kind: str = Field(alias="previewKind")
    media_type: str | None = Field(default=None, alias="mediaType")
    raw_url: str | None = Field(default=None, alias="rawUrl")
    download_url: str | None = Field(default=None, alias="downloadUrl")

    model_config = {"populate_by_name": True}


class AgentTemplateSessionCreate(BaseModel):
    seed_prompt: str = Field(alias="seedPrompt")

    model_config = {"populate_by_name": True}


class AgentTemplateSessionRead(BaseModel):
    id: str
    status: str
    draft: dict
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class AgentTemplateFinalize(BaseModel):
    name: str
    engine: str


class GitSyncCreate(BaseModel):
    remote: str
    branch: str
    mode: Literal["pull", "push"]


class GitSyncJobRead(BaseModel):
    id: str
    project_id: str = Field(alias="projectId")
    mode: str
    remote: str
    branch: str
    status: str
    commit_sha: str | None = Field(default=None, alias="commitSha")
    error_summary: str | None = Field(default=None, alias="errorSummary")
    logs: list[str]
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}
