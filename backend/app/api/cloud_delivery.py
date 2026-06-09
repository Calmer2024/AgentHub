from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.cloud_delivery_service import (
    CloudDeliveryNotFoundError,
    CloudDeliveryService,
    CloudDeliveryValidationError,
    DeploymentConflictError,
    PreviewExpiredError,
)
from ..services.phase11_schemas import (
    DeploymentCreate,
    DeploymentLogsRead,
    DeploymentRead,
    DeploymentRetryRequest,
    DeploymentRollbackRequest,
    PreviewCreate,
    PreviewRevokeRead,
    PreviewRevokeRequest,
    PreviewSessionRead,
)
from ..services.team_service import PermissionDeniedError
from .auth import require_current_user

router = APIRouter(prefix="", tags=["cloud-delivery"])


def _svc(db: AsyncSession) -> CloudDeliveryService:
    from ..main import _event_bus
    return CloudDeliveryService(db, event_bus=_event_bus)


@router.post("/artifacts/{artifact_id}/previews", response_model=PreviewSessionRead, status_code=201)
async def create_artifact_preview(
    artifact_id: str,
    data: PreviewCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).create_preview(artifact_id, data, user)
    except CloudDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except CloudDeliveryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/previews/{preview_id}", response_model=PreviewSessionRead)
async def get_preview(
    preview_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).get_preview(preview_id, user)
    except PreviewExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc))
    except CloudDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/previews/{preview_id}/revoke", response_model=PreviewRevokeRead, status_code=202)
async def revoke_preview(
    preview_id: str,
    data: PreviewRevokeRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        status = await _svc(db).revoke_preview(preview_id, user, reason=data.reason if data else None)
        return PreviewRevokeRead(status=status)
    except CloudDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/deployments", response_model=DeploymentRead, status_code=202)
async def create_deployment(
    data: DeploymentCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).create_deployment(data, user)
    except CloudDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except DeploymentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except CloudDeliveryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/deployments/{deployment_id}", response_model=DeploymentRead)
async def get_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).get_deployment(deployment_id, user)
    except CloudDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/deployments/{deployment_id}/logs", response_model=DeploymentLogsRead)
async def get_deployment_logs(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).get_deployment_logs(deployment_id, user)
    except CloudDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/deployments/{deployment_id}/retry", response_model=DeploymentRead, status_code=202)
async def retry_deployment(
    deployment_id: str,
    data: DeploymentRetryRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).retry_deployment(
            deployment_id,
            user,
            from_stage=data.from_stage if data else None,
        )
    except CloudDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except DeploymentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except CloudDeliveryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/deployments/{deployment_id}/rollback", response_model=DeploymentRead, status_code=202)
async def rollback_deployment(
    deployment_id: str,
    data: DeploymentRollbackRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).rollback_deployment(deployment_id, user, data.target_deployment_id)
    except CloudDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except CloudDeliveryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
