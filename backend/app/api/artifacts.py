import mimetypes
import re
from html import escape
from pathlib import Path
from typing import Callable, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Artifact, Project, Session as DBSession
from ..services.artifact_preview import artifact_preview_payload, infer_artifact_preview
from ..services.artifact_service import (
    ArtifactEditError,
    ArtifactNotFoundError,
    ArtifactService,
    ArtifactVersionNotFoundError,
    ArtifactWorkspaceWriteError,
    DiffResult,
)
from ..services.auth_service import AuthService
from ..services.cloud_storage import ensure_cloud_workspace
from ..services.html_preview_assets import inline_local_html_assets
from ..services.team_service import PermissionDeniedError
from ..services.tenant_guard import TenantGuard, tenant_scope_required_for_cloud
from ..services.workspace_provider import LocalWorkspaceProvider, WorkspaceNotFoundError, WorkspaceSecurityError

router = APIRouter(prefix="", tags=["artifacts"])


async def _authorize_project(request: Request, db: AsyncSession, project: Project | None, mode: str) -> None:
    if not project:
        return
    if project.workspace_mode != "cloud" and not tenant_scope_required_for_cloud():
        return
    actor = await AuthService(db).resolve_request(request)
    if not actor:
        raise HTTPException(status_code=401, detail="请先登录后继续")
    scope = await TenantGuard(db).scope_for_user(actor)
    guard = TenantGuard(db)
    try:
        if mode == "read":
            await guard.assert_project_read(scope, project)
        else:
            await guard.assert_project_write(scope, project)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


async def _authorize_session(request: Request, db: AsyncSession, session_id: str, mode: str) -> None:
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    project = await db.get(Project, session.project_id) if session.project_id else None
    await _authorize_project(request, db, project, mode)


async def _authorize_artifact(request: Request, db: AsyncSession, artifact_id: str, mode: str) -> Artifact:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    project = await db.get(Project, artifact.project_id) if artifact.project_id else None
    if project:
        await _authorize_project(request, db, project, mode)
    else:
        await _authorize_session(request, db, artifact.session_id, mode)
    return artifact


def _artifact_svc(db: AsyncSession) -> ArtifactService:
    from ..main import _event_bus
    return ArtifactService(db, event_bus=_event_bus)


def _artifact_file_target(project: Project, file_path: str) -> Path:
    workspace_path = _project_workspace_path(project)
    try:
        return LocalWorkspaceProvider().safe_resolve(workspace_path, file_path)
    except WorkspaceSecurityError as exc:
        raise HTTPException(status_code=403, detail="无权访问此路径") from exc
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="workspace not found") from exc


def _project_workspace_path(project: Project) -> str:
    if project.workspace_mode == "cloud":
        if not project.workspace_id:
            raise HTTPException(status_code=409, detail="cloud workspace is not initialized")
        return str(ensure_cloud_workspace(project.workspace_id, {
            "projectId": project.id,
            "projectName": project.name,
        }))
    return project.workspace_path


def _artifact_asset_target(project: Project, artifact_file_path: str, asset_path: str) -> Path:
    clean_asset = asset_path.replace("\\", "/").strip()
    if not clean_asset or clean_asset.startswith("/") or clean_asset.startswith("~"):
        raise HTTPException(status_code=403, detail="无权访问此路径")
    if any(part == ".." for part in clean_asset.split("/")):
        raise HTTPException(status_code=403, detail="无权访问此路径")

    artifact_rel = Path(artifact_file_path.replace("\\", "/"))
    artifact_dir = artifact_rel.parent.as_posix()
    combined = clean_asset if artifact_dir in {"", "."} else f"{artifact_dir}/{clean_asset}"
    target = _artifact_file_target(project, combined)
    base_dir = _artifact_file_target(project, artifact_dir if artifact_dir not in {"", "."} else "")
    if target != base_dir and base_dir not in target.parents:
        raise HTTPException(status_code=403, detail="无权访问此路径")
    return target


def _html_with_preview_base(content: str, base_href: str) -> str:
    base_tag = f'<base href="{escape(base_href, quote=True)}">'
    match = re.search(r"<head\b[^>]*>", content, flags=re.IGNORECASE)
    if match:
        insert_at = match.end()
        return f"{content[:insert_at]}{base_tag}{content[insert_at:]}"
    return f"{base_tag}{content}"


def _media_type_for_path(path: Path) -> str:
    media_type, _ = mimetypes.guess_type(path.name)
    if path.suffix.lower() == ".js":
        return "text/javascript"
    if path.suffix.lower() == ".css":
        return "text/css"
    return media_type or "application/octet-stream"


def _content_disposition(disposition: str, filename: str) -> str:
    safe_filename = filename.replace('"', "")
    return f'{disposition}; filename="{safe_filename}"'


def _is_html_preview_media_type(media_type: str | None) -> bool:
    return bool(media_type and media_type.split(";", 1)[0].strip().lower() == "text/html")


def _artifact_asset_base_url(artifact_id: str) -> str:
    return f"/api/artifacts/{artifact_id}/assets/"


def _file_response_headers(disposition: str, filename: str) -> dict[str, str]:
    return {
        "Content-Disposition": _content_disposition(disposition, filename),
        "X-Content-Type-Options": "nosniff",
    }


def _inline_file_response(
    target: Path,
    *,
    media_type: str,
    filename: str,
    disposition: str,
    artifact_id: str,
    asset_resolver: Callable[[str], Path] | None = None,
):
    headers = _file_response_headers(disposition, filename)
    if disposition != "attachment" and _is_html_preview_media_type(media_type):
        html = target.read_text(encoding="utf-8", errors="replace")
        if asset_resolver:
            html = inline_local_html_assets(html, asset_resolver)
        return Response(
            content=_html_with_preview_base(html, _artifact_asset_base_url(artifact_id)),
            media_type=media_type,
            headers=headers,
        )
    return FileResponse(
        target,
        media_type=media_type,
        filename=filename,
        content_disposition_type=disposition,
        headers={"X-Content-Type-Options": "nosniff"},
    )


class ArtifactRead(BaseModel):
    id: str
    session_id: str = Field(alias="sessionId")
    message_id: str = Field(alias="messageId")
    project_id: str | None = Field(default=None, alias="projectId")
    type: str
    title: str
    content: str
    status: str
    version: int
    parent_artifact_id: str | None = Field(default=None, alias="parentArtifactId")
    file_path: str | None = Field(default=None, alias="filePath")
    preview_id: str | None = Field(default=None, alias="previewId")
    source: str | None = None
    preview_kind: str = Field(alias="previewKind")
    preview_label: str = Field(alias="previewLabel")
    media_type: str | None = Field(default=None, alias="mediaType")
    file_extension: str | None = Field(default=None, alias="fileExtension")
    can_inline_preview: bool = Field(alias="canInlinePreview")
    is_binary: bool = Field(alias="isBinary")
    raw_url: str | None = Field(default=None, alias="rawUrl")
    download_url: str | None = Field(default=None, alias="downloadUrl")
    created_at: str = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_orm_with_iso(cls, obj: Artifact):
        preview = artifact_preview_payload(obj)
        return cls(
            id=obj.id, session_id=obj.session_id, message_id=obj.message_id,
            project_id=obj.project_id,
            type=obj.type, title=obj.title, content=obj.content,
            status=obj.status,
            version=obj.version or 1,
            parent_artifact_id=obj.parent_artifact_id,
            file_path=obj.file_path,
            preview_id=obj.preview_id,
            source=obj.source,
            preview_kind=str(preview["previewKind"]),
            preview_label=str(preview["previewLabel"]),
            media_type=preview["mediaType"] if isinstance(preview["mediaType"], str) else None,
            file_extension=preview["fileExtension"] if isinstance(preview["fileExtension"], str) else None,
            can_inline_preview=bool(preview["canInlinePreview"]),
            is_binary=bool(preview["isBinary"]),
            raw_url=preview["rawUrl"] if isinstance(preview["rawUrl"], str) else None,
            download_url=preview["downloadUrl"] if isinstance(preview["downloadUrl"], str) else None,
            created_at=obj.created_at.isoformat() if obj.created_at else "",
        )


class ArtifactVersionRead(BaseModel):
    id: str
    version: int
    content: str
    created_at: str = Field(alias="createdAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_artifact(cls, obj: Artifact):
        return cls(
            id=obj.id,
            version=obj.version or 1,
            content=obj.content,
            created_at=obj.created_at.isoformat() if obj.created_at else "",
        )


class DiffRead(BaseModel):
    from_version: int = Field(alias="fromVersion")
    to_version: int = Field(alias="toVersion")
    diff: str
    old_content: str = Field(alias="oldContent")
    new_content: str = Field(alias="newContent")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_result(cls, result: DiffResult):
        return cls(
            from_version=result.from_version,
            to_version=result.to_version,
            diff=result.diff,
            old_content=result.old_content,
            new_content=result.new_content,
        )


class ArtifactEditRequest(BaseModel):
    selection: str
    instruction: str
    edit_type: str = Field(default="replace", alias="editType")
    apply: bool = False
    proposed_content: str | None = Field(default=None, alias="proposedContent")

    model_config = {"populate_by_name": True}


class ArtifactEditRead(BaseModel):
    new_version: int | None = Field(default=None, alias="newVersion")
    diff: DiffRead
    artifact: ArtifactRead | None = None
    proposed_content: str = Field(alias="proposedContent")
    strategy: str

    model_config = {"populate_by_name": True}


class ArtifactSaveRequest(BaseModel):
    content: str
    title: str | None = None
    write_workspace: bool = Field(default=True, alias="writeWorkspace")

    model_config = {"populate_by_name": True}


class ArtifactRestoreRequest(BaseModel):
    version: int
    write_workspace: bool = Field(default=True, alias="writeWorkspace")

    model_config = {"populate_by_name": True}


@router.get("/sessions/{session_id}/artifacts", response_model=List[ArtifactRead])
async def list_artifacts(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _authorize_session(request, db, session_id, "read")
    artifacts = await _artifact_svc(db).list_current_artifacts(session_id)
    return [ArtifactRead.from_orm_with_iso(a) for a in artifacts]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactRead)
async def get_artifact(artifact_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    artifact = await _authorize_artifact(request, db, artifact_id, "read")
    return ArtifactRead.from_orm_with_iso(artifact)


@router.get("/artifacts/{artifact_id}/raw")
async def get_artifact_raw(
    artifact_id: str,
    request: Request,
    download: bool = False,
    db: AsyncSession = Depends(get_db),
):
    artifact = await _authorize_artifact(request, db, artifact_id, "read")
    preview = infer_artifact_preview(
        artifact_type=artifact.type,
        title=artifact.title,
        content=artifact.content,
        file_path=artifact.file_path,
    )
    filename = Path(artifact.file_path or artifact.title or "artifact").name
    disposition = "attachment" if download else "inline"

    if artifact.file_path and artifact.project_id:
        project = await db.get(Project, artifact.project_id)
        if project:
            target = _artifact_file_target(project, artifact.file_path)
            if target.exists() and target.is_file():
                return _inline_file_response(
                    target,
                    media_type=preview.media_type or "application/octet-stream",
                    filename=filename,
                    disposition=disposition,
                    artifact_id=artifact.id,
                    asset_resolver=lambda asset_path: _artifact_asset_target(
                        project,
                        artifact.file_path or "",
                        asset_path,
                    ),
                )

    headers = {}
    if download:
        headers["Content-Disposition"] = _content_disposition("attachment", filename)
    elif _is_html_preview_media_type(preview.media_type):
        headers["X-Content-Type-Options"] = "nosniff"
        return Response(
            content=_html_with_preview_base(artifact.content, _artifact_asset_base_url(artifact.id)),
            media_type=preview.media_type or "text/html",
            headers=headers,
        )
    return Response(
        content=artifact.content,
        media_type=preview.media_type or "text/plain",
        headers=headers,
    )


@router.get("/artifacts/{artifact_id}/assets/{asset_path:path}")
async def get_artifact_asset(
    artifact_id: str,
    asset_path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    artifact = await _authorize_artifact(request, db, artifact_id, "read")
    if not artifact.file_path or not artifact.project_id:
        raise HTTPException(status_code=404, detail="artifact asset not found")
    project = await db.get(Project, artifact.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    target = _artifact_asset_target(project, artifact.file_path, asset_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="artifact asset not found")
    return FileResponse(
        target,
        media_type=_media_type_for_path(target),
        filename=target.name,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/artifacts/{artifact_id}/versions", response_model=List[ArtifactVersionRead])
async def get_artifact_versions(artifact_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await _authorize_artifact(request, db, artifact_id, "read")
        versions = await _artifact_svc(db).get_versions(artifact_id)
    except ArtifactNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return [ArtifactVersionRead.from_artifact(a) for a in versions]


@router.get("/artifacts/{artifact_id}/diff", response_model=DiffRead)
async def get_artifact_diff(
    artifact_id: str,
    v1: int,
    v2: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_artifact(request, db, artifact_id, "read")
        result = await _artifact_svc(db).get_diff(artifact_id, v1, v2)
    except ArtifactNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    except ArtifactVersionNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact version not found")
    return DiffRead.from_result(result)


@router.post("/artifacts/{artifact_id}/edit", response_model=ArtifactEditRead)
async def edit_artifact(
    artifact_id: str,
    data: ArtifactEditRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_artifact(request, db, artifact_id, "write")
        result = await _artifact_svc(db).apply_edit(
            artifact_id=artifact_id,
            selection=data.selection,
            instruction=data.instruction,
            edit_type=data.edit_type,
            proposed_content=data.proposed_content,
            apply=data.apply,
        )
    except ArtifactNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    except ArtifactEditError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    artifact = ArtifactRead.from_orm_with_iso(result.artifact) if result.artifact else None
    return ArtifactEditRead(
        new_version=result.artifact.version if result.artifact else None,
        diff=DiffRead.from_result(result.diff),
        artifact=artifact,
        proposed_content=result.proposed_content,
        strategy=result.strategy,
    )


@router.post("/artifacts/{artifact_id}/save", response_model=ArtifactRead)
async def save_artifact_content(
    artifact_id: str,
    data: ArtifactSaveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_artifact(request, db, artifact_id, "write")
        artifact = await _artifact_svc(db).save_content(
            artifact_id,
            data.content,
            title=data.title,
            write_workspace=data.write_workspace,
        )
    except ArtifactNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    except ArtifactWorkspaceWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ArtifactRead.from_orm_with_iso(artifact)


@router.post("/artifacts/{artifact_id}/restore", response_model=ArtifactRead)
async def restore_artifact_version(
    artifact_id: str,
    data: ArtifactRestoreRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await _authorize_artifact(request, db, artifact_id, "write")
        artifact = await _artifact_svc(db).restore_version(
            artifact_id,
            data.version,
            write_workspace=data.write_workspace,
        )
    except ArtifactNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    except ArtifactVersionNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact version not found")
    except ArtifactWorkspaceWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ArtifactRead.from_orm_with_iso(artifact)
