"""会话服务 —— 封装会话 CRUD 业务逻辑。

从 API 路由中提取，使路由层退化为 thin handler (≤ 30 行)。
"""

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Session as DBSession, AgentConfig, SessionMember, Message, Project
from .schemas import SessionCreate, SessionRead, SessionUpdate, MemberRead
from .project_service import ProjectService
from .system_llm import SystemLLMUnavailableError, system_llm


class SessionNotFoundError(Exception):
    pass


class AgentNotFoundError(Exception):
    pass


class ProjectNotFoundError(Exception):
    pass


class SessionService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(self, data: SessionCreate) -> SessionRead:
        project_id = await self._resolve_project_id(data.project_id)
        group_agent_ids = await self._with_default_orchestrator(data.agent_config_ids or [])
        is_group = data.mode == "group" and len(group_agent_ids) >= 2

        session = DBSession(
            id=str(uuid.uuid4()),
            title=data.title,
            project_id=project_id,
            mode="group" if is_group else "single",
        )

        if is_group and group_agent_ids:
            session.agent_config_id = group_agent_ids[0]
        elif data.agent_config_id:
            session.agent_config_id = data.agent_config_id
        else:
            result = await self.db.execute(
                select(AgentConfig).where(AgentConfig.is_active == True).limit(1)
            )
            default_agent = result.scalars().first()
            session.agent_config_id = default_agent.id if default_agent else None

        self.db.add(session)

        if is_group and group_agent_ids:
            for aid in group_agent_ids[:6]:
                self.db.add(SessionMember(session_id=session.id, agent_config_id=aid))

        await self.db.commit()
        await self.db.refresh(session)
        return SessionRead.model_validate(session)

    async def list_sessions(self, project_id: str | None = None) -> list[SessionRead]:
        stmt = select(DBSession).where(DBSession.is_active == "1")
        if project_id is not None:
            stmt = stmt.where(DBSession.project_id == project_id)
        stmt = stmt.order_by(DBSession.updated_at.desc())
        result = await self.db.execute(stmt)
        sessions = result.scalars().all()
        return [SessionRead.model_validate(s) for s in sessions]

    async def get_session(self, session_id: str) -> SessionRead | None:
        session = await self.db.get(DBSession, session_id)
        if not session:
            return None
        return SessionRead.model_validate(session)

    async def update_session(self, session_id: str, data: SessionUpdate) -> SessionRead:
        session = await self.db.get(DBSession, session_id)
        if not session:
            raise SessionNotFoundError(session_id)

        if data.title is not None:
            session.title = data.title
        if data.agent_config_id is not None:
            agent = await self.db.get(AgentConfig, data.agent_config_id)
            if not agent:
                raise AgentNotFoundError(data.agent_config_id)
            session.agent_config_id = data.agent_config_id

        await self.db.commit()
        await self.db.refresh(session)
        return SessionRead.model_validate(session)

    async def delete_session(self, session_id: str) -> bool:
        session = await self.db.get(DBSession, session_id)
        if not session:
            return False
        session.is_active = "0"
        await self.db.commit()
        return True

    async def get_members(self, session_id: str) -> list[MemberRead]:
        result = await self.db.execute(
            select(SessionMember, AgentConfig)
            .join(AgentConfig, SessionMember.agent_config_id == AgentConfig.id)
            .where(SessionMember.session_id == session_id)
        )
        members: list[MemberRead] = []
        for sm, agent in result.all():
            members.append(MemberRead(
                agent_config_id=sm.agent_config_id,
                agent_name=agent.name,
                joined_at=sm.joined_at,
            ))
        return members

    async def add_member(self, session_id: str, agent_config_id: str) -> None:
        self.db.add(SessionMember(session_id=session_id, agent_config_id=agent_config_id))
        await self.db.commit()

    async def get_workspace_path(self, session_id: str) -> str:
        return await ProjectService(self.db).get_workspace_path_for_session(session_id)

    async def generate_title(self, session_id: str) -> str:
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(3)
        )
        msgs = list(result.scalars().all())
        if not msgs:
            raise ValueError("无消息可总结")

        session = await self.db.get(DBSession, session_id)
        if not session:
            raise ValueError("会话不存在")

        history = [{"role": m.role, "content": m.content} for m in reversed(msgs)]
        history.append({
            "role": "user",
            "content": "请用不超过10个字总结以上对话内容，只输出总结文本。",
        })

        title = ""
        try:
            stream = system_llm.chat_stream(
                messages=history,
                system_prompt="你是一个标题生成器。",
            )
            async for token in stream:
                title += token
        except SystemLLMUnavailableError as exc:
            raise ValueError(str(exc))

        session.title = title.strip()[:20] or "新对话"
        await self.db.commit()
        await self.db.refresh(session)
        return session.title

    async def _resolve_project_id(self, project_id: str | None) -> str:
        if project_id:
            project = await self.db.get(Project, project_id)
            if not project or project.status == "archived":
                raise ProjectNotFoundError(project_id)
            return project.id
        project = await ProjectService(self.db).ensure_default_project()
        return project.id

    async def _with_default_orchestrator(self, agent_ids: list[str]) -> list[str]:
        result = []
        seen: set[str] = set()
        for agent_id in agent_ids:
            if agent_id and agent_id not in seen:
                result.append(agent_id)
                seen.add(agent_id)

        row = await self.db.execute(
            select(AgentConfig).where(
                AgentConfig.primary_skill == "orchestrator_planner",
                AgentConfig.is_active == True,
            ).limit(1)
        )
        orchestrator = row.scalars().first()
        if orchestrator and orchestrator.id not in seen:
            result.append(orchestrator.id)
        return result
