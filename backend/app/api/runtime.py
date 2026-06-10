from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.phase10_schemas import RuntimeImageListRead, RunnerNodeListRead
from ..services.runner_provider import list_runtime_images, list_runner_nodes
from .auth import require_current_user

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/images", response_model=RuntimeImageListRead)
async def get_runtime_images(user: User = Depends(require_current_user)):
    del user
    return list_runtime_images()


@router.get("/runner-nodes", response_model=RunnerNodeListRead)
async def get_runner_nodes(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    del user
    return await list_runner_nodes(db)
