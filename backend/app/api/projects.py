from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
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
from ..services.workspace_provider import (
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


class TreeRead(BaseModel):
    tree: list[dict]


class FileRead(BaseModel):
    path: str
    content: str
    size: int


class FileWriteRequest(BaseModel):
    path: str
    content: str


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
    from pathlib import Path
    folder = Path(path)
    return {
        "workspacePath": str(folder),
        "folderName": folder.name or "新项目",
        "folderToken": token,
    }


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).create_project(data)
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: AsyncSession = Depends(get_db)):
    return await _svc(db).list_projects()


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).get_project(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    deleteFiles: bool = False,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _svc(db).delete_project(project_id, delete_files=deleteFiles)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except ProjectDeleteSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{project_id}/archive")
async def archive_project(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).archive_project(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        if data.name is None:
            return await _svc(db).get_project(project_id)
        return await _svc(db).rename_project(project_id, data.name)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{project_id}/tree", response_model=TreeRead)
async def get_tree(
    project_id: str,
    subpath: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        return {"tree": await _svc(db).get_tree(project_id, subpath)}
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except PreviewError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="path not found")


@router.get("/{project_id}/files", response_model=FileRead)
async def read_file(project_id: str, path: str, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).read_file(project_id, path)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except WorkspaceFileTooLargeError:
        raise HTTPException(status_code=400, detail="文件过大，无法在编辑器中打开")
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")


@router.put("/{project_id}/files", response_model=FileRead)
async def write_file(project_id: str, data: FileWriteRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).write_file(project_id, data.path, data.content)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail="workspace not found")


@router.post("/{project_id}/snapshot", response_model=SnapshotRead, status_code=201)
async def create_snapshot(
    project_id: str,
    data: SnapshotRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _svc(db).create_snapshot(project_id, data.label)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{project_id}/diff", response_model=DiffRead)
async def get_diff(project_id: str, baseRef: str, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).get_diff(project_id, baseRef)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="snapshot not found")


@router.post("/{project_id}/preview", response_model=PreviewRead)
async def create_preview(
    project_id: str,
    data: PreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _svc(db).create_preview(project_id, data.type, data.file_path)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="未找到可预览的文件")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{project_id}/builds", response_model=BuildQueuedRead, status_code=202)
async def create_project_build(
    project_id: str,
    data: BuildCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
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


@router.get("/{project_id}/builds", response_model=BuildListRead)
async def list_project_builds(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return BuildListRead(items=await _build_svc(db).list_builds(project_id))
    except BuildNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")


@router.get("/{project_id}/builds/{build_id}", response_model=BuildRunRead)
async def get_project_build(
    project_id: str,
    build_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        build = await _build_svc(db).get_build(project_id, build_id)
        from ..services.build_service import build_to_read
        return build_to_read(build)
    except BuildNotFoundError:
        raise HTTPException(status_code=404, detail="build not found")


@router.get("/{project_id}/builds/{build_id}/logs", response_model=BuildLogsRead)
async def get_project_build_logs(
    project_id: str,
    build_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return BuildLogsRead(chunks=await _build_svc(db).get_logs(project_id, build_id))
    except BuildNotFoundError:
        raise HTTPException(status_code=404, detail="build not found")


@router.get("/{project_id}/exports/source")
async def export_project_source(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
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


@router.get("/{project_id}/exports/builds/{build_id}")
async def export_project_build(
    project_id: str,
    build_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
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


@router.post("/{project_id}/previews", response_model=ProjectPreviewRead)
async def create_project_preview(
    project_id: str,
    data: ProjectPreviewCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
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


@router.post("/{project_id}/build")
async def start_build(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
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


@router.get("/{project_id}/preview/{preview_id}/{asset_path:path}")
async def serve_preview_asset(
    project_id: str,
    preview_id: str,
    asset_path: str,
    db: AsyncSession = Depends(get_db),
):
    del preview_id
    svc = _svc(db)
    try:
        project = await svc._get_project(project_id)
        target = svc.provider.safe_resolve(project.workspace_path, asset_path or "index.html")
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except WorkspaceSecurityError:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(target)


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
