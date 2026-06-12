"""Phase 9 团队与 RBAC 服务。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..event_bus.event_types import EventType
from ..models import Project, Team, TeamMember, User
from .audit_service import AuditService
from .auth_service import AuthService
from .phase9_schemas import TeamMemberRead, TeamRead

TeamRole = Literal["owner", "admin", "member", "viewer"]
VALID_ROLES = {"owner", "admin", "member", "viewer"}
PROJECT_WRITER_ROLES = {"owner", "admin", "member"}
TEAM_ADMIN_ROLES = {"owner", "admin"}


class TeamNotFoundError(ValueError):
    pass


class TeamConflictError(ValueError):
    pass


class TeamValidationError(ValueError):
    pass


class PermissionDeniedError(PermissionError):
    pass


class TeamService:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus
        self.audit = AuditService(db, event_bus=event_bus)
        self.auth = AuthService(db)

    async def list_teams(self, actor: User) -> list[TeamRead]:
        result = await self.db.execute(
            select(TeamMember, Team)
            .join(Team, Team.id == TeamMember.team_id)
            .where(TeamMember.user_id == actor.id)
            .order_by(Team.created_at.desc())
        )
        items: list[TeamRead] = []
        for member, team in result.all():
            count_result = await self.db.execute(
                select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id)
            )
            items.append(TeamRead(
                id=team.id,
                name=team.name,
                role=member.role,
                member_count=int(count_result.scalar() or 0),
                created_at=team.created_at,
            ))
        return items

    async def create_team(self, name: str, actor: User) -> TeamRead:
        clean_name = name.strip()
        if not clean_name:
            raise TeamValidationError("team name must not be empty")
        existing = await self.db.execute(
            select(Team).where(func.lower(Team.name) == clean_name.lower())
        )
        if existing.scalars().first():
            raise TeamConflictError("team name already exists")

        team = Team(id=str(uuid.uuid4()), name=clean_name, created_by=actor.id)
        member = TeamMember(
            id=str(uuid.uuid4()),
            team_id=team.id,
            user_id=actor.id,
            role="owner",
        )
        self.db.add(team)
        self.db.add(member)
        await self.audit.record(
            actor_user_id=actor.id,
            team_id=team.id,
            action="team.created",
            resource_type="team",
            resource_id=team.id,
            metadata={"name": team.name},
        )
        await self.db.commit()
        await self.db.refresh(team)
        return TeamRead(
            id=team.id,
            name=team.name,
            role="owner",
            member_count=1,
            created_at=team.created_at,
        )

    async def join_code(self, team_id: str, actor: User) -> str:
        await self._require_team_admin_role(team_id, actor.id)
        await self._get_team(team_id)
        return _encode_join_code(team_id)

    async def join_with_code(self, code: str, actor: User) -> TeamRead:
        team_id = _decode_join_code(code)
        team = await self._get_team(team_id)
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.user_id == actor.id,
            )
        )
        existing = result.scalars().first()
        if existing:
            return await self._team_to_read(team, existing.role)

        member = TeamMember(
            id=str(uuid.uuid4()),
            team_id=team.id,
            user_id=actor.id,
            role="member",
        )
        self.db.add(member)
        await self.audit.record(
            actor_user_id=actor.id,
            team_id=team.id,
            action="team.member.joined",
            resource_type="team_member",
            resource_id=member.id,
            metadata={"email": actor.email, "role": "member"},
        )
        await self._publish(EventType.TEAM_MEMBER_ADDED, {
            "teamId": team.id,
            "userId": actor.id,
            "role": "member",
        })
        await self.db.commit()
        return await self._team_to_read(team, "member")

    async def add_member(self, team_id: str, email: str, role: str, actor: User) -> TeamMemberRead:
        if role not in VALID_ROLES:
            raise TeamValidationError("invalid team role")
        actor_role = await self._require_team_admin_role(team_id, actor.id)
        if role == "owner" and actor_role != "owner":
            raise PermissionDeniedError("only team owners can grant owner role")
        team = await self._get_team(team_id)
        user = await self.auth.get_or_create_user(email)
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user.id,
            )
        )
        if result.scalars().first():
            raise TeamConflictError("team member already exists")

        member = TeamMember(
            id=str(uuid.uuid4()),
            team_id=team.id,
            user_id=user.id,
            role=role,
        )
        self.db.add(member)
        await self.audit.record(
            actor_user_id=actor.id,
            team_id=team.id,
            action="team.member.added",
            resource_type="team_member",
            resource_id=member.id,
            metadata={"email": user.email, "role": role},
        )
        await self._publish(EventType.TEAM_MEMBER_ADDED, {
            "teamId": team.id,
            "userId": user.id,
            "role": role,
        })
        await self.db.commit()
        await self.db.refresh(member)
        return self._member_to_read(member, user)

    async def list_members(self, team_id: str, actor: User) -> list[TeamMemberRead]:
        await self.role_for_user(team_id, actor.id)
        result = await self.db.execute(
            select(TeamMember, User)
            .join(User, User.id == TeamMember.user_id)
            .where(TeamMember.team_id == team_id)
            .order_by(TeamMember.created_at.asc())
        )
        return [self._member_to_read(member, user) for member, user in result.all()]

    async def update_member_role(
        self,
        team_id: str,
        member_id: str,
        role: str,
        actor: User,
    ) -> TeamMemberRead:
        if role not in VALID_ROLES:
            raise TeamValidationError("invalid team role")
        actor_role = await self._require_team_admin_role(team_id, actor.id)
        member = await self._get_member(team_id, member_id)
        if (member.role == "owner" or role == "owner") and actor_role != "owner":
            raise PermissionDeniedError("only team owners can manage owner role")
        if member.role == "owner" and role != "owner":
            await self._assert_owner_can_leave(team_id)
        member.role = role
        user = await self.db.get(User, member.user_id)
        assert user is not None
        await self.audit.record(
            actor_user_id=actor.id,
            team_id=team_id,
            action="team.member.role_updated",
            resource_type="team_member",
            resource_id=member.id,
            metadata={"email": user.email, "role": role},
        )
        await self.db.commit()
        await self.db.refresh(member)
        return self._member_to_read(member, user)

    async def remove_member(self, team_id: str, member_id: str, actor: User) -> None:
        actor_role = await self._require_team_admin_role(team_id, actor.id)
        member = await self._get_member(team_id, member_id)
        if member.role == "owner":
            if actor_role != "owner":
                raise PermissionDeniedError("only team owners can remove owners")
            await self._assert_owner_can_leave(team_id)
        user = await self.db.get(User, member.user_id)
        await self.db.delete(member)
        await self.audit.record(
            actor_user_id=actor.id,
            team_id=team_id,
            action="team.member.removed",
            resource_type="team_member",
            resource_id=member.id,
            metadata={"email": user.email if user else None, "role": member.role},
        )
        await self.db.commit()

    async def assert_project_create_allowed(self, team_id: str | None, actor: User) -> None:
        if not team_id:
            return
        role = await self.role_for_user(team_id, actor.id)
        if role not in PROJECT_WRITER_ROLES:
            raise PermissionDeniedError("you do not have permission to create team projects")

    async def assert_project_delete_allowed(self, project: Project, actor: User) -> None:
        if project.team_id:
            role = await self.role_for_user(project.team_id, actor.id)
            if role not in TEAM_ADMIN_ROLES:
                raise PermissionDeniedError("you do not have permission to delete team projects")
            return
        if project.owner_user_id and project.owner_user_id != actor.id:
            raise PermissionDeniedError("you do not have permission to delete this project")

    async def assert_workspace_read_allowed(self, project: Project, actor: User) -> None:
        if project.team_id:
            await self.role_for_user(project.team_id, actor.id)
            return
        if project.owner_user_id and project.owner_user_id != actor.id:
            raise PermissionDeniedError("you do not have permission to access this workspace")

    async def assert_workspace_write_allowed(self, project: Project, actor: User) -> None:
        if project.team_id:
            role = await self.role_for_user(project.team_id, actor.id)
            if role not in PROJECT_WRITER_ROLES:
                raise PermissionDeniedError("viewer cannot modify workspace")
            return
        if project.owner_user_id and project.owner_user_id != actor.id:
            raise PermissionDeniedError("you do not have permission to modify this workspace")

    async def assert_team_admin(self, team_id: str, user_id: str) -> None:
        await self._require_team_admin_role(team_id, user_id)

    async def role_for_user(self, team_id: str, user_id: str) -> str:
        team = await self._get_team(team_id)
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.user_id == user_id,
            )
        )
        member = result.scalars().first()
        if not member:
            raise PermissionDeniedError("you do not have access to this team")
        return str(member.role)

    async def _get_team(self, team_id: str) -> Team:
        team = await self.db.get(Team, team_id)
        if not team:
            raise TeamNotFoundError("team not found")
        return team

    async def _get_member(self, team_id: str, member_id: str) -> TeamMember:
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.id == member_id,
            )
        )
        member = result.scalars().first()
        if not member:
            raise TeamNotFoundError("team member not found")
        return member

    async def _require_team_admin_role(self, team_id: str, user_id: str) -> str:
        role = await self.role_for_user(team_id, user_id)
        if role not in TEAM_ADMIN_ROLES:
            raise PermissionDeniedError("you do not have permission to manage team members")
        return role

    async def _assert_owner_can_leave(self, team_id: str) -> None:
        result = await self.db.execute(
            select(func.count(TeamMember.id)).where(
                TeamMember.team_id == team_id,
                TeamMember.role == "owner",
            )
        )
        if int(result.scalar() or 0) <= 1:
            raise TeamValidationError("team must keep at least one owner")

    async def _team_to_read(self, team: Team, role: str) -> TeamRead:
        count_result = await self.db.execute(
            select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id)
        )
        return TeamRead(
            id=team.id,
            name=team.name,
            role=role,
            member_count=int(count_result.scalar() or 0),
            created_at=team.created_at,
        )

    def _member_to_read(self, member: TeamMember, user: User) -> TeamMemberRead:
        return TeamMemberRead(
            id=member.id,
            team_id=member.team_id,
            user_id=member.user_id,
            email=user.email,
            display_name=user.display_name,
            role=member.role,
            created_at=member.created_at,
        )

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)


def _encode_join_code(team_id: str) -> str:
    payload = json.dumps({"v": 1, "teamId": team_id}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = hmac.new(settings.agenthub_secret_key.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(signature)}"


def _decode_join_code(code: str) -> str:
    try:
        payload_part, signature_part = (code or "").strip().split(".", 1)
        payload = _unb64(payload_part)
        signature = _unb64(signature_part)
    except Exception as exc:
        raise TeamValidationError("invalid team join code") from exc
    expected = hmac.new(settings.agenthub_secret_key.encode("utf-8"), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise TeamValidationError("invalid team join code")
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise TeamValidationError("invalid team join code") from exc
    team_id = str(data.get("teamId") or "")
    if not team_id:
        raise TeamValidationError("invalid team join code")
    return team_id


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
