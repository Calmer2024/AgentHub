"""Service facade for executing AgentHub CLI wrapper agents."""

from __future__ import annotations

from typing import AsyncIterator

from ..agents.cli_adapters import CliEvent, get_cli_adapter, render_transcript_prompt
from ..models import AgentConfig


class CliAgentService:
    """Render chat context and delegate execution to a per-CLI adapter."""

    def __init__(self, event_bus=None):
        self.event_bus = event_bus

    async def stream(
        self,
        *,
        agent: AgentConfig,
        session_id: str,
        workspace_path: str,
        messages: list[dict],
        system_prompt: str,
    ) -> AsyncIterator[CliEvent]:
        if (agent.agent_type or "cli_wrapper") != "cli_wrapper":
            yield CliEvent(
                "error",
                "",
                error=f"Agent {agent.name} 不是 CLI Wrapper 类型，不能作为私聊执行 Agent。",
            )
            return

        adapter = get_cli_adapter(agent.cli_tool)
        prompt = adapter.render_prompt_messages(messages)
        async for event in adapter.stream(
            agent=agent,
            session_id=session_id,
            cwd=workspace_path,
            user_prompt=prompt,
            system_prompt=system_prompt,
            event_bus=self.event_bus,
        ):
            yield event


def render_cli_prompt(messages: list[dict]) -> str:
    """Render normalized chat messages into a plain transcript for CLI stdin."""
    return render_transcript_prompt(messages)
