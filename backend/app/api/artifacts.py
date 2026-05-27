from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Artifact

router = APIRouter(prefix="", tags=["artifacts"])


class ArtifactRead(BaseModel):
    id: str
    session_id: str = Field(alias="sessionId")
    message_id: str = Field(alias="messageId")
    type: str
    title: str
    content: str
    status: str
    created_at: str = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_orm_with_iso(cls, obj: Artifact):
        return cls(
            id=obj.id, session_id=obj.session_id, message_id=obj.message_id,
            type=obj.type, title=obj.title, content=obj.content,
            status=obj.status, created_at=obj.created_at.isoformat() if obj.created_at else "",
        )


@router.get("/sessions/{session_id}/artifacts", response_model=List[ArtifactRead])
async def list_artifacts(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Artifact).where(Artifact.session_id == session_id).order_by(Artifact.created_at.desc())
    )
    return [ArtifactRead.from_orm_with_iso(a) for a in result.scalars().all()]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactRead)
async def get_artifact(artifact_id: str, db: AsyncSession = Depends(get_db)):
    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Artifact not found")
    return ArtifactRead.from_orm_with_iso(artifact)
