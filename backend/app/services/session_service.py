"""会话服务 —— 封装会话 CRUD 业务逻辑。

从 API 路由中提取，使路由层退化为 thin handler (≤ 30 行)。
"""

import json
import uuid
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Session as DBSession, AgentConfig, SessionMember, Project, Message as DBMessage
from .message_service_sqlalchemy import _reference_snapshot, message_to_read
from .schemas import (
    ForwardMessagesRequest,
    ForwardMessagesResult,
    SessionCreate,
    SessionRead,
    SessionUpdate,
    MemberRead,
)
from .project_service import ProjectService
from ..core.timezone import china_now


class SessionNotFoundError(Exception):
    pass


class AgentNotFoundError(Exception):
    pass


class ProjectNotFoundError(Exception):
    pass


class MessageNotForwardableError(Exception):
    pass


MAX_GROUP_AGENTS = 12


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
            for aid in group_agent_ids[:MAX_GROUP_AGENTS]:
                self.db.add(SessionMember(session_id=session.id, agent_config_id=aid))

        await self.db.commit()
        await self.db.refresh(session)
        return SessionRead.model_validate(session)

    async def list_sessions(self, project_id: str | None = None, include_archived: bool = False) -> list[SessionRead]:
        stmt = select(DBSession).where(DBSession.is_active == "1")
        if not include_archived:
            stmt = stmt.where(DBSession.archived_at.is_(None))
        if project_id is not None:
            stmt = stmt.where(DBSession.project_id == project_id)
        stmt = stmt.order_by(desc(DBSession.is_pinned), DBSession.updated_at.desc())
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
        if data.is_pinned is not None:
            session.is_pinned = "1" if data.is_pinned else "0"
        if data.archived is not None:
            session.archived_at = china_now() if data.archived else None
        if data.is_muted is not None:
            session.is_muted = "1" if data.is_muted else "0"

        await self.db.commit()
        await self.db.refresh(session)
        return SessionRead.model_validate(session)

    async def mark_read(self, session_id: str) -> SessionRead:
        session = await self.db.get(DBSession, session_id)
        if not session:
            raise SessionNotFoundError(session_id)
        session.unread_count = 0
        session.last_read_at = china_now()
        await self.db.commit()
        await self.db.refresh(session)
        return SessionRead.model_validate(session)

    async def forward_messages(self, data: ForwardMessagesRequest) -> ForwardMessagesResult:
        source_messages = await self._load_forward_source_messages(data.message_ids)
        target_sessions = await self._load_forward_target_sessions(data.target_session_ids)
        if not source_messages:
            raise MessageNotForwardableError("no messages to forward")

        created: list[DBMessage] = []
        now = china_now()
        for target in target_sessions:
            for source in source_messages:
                forwarded = self._forwarded_message(target.id, source, now)
                self.db.add(forwarded)
                created.append(forwarded)
            target.updated_at = now
            target.last_read_at = now

        await self.db.commit()
        for message in created:
            await self.db.refresh(message)
        return ForwardMessagesResult(messages=[message_to_read(message) for message in created])

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

    @staticmethod
    def increment_unread(session: DBSession, amount: int = 1) -> None:
        session.unread_count = max(0, int(session.unread_count or 0) + amount)

    @staticmethod
    def clear_unread(session: DBSession) -> None:
        session.unread_count = 0
        session.last_read_at = china_now()

    async def _load_forward_source_messages(self, message_ids: list[str]) -> list[DBMessage]:
        unique_ids = list(dict.fromkeys(message_ids))
        result = await self.db.execute(select(DBMessage).where(DBMessage.id.in_(unique_ids)))
        by_id = {message.id: message for message in result.scalars().all()}
        missing = [message_id for message_id in unique_ids if message_id not in by_id]
        if missing:
            raise MessageNotForwardableError(f"message not found: {missing[0]}")
        return [by_id[message_id] for message_id in unique_ids]

    async def _load_forward_target_sessions(self, session_ids: list[str]) -> list[DBSession]:
        unique_ids = list(dict.fromkeys(session_ids))
        result = await self.db.execute(
            select(DBSession).where(DBSession.id.in_(unique_ids), DBSession.is_active == "1")
        )
        by_id = {session.id: session for session in result.scalars().all()}
        missing = [session_id for session_id in unique_ids if session_id not in by_id]
        if missing:
            raise SessionNotFoundError(missing[0])
        return [by_id[session_id] for session_id in unique_ids]

    @staticmethod
    def _forwarded_message(target_session_id: str, source: DBMessage, created_at) -> DBMessage:
        snapshot = _reference_snapshot(source)
        source_name = snapshot.get("sourceName") or snapshot.get("agentName") or (
            "用户" if source.role == "user" else "AI"
        )
        content = f"转发自 {source_name}：\n\n{source.content}"
        metadata = {
            "forwarded": True,
            "forwardSource": snapshot,
        }
        return DBMessage(
            id=str(uuid.uuid4()),
            session_id=target_session_id,
            role="user",
            content=content,
            content_type=getattr(source, "content_type", "text") or "text",
            source_type="user",
            source_name="用户",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            created_at=created_at,
        )

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
