"""TokenEvent —— AgentExecutor 输出的结构化流事件。"""


class TokenEvent:
    """Agent 流式输出的单个事件。"""

    def __init__(self, agent_id: str = "", agent_name: str = "", token: str = "",
                 done: bool = False, message_id: str = "", error: str = "",
                 event_type: str = "token", metadata: dict | None = None):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.token = token
        self.done = done
        self.message_id = message_id
        self.error = error
        self.event_type = event_type
        self.metadata = metadata or {}

    @property
    def is_chain_step(self) -> bool:
        return self.event_type == "chain_step"

    @property
    def is_phase_change(self) -> bool:
        return self.event_type == "phase_change"

    @property
    def is_structured(self) -> bool:
        """非纯 token 的结构化事件。"""
        return self.event_type != "token"

    def to_dict(self) -> dict:
        d = {
            "agentId": self.agent_id,
            "agentName": self.agent_name,
            "token": self.token,
            "done": self.done,
            "messageId": self.message_id,
            "error": self.error,
        }
        if self.event_type != "token":
            d["eventType"] = self.event_type
        if self.metadata:
            d["metadata"] = self.metadata
        return d
