"""单个 Agent CLI 调用契约。"""

from dataclasses import dataclass, field

from .agent_profile import AgentProfileSnapshot


@dataclass
class AgentCall:
    """一次直接 Agent 调用；多 Agent 依赖由 CollaborationScheduler 管理。"""

    agent: AgentProfileSnapshot
    task: str = "direct turn"
    role: str = "worker"
    input_messages: list[dict] = field(default_factory=list)
    role_prompt_override: str | None = None
    depends_on: list[str] = field(default_factory=list)
    phase: int = 0
