from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.phase10_schemas import QuotaSummaryRead
from ..services.quota_service import QuotaService
from .auth import require_current_user

router = APIRouter(prefix="/quotas", tags=["quotas"])


@router.get("/me", response_model=QuotaSummaryRead)
async def get_my_quota(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    return await QuotaService(db).summary(user)
