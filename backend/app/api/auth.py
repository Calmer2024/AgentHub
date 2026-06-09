from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.auth_service import (
    AuthInvalidError,
    AuthRequiredError,
    AuthService,
    auth_token_to_read,
    cloud_auth_required,
    dev_header_auth_enabled,
)
from ..services.phase14_schemas import (
    AuthDefaultSpaceRead,
    AuthLoginRequest,
    AuthLogoutRequest,
    AuthMeRead,
    AuthProviderRead,
    AuthProvidersRead,
    AuthRefreshRequest,
    AuthTokenRead,
)
from ..services.team_service import TeamService

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


async def optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    return await AuthService(db).resolve_request(request)


async def require_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        return await AuthService(db).require_request_user(request)
    except AuthRequiredError:
        raise HTTPException(status_code=401, detail="请先登录后继续")


async def require_current_user_or_dev_header(
    request: Request,
    db: AsyncSession,
    x_agenthub_user_email: str | None = Header(default=None),
    x_agenthub_user_name: str | None = Header(default=None),
    x_agenthub_user_avatar: str | None = Header(default=None),
) -> User:
    user = await AuthService(db).resolve_request(request)
    if user:
        return user
    return await require_user_from_header_values(
        db,
        x_agenthub_user_email,
        display_name=x_agenthub_user_name,
        avatar_url=x_agenthub_user_avatar,
    )


@router.get("/providers", response_model=AuthProvidersRead)
async def list_auth_providers():
    items = [
        AuthProviderRead(
            id="local_email",
            label="邮箱登录",
            type="email",
            enabled=True,
            dev_only=False,
        )
    ]
    if dev_header_auth_enabled():
        items.append(AuthProviderRead(
            id="dev_header",
            label="开发态请求头",
            type="dev_header",
            enabled=True,
            dev_only=True,
        ))
    return AuthProvidersRead(items=items)


@router.post("/login", response_model=AuthTokenRead)
async def login(
    data: AuthLoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await AuthService(db).login(
            email=data.email,
            display_name=data.display_name,
            avatar_url=data.avatar_url,
            provider=data.provider or "local_email",
            request=request,
        )
    except AuthInvalidError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    read = await _me_read(db, result.user)
    _set_auth_cookies(response, result.access_token, result.refresh_token)
    return auth_token_to_read(result, read)


@router.post("/refresh", response_model=AuthTokenRead)
async def refresh(
    response: Response,
    request: Request,
    data: AuthRefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await AuthService(db).refresh(
            data.refresh_token if data else None,
            request,
        )
    except AuthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    read = await _me_read(db, result.user)
    _set_auth_cookies(response, result.access_token, result.refresh_token)
    return auth_token_to_read(result, read)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    request: Request,
    data: AuthLogoutRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    await AuthService(db).logout(
        request=request,
        refresh_token=data.refresh_token if data else None,
    )
    response.delete_cookie("agenthub_access_token")
    response.delete_cookie("agenthub_refresh_token")


@router.get("/me", response_model=AuthMeRead)
async def get_current_user(user: User = Depends(require_current_user), db: AsyncSession = Depends(get_db)):
    return await _me_read(db, user)


async def _me_read(db: AsyncSession, user: User) -> AuthMeRead:
    teams = await TeamService(db).list_teams(user)
    default_team = teams[0] if teams else None
    default_space = AuthDefaultSpaceRead(
        kind="team" if default_team else "personal",
        id=default_team.id if default_team else user.id,
        name=default_team.name if default_team else "个人空间",
    )
    return AuthMeRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        status=user.status,
        last_login_at=user.last_login_at,
        teams=teams,
        default_space=default_space,
    )


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    from ..config import settings

    response.set_cookie(
        "agenthub_access_token",
        access_token,
        httponly=True,
        secure=settings.agenthub_cookie_secure,
        samesite="lax",
        max_age=settings.agenthub_access_token_seconds,
    )
    response.set_cookie(
        "agenthub_refresh_token",
        refresh_token,
        httponly=True,
        secure=settings.agenthub_cookie_secure,
        samesite="lax",
        max_age=settings.agenthub_refresh_token_days * 24 * 60 * 60,
    )


def cloud_login_required() -> bool:
    return cloud_auth_required()
