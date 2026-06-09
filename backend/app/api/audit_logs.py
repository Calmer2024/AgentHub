from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Project, User
from ..services.audit_service import AuditService
from ..services.phase9_schemas import AuditLogListRead
from ..services.team_service import PermissionDeniedError, TeamService
from ..services.tenant_guard import TenantGuard
from .auth import require_current_user

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", response_model=AuditLogListRead)
async def list_audit_logs(
    projectId: str | None = None,
    teamId: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    from ..main import _event_bus

    team_service = TeamService(db, event_bus=_event_bus)
    try:
        guard = TenantGuard(db)
        scope = await guard.scope_for_user(user)
        if teamId:
            await team_service.role_for_user(teamId, user.id)
        if projectId:
            project = await db.get(Project, projectId)
            if not project:
                raise HTTPException(status_code=404, detail="project not found")
            await guard.assert_project_read(scope, project)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    service = AuditService(db, event_bus=_event_bus)
    if not projectId and not teamId:
        return AuditLogListRead(items=await service.list_logs_for_scope(scope))
    return AuditLogListRead(items=await service.list_logs(project_id=projectId, team_id=teamId))
