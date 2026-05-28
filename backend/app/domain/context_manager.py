"""ContextManager —— Token 预算管理与 Prompt 组装。

Domain 层纯逻辑，零 FastAPI/SQLAlchemy 依赖。
"""

from dataclasses import dataclass, field


@dataclass
class PromptAssemblyInput:
    session_id: str
    system_prompt: str
    messages: list[dict]
    pinned_message_ids: list[str] = field(default_factory=list)
    max_tokens: int = 100_000
    reserve_tokens: int = 4096


@dataclass
class PromptAssemblyOutput:
    assembled_messages: list[dict]
    total_tokens: int
    truncated: bool
    pinned_included: list[str]


class ContextManager:
    """Token 预算管理器。

    策略：
    1. System Prompt 固定在最前
    2. Pin 消息按时间排序插入（最多保留 max_tokens * 0.5 给 pin）
    3. 非 Pin 消息按 FIFO 从最早开始移除
    4. 预留 reserve_tokens 给本次回复
    """

    # 粗略 token 估算：中文约 1.5 字符/token，英文约 4 字符/token
    CHARS_PER_TOKEN = 3.5

    def estimate_tokens(self, messages: list[dict]) -> int:
        total = 0
        for m in messages:
            content = m.get("content", "")
            total += max(1, len(content) / self.CHARS_PER_TOKEN)
        return int(total)

    def assemble(self, input: PromptAssemblyInput) -> PromptAssemblyOutput:
        available = input.max_tokens - input.reserve_tokens
        if available <= 0:
            return PromptAssemblyOutput(
                assembled_messages=[{"role": "system", "content": input.system_prompt}],
                total_tokens=0,
                truncated=True,
                pinned_included=[],
            )

        # 分类消息
        pinned = []
        normal = []
        pin_ids = set(input.pinned_message_ids)
        for m in input.messages:
            if m.get("id") in pin_ids:
                pinned.append(m)
            else:
                normal.append(m)

        # Pin 消息按时间排序（假设有 created_at 或保持原序）
        pinned_budget = int(available * 0.5)

        result = []
        total_tokens = 0
        pinned_included: list[str] = []

        # System prompt
        sys_tokens = self.estimate_tokens([{"role": "system", "content": input.system_prompt}])
        total_tokens += sys_tokens

        # Pin 消息（保留最近的消息优先）
        for m in reversed(pinned):
            t = self.estimate_tokens([m])
            if total_tokens + t > pinned_budget:
                break
            result.insert(0, m)
            total_tokens += t
            pinned_included.append(m.get("id", ""))

        # 非 Pin 消息按 FIFO 从最近开始填充
        truncated = False
        for m in reversed(normal):
            t = self.estimate_tokens([m])
            if total_tokens + t > available:
                truncated = True
                break
            result.insert(0, m)
            total_tokens += t

        # 插入 system prompt
        result.insert(0, {"role": "system", "content": input.system_prompt})

        return PromptAssemblyOutput(
            assembled_messages=result,
            total_tokens=total_tokens,
            truncated=truncated,
            pinned_included=pinned_included,
        )
