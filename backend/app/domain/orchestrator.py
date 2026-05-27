import asyncio
from ..models import AgentConfig


class Orchestrator:
    async def route(
        self,
        mentions: list[str] | None,
        member_agents: list[AgentConfig],
    ) -> list[AgentConfig]:
        """决定消息路由到哪些 Agent。member_agents 由调用方从 DB 查询后传入。"""
        if mentions:
            mention_set = set(mentions)
            return [a for a in member_agents if a.id in mention_set]

        return member_agents

    async def coordinate(
        self,
        agents: list[AgentConfig],
        messages: list[dict],
        adapter_factory,
    ) -> list[dict]:
        if not agents:
            return []

        async def invoke(agent: AgentConfig) -> dict | None:
            try:
                adapter = adapter_factory(agent.provider)
                if not adapter or not hasattr(adapter, "chat_stream"):
                    return {"agent_id": agent.id, "agent_name": agent.name, "content": f"[{agent.name} 不可用]", "error": True}
                full = ""
                async for token in adapter.chat_stream(
                    messages=messages,
                    system_prompt=agent.system_prompt,
                    model=agent.model or None,
                ):
                    full += token
                return {"agent_id": agent.id, "agent_name": agent.name, "content": full, "error": False}
            except asyncio.TimeoutError:
                return {"agent_id": agent.id, "agent_name": agent.name, "content": f"[{agent.name} 响应超时]", "error": True}
            except Exception as e:
                return {"agent_id": agent.id, "agent_name": agent.name, "content": f"[{agent.name} 错误: {e}]", "error": True}

        tasks = [asyncio.create_task(invoke(agent)) for agent in agents[:5]]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


orchestrator = Orchestrator()
