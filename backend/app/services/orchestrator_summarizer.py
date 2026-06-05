"""Orchestrator 中枢总结生成器。"""

import inspect
from collections.abc import AsyncIterator

from ..domain.execution_planner import AgentCall
from .system_llm import SystemLLMUnavailableError, system_llm

ORCHESTRATOR_SOURCE_ID = "orchestrator"
ORCHESTRATOR_SOURCE_NAME = "Orchestrator 中枢"
SUMMARY_CONTENT_TYPE = "orchestrator_summary"

SUMMARY_SYSTEM_PROMPT = """你是 AgentHub 的 Orchestrator 中枢。
你的职责不是再做一个 Agent，而是把项目小队成员的产出整合成最终答复。
要求:
1. 明确综合结论和建议执行顺序。
2. 合并重复内容，指出冲突或遗漏。
3. 保留关键代码、接口、风险和下一步。
4. 不要声称你亲自完成了某个 Agent 的工作。"""


class OrchestratorSummarizer:
    """把多个 Agent 输出整合成一个系统整理消息。"""

    def current_model_config(self) -> dict:
        return {"system_model_provider": "deepseek", "system_model": system_llm.model}

    async def stream_summary(
        self,
        user_goal: str,
        plan_summary: str,
        agent_texts: dict[str, str],
        calls_by_key: dict[str, AgentCall],
    ) -> AsyncIterator[str]:
        if not agent_texts:
            return
        async for token in self._llm_summary(
            user_goal, plan_summary, agent_texts, calls_by_key,
        ):
            yield token

    async def _llm_summary(
        self, user_goal: str, plan_summary: str,
        agent_texts: dict[str, str], calls_by_key: dict[str, AgentCall],
    ) -> AsyncIterator[str]:
        try:
            emitted = False
            stream = system_llm.chat_stream(
                messages=self._messages(user_goal, plan_summary, agent_texts, calls_by_key),
                system_prompt=SUMMARY_SYSTEM_PROMPT,
            )
            if inspect.isawaitable(stream):
                stream = await stream
            async for token in stream:
                emitted = True
                yield token
            if emitted:
                return
        except (SystemLLMUnavailableError, Exception):
            pass
        yield self._fallback_summary(agent_texts, calls_by_key)

    @staticmethod
    def _messages(
        user_goal: str, plan_summary: str,
        agent_texts: dict[str, str], calls_by_key: dict[str, AgentCall],
    ) -> list[dict]:
        parts = [f"用户目标:\n{user_goal}", f"编排说明:\n{plan_summary}"]
        parts.append("Agent 产出:")
        for key, text in agent_texts.items():
            call = calls_by_key.get(key)
            label = f"@{call.agent.name} / {call.role} / {call.task}" if call else key
            parts.append(f"\n---\n{label}\n{text[:5000]}")
        return [{"role": "user", "content": "\n\n".join(parts)}]

    @staticmethod
    def _fallback_summary(
        agent_texts: dict[str, str], calls_by_key: dict[str, AgentCall],
    ) -> str:
        lines = ["## 综合总结", "", "中枢已收集各 Agent 的产出，建议优先按以下顺序整合:"]
        for key, text in agent_texts.items():
            call = calls_by_key.get(key)
            name = call.agent.name if call else key
            role = call.role if call else "assistant"
            first = " ".join(text.strip().split())[:240]
            lines.append(f"- @{name} ({role}): {first}")
        lines.append("")
        lines.append("请以上述产出为基础继续迭代；如存在冲突，应以审查者或综合者的结论优先。")
        return "\n".join(lines)
