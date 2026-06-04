from enum import Enum


class EventType(str, Enum):
    MESSAGE_CREATED = "message.created"
    MESSAGE_STREAMING = "message.streaming"
    MESSAGE_COMPLETED = "message.completed"
    ORCHESTRATOR_TASK_STARTED = "orchestrator.task.started"
    ORCHESTRATOR_TASK_COMPLETED = "orchestrator.task.completed"
    AGENT_CALL_STARTED = "agent.call.started"
    AGENT_CALL_COMPLETED = "agent.call.completed"
    PROJECT_CREATED = "project.created"
    WORKSPACE_FILE_CHANGED = "workspace.file_changed"
    WORKSPACE_DIFF_READY = "workspace.diff_ready"
    PREVIEW_READY = "preview.ready"
    BUILD_STARTED = "build.started"
    BUILD_LOG = "build.log"
    BUILD_COMPLETED = "build.completed"
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_UPDATED = "artifact.updated"
