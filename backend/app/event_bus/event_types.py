from enum import Enum


class EventType(str, Enum):
    MESSAGE_CREATED = "message.created"
    MESSAGE_STREAMING = "message.streaming"
    MESSAGE_COMPLETED = "message.completed"
    ORCHESTRATOR_TASK_STARTED = "orchestrator.task.started"
    ORCHESTRATOR_TASK_COMPLETED = "orchestrator.task.completed"
    AGENT_CALL_STARTED = "agent.call.started"
    AGENT_CALL_COMPLETED = "agent.call.completed"
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_UPDATED = "artifact.updated"
