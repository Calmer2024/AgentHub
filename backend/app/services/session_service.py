"""会话服务 —— 封装会话 CRUD 业务逻辑。

从 API 路由中提取，使路由层退化为 thin handler (≤ 30 行)。
"""

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Session as DBSession, AgentConfig, SessionMember, Project
from .schemas import SessionCreate, SessionRead, SessionUpdate, MemberRead
from .project_service import ProjectService


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
        is_group = data.mode == "group" and data.agent_config_ids and len(data.agent_config_ids) >= 2

        session = DBSession(
            id=str(uuid.uuid4()),
            title=data.title,
            project_id=project_id,
            mode="group" if is_group else "single",
        )

        if is_group and data.agent_config_ids:
            session.agent_config_id = data.agent_config_ids[0]
        elif data.agent_config_id:
            session.agent_config_id = data.agent_config_id
        else:
            result = await self.db.execute(
                select(AgentConfig).where(AgentConfig.is_active == True).limit(1)
            )
            default_agent = result.scalars().first()
            session.agent_config_id = default_agent.id if default_agent else None

        self.db.add(session)

        if is_group and data.agent_config_ids:
            for aid in data.agent_config_ids[:5]:
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

    async def _resolve_project_id(self, project_id: str | None) -> str:
        if project_id:
            project = await self.db.get(Project, project_id)
            if not project or project.status == "archived":
                raise ProjectNotFoundError(project_id)
            return project.id
        project = await ProjectService(self.db).ensure_default_project()
        return project.id
