"""Service 层 Pydantic 模型 —— 跨 Service 和 API 层共享。

字段命名统一使用 camelCase alias，与前端 TypeScript interface 严格对齐。
"""

from datetime import datetime

from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    session_id: str = Field(alias="sessionId")
    role: str = "user"
    content: str
    content_type: str = Field(default="text", alias="contentType")
    parent_message_id: str | None = Field(default=None, alias="parentMessageId")
    metadata: dict | None = None

    model_config = {"populate_by_name": True}


class MessageRead(BaseModel):
    id: str
    session_id: str = Field(alias="sessionId")
    role: str
    content: str
    content_type: str = Field(default="text", alias="contentType")
    agent_name: str | None = Field(default=None, alias="agentName")
    source_type: str = Field(default="agent", alias="sourceType")
    source_id: str | None = Field(default=None, alias="sourceId")
    source_name: str | None = Field(default=None, alias="sourceName")
    parent_message_id: str | None = Field(default=None, alias="parentMessageId")
    is_pinned: bool = Field(default=False, alias="isPinned")
    agent_role: str | None = Field(default=None, alias="agentRole")
    phase: int | None = None
    task_name: str | None = Field(default=None, alias="taskName")
    is_collaborating: bool = Field(default=False, alias="isCollaborating")
    created_at: datetime = Field(alias="createdAt")
    metadata: dict | None = None
    highlight: str | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class SessionCreate(BaseModel):
    title: str = "新对话"
    project_id: str | None = Field(default=None, alias="projectId")
    agent_config_id: str | None = Field(default=None, alias="agentConfigId")
    mode: str = "single"
    agent_config_ids: list[str] | None = Field(default=None, alias="agentConfigIds")

    model_config = {"populate_by_name": True}


class SessionRead(BaseModel):
    id: str
    title: str
    project_id: str | None = Field(default=None, alias="projectId")
    agent_config_id: str | None = Field(default=None, alias="agentConfigId")
    mode: str = "single"
    is_pinned: bool = Field(default=False, alias="isPinned")
    archived_at: datetime | None = Field(default=None, alias="archivedAt")
    unread_count: int = Field(default=0, alias="unreadCount")
    last_read_at: datetime | None = Field(default=None, alias="lastReadAt")
    is_muted: bool = Field(default=False, alias="isMuted")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class SessionUpdate(BaseModel):
    title: str | None = None
    agent_config_id: str | None = Field(default=None, alias="agentConfigId")
    is_pinned: bool | None = Field(default=None, alias="isPinned")
    archived: bool | None = None
    is_muted: bool | None = Field(default=None, alias="isMuted")

    model_config = {"populate_by_name": True}


class ForwardMessagesRequest(BaseModel):
    message_ids: list[str] = Field(alias="messageIds", min_length=1, max_length=20)
    target_session_ids: list[str] = Field(alias="targetSessionIds", min_length=1, max_length=10)

    model_config = {"populate_by_name": True}


class ForwardMessagesResult(BaseModel):
    messages: list[MessageRead]

    model_config = {"populate_by_name": True}


class MemberRead(BaseModel):
    agent_config_id: str = Field(alias="agentConfigId")
    agent_name: str = Field(alias="agentName")
    joined_at: datetime = Field(alias="joinedAt")

    model_config = {"populate_by_name": True}


class GroupMemberCreate(BaseModel):
    agent_config_id: str = Field(alias="agentConfigId")

    model_config = {"populate_by_name": True}


class ChainConfigSchema(BaseModel):
    """链式协作配置 (运行时参数，不持久化)。"""
    chain_name: str | None = Field(default=None, alias="chainName")
    agent_order: list[str] | None = Field(default=None, alias="agentOrder")

    model_config = {"populate_by_name": True}


class ChatRequest(BaseModel):
    """聊天请求 (含可选链式配置)。"""
    content: str
    mentions: list[str] | None = None
    parent_message_id: str | None = Field(default=None, alias="parentMessageId")
    chain_config: ChainConfigSchema | None = Field(default=None, alias="chainConfig")

    model_config = {"populate_by_name": True}


class ProjectCreate(BaseModel):
    name: str
    workspace_path: str | None = Field(default=None, alias="workspacePath")
    folder_token: str | None = Field(default=None, alias="folderToken")
    workspace_mode: str = Field(default="local", alias="workspaceMode")
    team_id: str | None = Field(default=None, alias="teamId")
    template: str | None = None

    model_config = {"populate_by_name": True}


class ProjectUpdate(BaseModel):
    name: str | None = None

    model_config = {"populate_by_name": True}


class ProjectRead(BaseModel):
    id: str
    name: str
    workspace_path: str | None = Field(default=None, alias="workspacePath")
    workspace_mode: str = Field(default="local", alias="workspaceMode")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    team_id: str | None = Field(default=None, alias="teamId")
    status: str
    file_count: int = Field(default=0, alias="fileCount")
    total_size_bytes: int = Field(default=0, alias="totalSizeBytes")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}
