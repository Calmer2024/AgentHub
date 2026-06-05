from fastapi import APIRouter
from pydantic import BaseModel

from ..domain.skill_registry import SkillRegistry

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillRead(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str]
    source: str
    path: str | None = None


@router.get("", response_model=list[SkillRead])
async def list_skills():
    return [skill.to_api() for skill in SkillRegistry().list()]
