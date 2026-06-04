from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.project_service import (
    ProjectConflictError,
    ProjectNotFoundError,
    ProjectService,
    ProjectValidationError,
    register_folder_grant,
)
from ..services.schemas import ProjectCreate, ProjectRead
from ..services.workspace_provider import (
    WorkspaceFileTooLargeError,
    WorkspaceNotFoundError,
    WorkspaceSecurityError,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _svc(db: AsyncSession) -> ProjectService:
    from ..main import _event_bus
    return ProjectService(db, event_bus=_event_bus)


class TreeRead(BaseModel):
    tree: list[dict]


class FileRead(BaseModel):
    path: str
    content: str
    size: int


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
async def archive_project(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).archive_project(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")


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
        return await _svc(db).create_preview(project_id, data.type)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="未找到可预览的文件（需要 index.html）")
    except ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{project_id}/build")
async def start_build(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await _svc(db).start_build(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")


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
