"""Service facade for executing AgentHub CLI wrapper agents."""

from __future__ import annotations

from typing import AsyncIterator

from ..agents.cli_adapters import (
    CliEvent,
    EngineSessionResumePolicy,
    PersistentProcessPolicy,
    get_cli_adapter,
    render_transcript_prompt,
)
from ..domain.skill_registry import SkillRegistry
from ..models import AgentConfig
from .cli_agent_registry import decode_json_list


class CliAgentService:
    """Render chat context and delegate execution to a per-CLI adapter."""

    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self._skills = SkillRegistry()

    async def stream(
        self,
        *,
        agent: AgentConfig,
        session_id: str,
        runtime_session_id: str | None = None,
        workspace_path: str,
        messages: list[dict],
        system_prompt: str,
        engine_session_id: str | None = None,
        engine_session_mode: str = "resume",
        persistent_process: bool = False,
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
        assembled_system_prompt = self._assemble_system_prompt(agent, system_prompt)
        if persistent_process and adapter.supports_persistent_process:
            async for event in adapter.stream_persistent_turn(
                agent=agent,
                session_id=session_id,
                runtime_session_id=runtime_session_id,
                cwd=workspace_path,
                user_prompt=prompt,
                system_prompt=assembled_system_prompt,
                engine_session_id=engine_session_id,
                engine_session_mode=engine_session_mode,
                event_bus=self.event_bus,
            ):
                yield event
            return

        async for event in adapter.stream(
            agent=agent,
            session_id=session_id,
            cwd=workspace_path,
            user_prompt=prompt,
            system_prompt=assembled_system_prompt,
            engine_session_id=engine_session_id,
            engine_session_mode=engine_session_mode,
            event_bus=self.event_bus,
        ):
            yield event

    def supports_engine_session_resume(self, agent: AgentConfig) -> bool:
        return bool(get_cli_adapter(agent.cli_tool).supports_engine_session_resume)

    def engine_session_resume_policy(self, agent: AgentConfig) -> EngineSessionResumePolicy:
        return get_cli_adapter(agent.cli_tool).engine_session_resume_policy

    def supports_persistent_process(self, agent: AgentConfig) -> bool:
        return bool(get_cli_adapter(agent.cli_tool).supports_persistent_process)

    def persistent_process_policy(self, agent: AgentConfig) -> PersistentProcessPolicy:
        return get_cli_adapter(agent.cli_tool).persistent_process_policy

    def _assemble_system_prompt(self, agent: AgentConfig, base_prompt: str) -> str:
        parts: list[str] = [
            (
                "[AgentHub Agent Profile]\n"
                f"当前会话中的用户可见 Agent 名称: {agent.name}\n"
                f"底层 Engine: {agent.cli_tool or 'custom'}\n"
                "Agent 的身份和业务边界由 Agent System Prompt 定义；"
                "Rules 定义长期行为规则；工具集只补充可复用能力。"
                "当用户询问你是什么角色时，回答 Agent Profile 身份，而不是只回答底层 Engine 名称。"
            )
        ]
        if base_prompt.strip():
            parts.append(f"[Agent System Prompt]\n{base_prompt.strip()}")

        rules = str(getattr(agent, "rules", "") or "").strip()
        if rules:
            parts.append(f"[Agent Rules]\n{rules}")

        toolset = decode_json_list(getattr(agent, "toolset", "[]"))
        tag_only_tools: list[str] = []
        for tool_id in toolset:
            skill = self._skills.get(tool_id)
            if skill:
                parts.append(f"[Local Tool: {skill.id}]\n{skill.prompt}")
            else:
                tag_only_tools.append(tool_id)
        if tag_only_tools:
            parts.append(f"[Agent Toolset]\n{', '.join(tag_only_tools)}")

        policy = (agent.context_policy or "workspace_coding").strip()
        if policy:
            parts.append(f"[Context Policy: {policy}]")

        return "\n\n".join(parts)


def render_cli_prompt(messages: list[dict]) -> str:
    """Render normalized chat messages into a plain transcript for CLI stdin."""
    return render_transcript_prompt(messages)
