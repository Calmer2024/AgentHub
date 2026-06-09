from typing import cast

from fastapi import APIRouter

from ..config import settings
from ..services.phase13_schemas import (
    AppSurface,
    ProductEdition,
    RuntimeCapabilitiesRead,
    RuntimeFeatureFlags,
    RuntimeLimits,
)

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


def _normalized_edition(value: str) -> str:
    return "saas" if value.lower() == "saas" else "local"


def _normalized_surface(value: str) -> str:
    return "mobile" if value.lower() == "mobile" else "desktop"


def _feature_matrix(edition: str, surface: str) -> RuntimeFeatureFlags:
    is_local_desktop = edition == "local" and surface == "desktop"
    is_saas_desktop = edition == "saas" and surface == "desktop"
    is_mobile = edition == "saas" and surface == "mobile"

    return RuntimeFeatureFlags(
        local_workspace=is_local_desktop,
        local_cli_runtime=is_local_desktop,
        local_preview=is_local_desktop,
        local_build_export=is_local_desktop,
        cloud_workspace=is_saas_desktop or is_mobile,
        team_spaces=is_saas_desktop,
        cloud_preview=is_saas_desktop or is_mobile,
        deployment=is_saas_desktop,
        audit_logs=is_saas_desktop,
        notifications=is_saas_desktop or is_mobile,
        mobile_approvals=is_mobile,
    )


@router.get("", response_model=RuntimeCapabilitiesRead)
async def get_capabilities() -> RuntimeCapabilitiesRead:
    edition = _normalized_edition(settings.agenthub_edition)
    surface = _normalized_surface(settings.agenthub_surface)
    auth_required = bool(settings.agenthub_auth_required or edition == "saas")

    return RuntimeCapabilitiesRead(
        edition=cast(ProductEdition, edition),
        surface=cast(AppSurface, surface),
        auth_required=auth_required,
        api_base_url=settings.agenthub_api_base_url.rstrip("/"),
        features=_feature_matrix(edition, surface),
        limits=RuntimeLimits(max_upload_bytes=settings.agenthub_max_upload_bytes),
    )
