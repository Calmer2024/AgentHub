from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.phase10_schemas import SecretCreate, SecretRefRead
from ..services.secret_service import SecretService, SecretValidationError
from .auth import require_current_user

router = APIRouter(prefix="/secrets", tags=["secrets"])


@router.post("", response_model=SecretRefRead, status_code=201)
async def create_secret(
    data: SecretCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return await SecretService(db).create_secret(data, user)
    except SecretValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
