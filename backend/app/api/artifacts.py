from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Artifact
from ..services.artifact_service import (
    ArtifactEditError,
    ArtifactNotFoundError,
    ArtifactService,
    ArtifactVersionNotFoundError,
    ArtifactWorkspaceWriteError,
    DiffResult,
)

router = APIRouter(prefix="", tags=["artifacts"])


def _artifact_svc(db: AsyncSession) -> ArtifactService:
    from ..main import _event_bus
    return ArtifactService(db, event_bus=_event_bus)


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
    created_at: str = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_orm_with_iso(cls, obj: Artifact):
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
async def list_artifacts(session_id: str, db: AsyncSession = Depends(get_db)):
    artifacts = await _artifact_svc(db).list_current_artifacts(session_id)
    return [ArtifactRead.from_orm_with_iso(a) for a in artifacts]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactRead)
async def get_artifact(artifact_id: str, db: AsyncSession = Depends(get_db)):
    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return ArtifactRead.from_orm_with_iso(artifact)


@router.get("/artifacts/{artifact_id}/versions", response_model=List[ArtifactVersionRead])
async def get_artifact_versions(artifact_id: str, db: AsyncSession = Depends(get_db)):
    try:
        versions = await _artifact_svc(db).get_versions(artifact_id)
    except ArtifactNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return [ArtifactVersionRead.from_artifact(a) for a in versions]


@router.get("/artifacts/{artifact_id}/diff", response_model=DiffRead)
async def get_artifact_diff(
    artifact_id: str,
    v1: int,
    v2: int,
    db: AsyncSession = Depends(get_db),
):
    try:
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
    db: AsyncSession = Depends(get_db),
):
    try:
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
    db: AsyncSession = Depends(get_db),
):
    try:
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
    db: AsyncSession = Depends(get_db),
):
    try:
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
