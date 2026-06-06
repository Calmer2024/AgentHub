"""SharedContext —— DAG 协作中的共享对话流与定向注入。"""


class SharedContext:
    """保存协作共享上下文。

    所有 Agent 读取同一份基础消息；每个任务完成后追加到共享对话流。
    有依赖的后继任务额外收到前驱完整产出的定向注入。
    """

    def __init__(self, base_messages: list[dict]):
        self.messages = [dict(m) for m in base_messages]
        self.agent_outputs: dict[str, str] = {}

    def append_output(
        self, task_name: str, agent_name: str, role: str, content: str,
    ) -> None:
        """记录任务产出，并追加为后续 Agent 可读的 assistant 消息。"""
        if not content:
            return
        self.agent_outputs[task_name] = content
        self.messages.append({
            "role": "assistant",
            "content": f"[{role}] @{agent_name}:\n{content}",
        })

    def get_for_agent(self, depends_on: list[str]) -> list[dict]:
        """返回某个 Agent 的输入消息，包含依赖任务的完整产出注入。"""
        msgs = [dict(m) for m in self.messages]
        for dep in depends_on:
            output = self.agent_outputs.get(dep, "")
            if output:
                msgs.append({
                    "role": "assistant",
                    "content": f"[上一步 ({dep}) 完整产出]\n{output[:3000]}",
                })
        return msgs
