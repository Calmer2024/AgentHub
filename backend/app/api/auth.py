from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.auth_service import AuthRequiredError, AuthService
from ..services.phase9_schemas import CurrentUserRead

router = APIRouter(prefix="/auth", tags=["auth"])


async def require_user_from_header_values(
    db: AsyncSession,
    email: str | None,
    display_name: str | None = None,
    avatar_url: str | None = None,
) -> User:
    try:
        return await AuthService(db).require_user(
            email,
            display_name=display_name,
            avatar_url=avatar_url,
        )
    except AuthRequiredError:
        raise HTTPException(status_code=401, detail="请先登录后继续")


async def require_current_user(
    db: AsyncSession = Depends(get_db),
    x_agenthub_user_email: str | None = Header(default=None),
    x_agenthub_user_name: str | None = Header(default=None),
    x_agenthub_user_avatar: str | None = Header(default=None),
) -> User:
    return await require_user_from_header_values(
        db,
        x_agenthub_user_email,
        display_name=x_agenthub_user_name,
        avatar_url=x_agenthub_user_avatar,
    )


@router.get("/me", response_model=CurrentUserRead)
async def get_current_user(user: User = Depends(require_current_user)):
    return CurrentUserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )
