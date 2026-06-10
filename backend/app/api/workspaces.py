from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.cloud_workspace_provider import (
    CloudWorkspaceProvider,
    WorkspaceConflictError,
    WorkspaceNotFoundCloudError,
    WorkspaceUnsupportedMediaError,
    WorkspaceValidationError,
)
from ..services.phase9_schemas import (
    GitHubImportCreate,
    WorkspaceImportQueuedRead,
    WorkspaceRead,
    WorkspaceRestoreCreate,
    WorkspaceRestoreQueuedRead,
    WorkspaceSnapshotCreate,
    WorkspaceSnapshotRead,
)
from ..services.team_service import PermissionDeniedError
from .auth import require_current_user

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _svc(db: AsyncSession) -> CloudWorkspaceProvider:
    from ..main import _event_bus
    return CloudWorkspaceProvider(db, event_bus=_event_bus)


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return await _svc(db).get_workspace(workspace_id, user)
    except WorkspaceNotFoundCloudError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{workspace_id}/snapshots", response_model=WorkspaceSnapshotRead, status_code=201)
async def create_workspace_snapshot(
    workspace_id: str,
    data: WorkspaceSnapshotCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return await _svc(db).create_snapshot(workspace_id, data.label, user)
    except WorkspaceNotFoundCloudError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except WorkspaceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{workspace_id}/snapshots/{snapshot_id}/restore", response_model=WorkspaceRestoreQueuedRead, status_code=202)
async def restore_workspace_snapshot(
    workspace_id: str,
    snapshot_id: str,
    data: WorkspaceRestoreCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        restore_id = await _svc(db).restore_snapshot(workspace_id, snapshot_id, data.strategy, user)
        return WorkspaceRestoreQueuedRead(restore_id=restore_id)
    except WorkspaceNotFoundCloudError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WorkspaceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except WorkspaceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{workspace_id}/imports/zip", response_model=WorkspaceImportQueuedRead, status_code=202)
async def import_workspace_zip(
    workspace_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        data = await file.read()
        import_id, status = await _svc(db).import_zip(
            workspace_id,
            filename=file.filename or "source.zip",
            content_type=file.content_type,
            data=data,
            actor=user,
        )
        return WorkspaceImportQueuedRead(import_id=import_id, status=status)
    except WorkspaceUnsupportedMediaError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except WorkspaceNotFoundCloudError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except WorkspaceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except WorkspaceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{workspace_id}/imports/github", response_model=WorkspaceImportQueuedRead, status_code=202)
async def import_workspace_github(
    workspace_id: str,
    data: GitHubImportCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        import_id, status = await _svc(db).import_github(
            workspace_id,
            repo_url=data.repo_url,
            branch=data.branch,
            actor=user,
        )
        return WorkspaceImportQueuedRead(import_id=import_id, status=status)
    except WorkspaceNotFoundCloudError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except WorkspaceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
