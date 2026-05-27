import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SessionMember, AgentConfig


class Orchestrator:
    async def route(
        self,
        session_id: str,
        mentions: list[str] | None,
        db: AsyncSession,
    ) -> list[AgentConfig]:
        if mentions:
            agents = []
            for agent_id in mentions:
                agent = await db.get(AgentConfig, agent_id)
                if agent and agent.is_active:
                    agents.append(agent)
            return agents

        result = await db.execute(
            select(AgentConfig).join(
                SessionMember, SessionMember.agent_config_id == AgentConfig.id
            ).where(
                SessionMember.session_id == session_id,
                AgentConfig.is_active == True,
            )
        )
        return list(result.scalars().all())

    async def coordinate(
        self,
        session_id: str,
        messages: list[dict],
        db: AsyncSession,
        adapter_factory,
    ) -> list[dict]:
        agents = await self.route(session_id, mentions=None, db=db)
        if not agents:
            return []

        async def invoke(agent: AgentConfig) -> dict | None:
            try:
                adapter = adapter_factory(agent.provider)
                if not adapter or not hasattr(adapter, 'chat_stream'):
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
