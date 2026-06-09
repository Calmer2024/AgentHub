"""Phase 13 产品壳能力契约。"""

from typing import Literal

from pydantic import BaseModel, Field


ProductEdition = Literal["local", "saas"]
AppSurface = Literal["desktop", "mobile"]


class RuntimeFeatureFlags(BaseModel):
    local_workspace: bool = Field(alias="localWorkspace")
    local_cli_runtime: bool = Field(alias="localCliRuntime")
    local_preview: bool = Field(alias="localPreview")
    local_build_export: bool = Field(alias="localBuildExport")
    cloud_workspace: bool = Field(alias="cloudWorkspace")
    team_spaces: bool = Field(alias="teamSpaces")
    cloud_preview: bool = Field(alias="cloudPreview")
    deployment: bool
    audit_logs: bool = Field(alias="auditLogs")
    notifications: bool
    mobile_approvals: bool = Field(alias="mobileApprovals")

    model_config = {"populate_by_name": True}


class RuntimeLimits(BaseModel):
    max_upload_bytes: int | None = Field(default=None, alias="maxUploadBytes")

    model_config = {"populate_by_name": True}


class RuntimeCapabilitiesRead(BaseModel):
    edition: ProductEdition
    surface: AppSurface
    auth_required: bool = Field(alias="authRequired")
    api_base_url: str = Field(alias="apiBaseUrl")
    features: RuntimeFeatureFlags
    limits: RuntimeLimits

    model_config = {"populate_by_name": True}
