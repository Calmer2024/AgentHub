"""Phase 14 租户范围与 cloud 资源访问门卫。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Project, TeamMember, User
from .audit_service import AuditService
from .team_service import PermissionDeniedError


PROJECT_WRITER_ROLES = {"owner", "admin", "member"}
TEAM_ADMIN_ROLES = {"owner", "admin"}


@dataclass(frozen=True)
class TenantScope:
    actor_user_id: str
    personal_project_owner_id: str
    team_ids: list[str]
    edition: str
    surface: str


class TenantGuard:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    async def scope_for_user(self, user: User) -> TenantScope:
        result = await self.db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == user.id)
        )
        return TenantScope(
            actor_user_id=user.id,
            personal_project_owner_id=user.id,
            team_ids=[str(item) for item in result.scalars().all()],
            edition=_edition(),
            surface=_surface(),
        )

    def visible_project_filter(self, scope: TenantScope):
        filters = [
            (Project.workspace_mode == "cloud")
            & (Project.owner_user_id == scope.personal_project_owner_id)
            & Project.team_id.is_(None),
        ]
        if scope.team_ids:
            filters.append((Project.workspace_mode == "cloud") & Project.team_id.in_(scope.team_ids))
        return or_(*filters)

    async def assert_project_read(self, scope: TenantScope, project: Project) -> None:
        if project.workspace_mode != "cloud":
            if scope.edition == "saas":
                await self._deny(scope, "project.read.denied", project, "SaaS 无权访问本机项目")
            return
        if project.team_id:
            if project.team_id in scope.team_ids:
                return
            await self._deny(scope, "project.read.denied", project, "不属于该团队")
        if project.owner_user_id == scope.actor_user_id:
            return
        await self._deny(scope, "project.read.denied", project, "不属于当前用户")

    async def assert_project_write(self, scope: TenantScope, project: Project) -> None:
        if project.workspace_mode != "cloud":
            if scope.edition == "saas":
                await self._deny(scope, "project.write.denied", project, "SaaS 无权修改本机项目")
            return
        if project.team_id:
            role = await self._role_for(scope, project.team_id)
            if role in PROJECT_WRITER_ROLES:
                return
            await self._deny(scope, "project.write.denied", project, "viewer 不能修改团队项目")
        if project.owner_user_id == scope.actor_user_id:
            return
        await self._deny(scope, "project.write.denied", project, "不属于当前用户")

    async def assert_project_delete(self, scope: TenantScope, project: Project) -> None:
        if project.workspace_mode != "cloud":
            if scope.edition == "saas":
                await self._deny(scope, "project.delete.denied", project, "SaaS 无权删除本机项目")
            return
        if project.team_id:
            role = await self._role_for(scope, project.team_id)
            if role in TEAM_ADMIN_ROLES:
                return
            await self._deny(scope, "project.delete.denied", project, "只有团队管理员可以删除团队项目")
        if project.owner_user_id == scope.actor_user_id:
            return
        await self._deny(scope, "project.delete.denied", project, "不属于当前用户")

    async def can_read_project(self, scope: TenantScope, project: Project) -> bool:
        try:
            await self.assert_project_read(scope, project)
            return True
        except PermissionDeniedError:
            return False

    async def _role_for(self, scope: TenantScope, team_id: str) -> str:
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == scope.actor_user_id,
            )
        )
        member = result.scalars().first()
        if not member:
            raise PermissionDeniedError("you do not have access to this team")
        return str(member.role)

    async def _deny(
        self,
        scope: TenantScope,
        action: str,
        project: Project,
        reason: str,
    ) -> None:
        await self.audit.record(
            actor_user_id=scope.actor_user_id,
            team_id=project.team_id,
            project_id=project.id,
            action=action,
            resource_type="project",
            resource_id=project.id,
            metadata={"reason": reason},
        )
        await self.db.commit()
        raise PermissionDeniedError(reason)


def tenant_scope_required_for_cloud() -> bool:
    return bool(settings.agenthub_auth_required or _edition() == "saas" or _surface() == "mobile")


def _edition() -> str:
    return "saas" if settings.agenthub_edition.lower() == "saas" else "local"


def _surface() -> str:
    return "mobile" if settings.agenthub_surface.lower() == "mobile" else "desktop"
