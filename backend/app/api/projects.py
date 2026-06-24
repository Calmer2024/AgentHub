import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote

from ..database import get_db
from ..services.build_service import (
    BuildConflictError,
    BuildNotFoundError,
    BuildNotReadyError,
    BuildService,
    BuildValidationError,
)
from ..services.phase8_schemas import (
    BuildCreate,
    BuildListRead,
    BuildLogsRead,
    BuildQueuedRead,
    BuildRunRead,
    ProjectPreviewCreate,
    ProjectPreviewRead,
)
from ..services.project_service import (
    ProjectConflictError,
    ProjectDeleteSafetyError,
    ProjectNotFoundError,
    ProjectService,
    ProjectValidationError,
    register_folder_grant,
)
from ..services.preview_service import PreviewError
from ..services.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from ..services.team_service import PermissionDeniedError
from ..services.auth_service import AuthService
from ..services.html_preview_assets import inline_local_html_assets
from ..services.tenant_guard import TenantGuard, tenant_scope_required_for_cloud
from ..services.workspace_provider import (
    EXCLUDED_NAMES,
    WorkspaceFileConflictError,
    WorkspaceFileExistsError,
    WorkspaceFileTooLargeError,
    WorkspaceNotFoundError,
    WorkspaceSecurityError,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _svc(db: AsyncSession) -> ProjectService:
    from ..main import _event_bus
    return ProjectService(db, event_bus=_event_bus)


def _build_svc(db: AsyncSession) -> BuildService:
    from ..main import _event_bus
    return BuildService(db, event_bus=_event_bus)


async def _optional_scope(request: Request, db: AsyncSession):
    user = await AuthService(db).resolve_request(request)
    if not user:
        return None
    return await TenantGuard(db).scope_for_user(user)


async def _require_actor(request: Request, db: AsyncSession):
    user = await AuthService(db).resolve_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录后继续")
    return user


async def _authorize_project(
    request: Request,
    db: AsyncSession,
    project_id: str,
    *,
    mode: str,
):
    project = await _svc(db)._get_project(project_id)
    if project.workspace_mode != "cloud" and not tenant_scope_required_for_cloud():
        return project
    user = await _require_actor(request, db)
    scope = await TenantGuard(db).scope_for_user(user)
    guard = TenantGuard(db)
    if mode == "read":
        await guard.assert_project_read(scope, project)
    elif mode == "delete":
        await guard.assert_project_delete(scope, project)
    else:
        await guard.assert_project_write(scope, project)
    return project


class TreeRead(BaseModel):
    tree: list[dict]


class FileRead(BaseModel):
    path: str
    content: str
    size: int
    name: str | None = None
    type: str | None = None
    mtime: float | None = None
    etag: str | None = None
    media_type: str | None = Field(default=None, alias="mediaType")
    extension: str | None = None
    editable: bool | None = None
    previewable: bool | None = None
    preview_kind: str | None = Field(default=None, alias="previewKind")
    readonly_reason: str | None = Field(default=None, alias="readonlyReason")
    encoding: str | None = None

    model_config = {"populate_by_name": True}


class FileWriteRequest(BaseModel):
    path: str
    content: str
    base_etag: str | None = Field(default=None, alias="baseEtag")
    force: bool = False

    model_config = {"populate_by_name": True}


class FileCreateRequest(BaseModel):
    path: str
    content: str = ""
    overwrite: bool = False


class DirectoryCreateRequest(BaseModel):
    path: str


class PathMoveRequest(BaseModel):
    source_path: str = Field(alias="sourcePath")
    target_path: str = Field(alias="targetPath")
    overwrite: bool = False

    model_config = {"populate_by_name": True}


class PathDeleteRequest(BaseModel):
    paths: list[str]
    use_trash: bool = Field(default=True, alias="useTrash")

    model_config = {"populate_by_name": True}


class PathOperationRead(BaseModel):
    items: list[dict]


class SearchRead(BaseModel):
    items: list[dict]


class SnapshotRequest(BaseModel):
    label: str


class SnapshotRead(BaseModel):
    snapshot_id: str = Field(alias="snapshotId")
    label: str
    created_at: str = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class DiffRead(BaseModel):
    changed_files: list[dict] = Field(alias="changedFiles")

    model_config = {"populate_by_name": True}


class PreviewRequest(BaseModel):
    type: str = "static"
    file_path: str | None = Field(default=None, alias="filePath")

    model_config = {"populate_by_name": True}


class PreviewRead(BaseModel):
    preview_id: str = Field(alias="previewId")
    preview_url: str = Field(alias="previewUrl")

    model_config = {"populate_by_name": True}


class FolderPickRead(BaseModel):
    workspace_path: str = Field(alias="workspacePath")
    folder_name: str = Field(alias="folderName")
    folder_token: str = Field(alias="folderToken")

    model_config = {"populate_by_name": True}


@router.post("/pick-folder", response_model=FolderPickRead)
async def pick_folder():
    path = _pick_folder_dialog()
    if not path:
        raise HTTPException(status_code=400, detail="folder selection cancelled")
    token = register_folder_grant(path)
    folder = Path(path)
    return {
        "workspacePath": str(folder),
        "folderName": folder.name or "新项目",
        "folderToken": token,
    }


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(
    data: ProjectCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        actor = None
        if tenant_scope_required_for_cloud() and data.workspace_mode != "cloud":
            raise PermissionDeniedError("SaaS/Mobile 只能创建云端项目")
        if data.workspace_mode == "cloud" or data.team_id:
            actor = await _require_actor(request, db)
        return await _svc(db).create_project(data, actor=actor)
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("", response_model=list[ProjectRead])
async def list_projects(request: Request, db: AsyncSession = Depends(get_db)):
    scope = await _optional_scope(request, db)
    if tenant_scope_required_for_cloud() and not scope:
        raise HTTPException(status_code=401, detail="请先登录后继续")
    try:
        return await _svc(db).list_projects(scope=scope)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        project = await _authorize_project(request, db, project_id, mode="read")
        return await _svc(db)._to_read(project, include_stats=True)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    request: Request,
    deleteFiles: bool = False,
    db: AsyncSession = Depends(get_db),
):
    try:
        actor = None
        project = await _authorize_project(request, db, project_id, mode="delete")
        if project.workspace_mode == "cloud" or project.team_id:
            actor = await _require_actor(request, db)
        return await _svc(db).delete_project(project_id, delete_files=deleteFiles, actor=actor)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except ProjectDeleteSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{project_id}/archive")
async def archive_project(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_project(request, db, project_id, mode="write")
        return await _svc(db).archive_project(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="write")
        if data.name is None:
            return await _svc(db).get_project(project_id)
        return await _svc(db).rename_project(project_id, data.name)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}/tree", response_model=TreeRead)
async def get_tree(
    project_id: str,
    request: Request,
    subpath: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        return {"tree": await _svc(db).get_tree(project_id, subpath)}
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except PreviewError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="path not found")


@router.get("/{project_id}/files", response_model=FileRead)
async def read_file(project_id: str, path: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        return await _svc(db).read_file(project_id, path)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceFileTooLargeError:
        raise HTTPException(status_code=400, detail="文件过大，无法在编辑器中打开")
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.put("/{project_id}/files", response_model=FileRead)
async def write_file(project_id: str, data: FileWriteRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_project(request, db, project_id, mode="write")
        return await _svc(db).write_file(
            project_id,
            data.path,
            data.content,
            base_etag=data.base_etag,
            force=data.force,
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceFileConflictError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "code": "workspace_file_conflict",
                "currentContent": exc.current_content,
                "currentEtag": exc.current_etag,
                "currentMtime": exc.current_mtime,
            },
        )
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{project_id}/files", response_model=FileRead, status_code=201)
async def create_file(project_id: str, data: FileCreateRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_project(request, db, project_id, mode="write")
        return await _svc(db).create_file(
            project_id,
            data.path,
            data.content,
            overwrite=data.overwrite,
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceFileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ProjectValidationError, WorkspaceNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{project_id}/directories", status_code=201)
async def create_directory(
    project_id: str,
    data: DirectoryCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="write")
        return await _svc(db).create_directory(project_id, data.path)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceFileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ProjectValidationError, WorkspaceNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.patch("/{project_id}/paths")
async def move_path(project_id: str, data: PathMoveRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_project(request, db, project_id, mode="write")
        return await _svc(db).move_path(
            project_id,
            data.source_path,
            data.target_path,
            overwrite=data.overwrite,
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceFileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.delete("/{project_id}/paths", response_model=PathOperationRead)
async def delete_paths(project_id: str, data: PathDeleteRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_project(request, db, project_id, mode="write")
        return await _svc(db).delete_paths(project_id, data.paths, use_trash=data.use_trash)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}/search-files", response_model=SearchRead)
async def search_files(
    project_id: str,
    q: str,
    request: Request,
    includeContent: bool = True,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        return await _svc(db).search_files(
            project_id,
            q,
            include_content=includeContent,
            limit=max(1, min(limit, 200)),
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}/download")
async def download_path(
    project_id: str,
    request: Request,
    path: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        if path:
            svc = _svc(db)
            project = await svc._get_project(project_id)
            workspace_path = svc._file_workspace_path(project)
            target = svc.provider.safe_resolve(workspace_path, path)
            rel_parts = target.relative_to(Path(workspace_path).expanduser().resolve()).parts
            if any(part in EXCLUDED_NAMES for part in rel_parts):
                raise WorkspaceSecurityError("protected path")
            if not target.exists():
                raise WorkspaceNotFoundError("path not found")
            if target.is_file():
                return FileResponse(
                    target,
                    media_type=_media_type_for_path(target),
                    filename=target.name,
                    headers={"X-Content-Type-Options": "nosniff"},
                )
        data, filename = await _svc(db).download_path(project_id, path)
        return _zip_response(data, filename)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="path not found")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{project_id}/snapshot", response_model=SnapshotRead, status_code=201)
async def create_snapshot(
    project_id: str,
    data: SnapshotRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="write")
        return await _svc(db).create_snapshot(project_id, data.label)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}/diff", response_model=DiffRead)
async def get_diff(project_id: str, baseRef: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        return await _svc(db).get_diff(project_id, baseRef)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="snapshot not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{project_id}/preview", response_model=PreviewRead)
async def create_preview(
    project_id: str,
    data: PreviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        return await _svc(db).create_preview(project_id, data.type, data.file_path)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="未找到可预览的文件")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{project_id}/builds", response_model=BuildQueuedRead, status_code=202)
async def create_project_build(
    project_id: str,
    data: BuildCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="write")
        build = await _build_svc(db).run_build(
            project_id,
            command=data.command,
            install_command=data.install_command,
            artifact_path=data.artifact_path,
        )
        return BuildQueuedRead(build_id=build.id, status=build.status)
    except (BuildNotFoundError, ProjectNotFoundError):
        raise HTTPException(status_code=404, detail="project not found")
    except BuildConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (BuildValidationError, WorkspaceNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}/builds", response_model=BuildListRead)
async def list_project_builds(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        return BuildListRead(items=await _build_svc(db).list_builds(project_id))
    except BuildNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}/builds/{build_id}", response_model=BuildRunRead)
async def get_project_build(
    project_id: str,
    build_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        build = await _build_svc(db).get_build(project_id, build_id)
        from ..services.build_service import build_to_read
        return build_to_read(build)
    except BuildNotFoundError:
        raise HTTPException(status_code=404, detail="build not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}/builds/{build_id}/logs", response_model=BuildLogsRead)
async def get_project_build_logs(
    project_id: str,
    build_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        return BuildLogsRead(chunks=await _build_svc(db).get_logs(project_id, build_id))
    except BuildNotFoundError:
        raise HTTPException(status_code=404, detail="build not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}/exports/source")
async def export_project_source(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        data, filename = await _build_svc(db).export_source(project_id)
        return _zip_response(data, filename)
    except BuildNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except BuildConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}/exports/builds/{build_id}")
async def export_project_build(
    project_id: str,
    build_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        data, filename = await _build_svc(db).export_build(project_id, build_id)
        return _zip_response(data, filename)
    except BuildNotFoundError:
        raise HTTPException(status_code=404, detail="build not found")
    except BuildNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{project_id}/previews", response_model=ProjectPreviewRead)
async def create_project_preview(
    project_id: str,
    data: ProjectPreviewCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_project(request, db, project_id, mode="read")
        return await _build_svc(db).create_preview(
            project_id,
            source=data.source,
            path=data.path,
            build_id=data.build_id,
        )
    except BuildNotFoundError:
        raise HTTPException(status_code=404, detail="project or build not found")
    except BuildNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except BuildValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="未找到可预览的文件")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{project_id}/build")
async def start_build(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_project(request, db, project_id, mode="write")
        build = await _build_svc(db).run_build(
            project_id,
            command=None,
            install_command=None,
            artifact_path=None,
        )
        return {"buildId": build.id, "status": build.status}
    except BuildNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except BuildConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except BuildValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{project_id}/preview/{preview_id}/{asset_path:path}")
async def serve_preview_asset(
    project_id: str,
    preview_id: str,
    asset_path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    del preview_id
    svc = _svc(db)
    try:
        await _authorize_project(request, db, project_id, mode="read")
        project = await svc._get_project(project_id)
        workspace_path = svc._file_workspace_path(project)
        target = svc.provider.safe_resolve(workspace_path, asset_path or "index.html")
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    media_type = _media_type_for_path(target)
    if _is_html_preview_media_type(media_type):
        base_dir = target.parent

        def resolve_local_asset(path: str) -> Path:
            return svc.provider.safe_resolve(str(base_dir), path)

        html = inline_local_html_assets(
            target.read_text(encoding="utf-8", errors="replace"),
            resolve_local_asset,
        )
        return Response(
            content=html,
            media_type=media_type,
            headers={"X-Content-Type-Options": "nosniff"},
        )
    return FileResponse(
        target,
        media_type=media_type,
        filename=target.name,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _media_type_for_path(path: Path) -> str:
    media_type, _ = mimetypes.guess_type(path.name)
    if path.suffix.lower() == ".js":
        return "text/javascript"
    if path.suffix.lower() == ".css":
        return "text/css"
    return media_type or "application/octet-stream"


def _is_html_preview_media_type(media_type: str | None) -> bool:
    return bool(media_type and media_type.split(";", 1)[0].strip().lower() == "text/html")


def _pick_folder_dialog() -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"system folder picker unavailable: {exc}")

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(title="选择项目文件夹")
        return selected or None
    finally:
        root.destroy()


def _zip_response(data: bytes, filename: str) -> Response:
    encoded_filename = quote(filename)
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="agenthub-export.zip"; filename*=UTF-8\'\'{encoded_filename}'
            ),
        },
    )
