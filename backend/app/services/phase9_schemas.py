"""Phase 9 Cloud Workspace 的 API/Service 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


WorkspaceMode = Literal["local", "cloud"]
TeamRole = Literal["owner", "admin", "member", "viewer"]


class CurrentUserRead(BaseModel):
    id: str
    email: str
    username: str | None = None
    display_name: str = Field(alias="displayName")
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True, "from_attributes": True}


class TeamCreate(BaseModel):
    name: str


class TeamRead(BaseModel):
    id: str
    name: str
    role: TeamRole
    member_count: int = Field(alias="memberCount")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class TeamListRead(BaseModel):
    items: list[TeamRead]


class TeamMemberCreate(BaseModel):
    email: str
    role: TeamRole


class TeamMemberRead(BaseModel):
    id: str
    team_id: str = Field(alias="teamId")
    user_id: str = Field(alias="userId")
    email: str
    display_name: str = Field(alias="displayName")
    role: TeamRole
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class WorkspaceSnapshotRead(BaseModel):
    id: str
    workspace_id: str = Field(alias="workspaceId")
    label: str | None = None
    storage_uri: str = Field(alias="storageUri")
    created_by: str | None = Field(default=None, alias="createdBy")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class WorkspaceImportRead(BaseModel):
    id: str
    workspace_id: str = Field(alias="workspaceId")
    source: Literal["zip", "github"]
    status: str
    detail: str
    metadata: dict = Field(default_factory=dict)
    created_by: str | None = Field(default=None, alias="createdBy")
    created_at: datetime = Field(alias="createdAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")

    model_config = {"populate_by_name": True}


class WorkspaceRestoreRead(BaseModel):
    id: str
    workspace_id: str = Field(alias="workspaceId")
    snapshot_id: str = Field(alias="snapshotId")
    strategy: Literal["replace", "branch"]
    status: str
    created_at: datetime = Field(alias="createdAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")

    model_config = {"populate_by_name": True}


class WorkspaceRead(BaseModel):
    id: str
    project_id: str = Field(alias="projectId")
    provider: str
    status: str
    storage_uri: str = Field(alias="storageUri")
    snapshots: list[WorkspaceSnapshotRead] = Field(default_factory=list)
    imports: list[WorkspaceImportRead] = Field(default_factory=list)
    restores: list[WorkspaceRestoreRead] = Field(default_factory=list)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class WorkspaceSnapshotCreate(BaseModel):
    label: str | None = None


class WorkspaceRestoreCreate(BaseModel):
    strategy: Literal["replace", "branch"]


class WorkspaceRestoreQueuedRead(BaseModel):
    restore_id: str = Field(alias="restoreId")

    model_config = {"populate_by_name": True}


class WorkspaceImportQueuedRead(BaseModel):
    import_id: str = Field(alias="importId")
    status: str

    model_config = {"populate_by_name": True}


class GitHubImportCreate(BaseModel):
    repo_url: str = Field(alias="repoUrl")
    branch: str | None = None

    model_config = {"populate_by_name": True}


class AuditLogRead(BaseModel):
    id: str
    actor_user_id: str | None = Field(default=None, alias="actorUserId")
    team_id: str | None = Field(default=None, alias="teamId")
    project_id: str | None = Field(default=None, alias="projectId")
    action: str
    resource_type: str = Field(alias="resourceType")
    resource_id: str = Field(alias="resourceId")
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class AuditLogListRead(BaseModel):
    items: list[AuditLogRead]
