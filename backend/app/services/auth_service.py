"""Phase 14 AuthProvider、生产 session token 与开发态 mock auth。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.timezone import china_now
from ..models import AuthIdentity, AuthSession, User
from .audit_service import AuditService
from .phase14_schemas import AuthTokenRead


class AuthRequiredError(PermissionError):
    pass


class AuthInvalidError(AuthRequiredError):
    pass


@dataclass(frozen=True)
class AuthSubject:
    provider: str
    subject: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None


@dataclass(frozen=True)
class AuthSessionResult:
    user: User
    session: AuthSession
    access_token: str
    refresh_token: str
    expires_at: datetime


class AuthProvider(Protocol):
    async def resolve_request(self, request: Request) -> AuthSubject | None:
        ...


def dev_header_auth_enabled() -> bool:
    """开发请求头只能在显式开发配置下启用，生产环境一律关闭。"""
    return (
        bool(settings.agenthub_dev_auth_enabled)
        and settings.agenthub_environment.lower() != "production"
    )


def cloud_auth_required() -> bool:
    edition = settings.agenthub_edition.lower()
    surface = settings.agenthub_surface.lower()
    return bool(settings.agenthub_auth_required or edition == "saas" or surface == "mobile")


class DevHeaderAuthProvider:
    async def resolve_request(self, request: Request) -> AuthSubject | None:
        if not dev_header_auth_enabled():
            return None
        email = (request.headers.get("x-agenthub-user-email") or "").strip().lower()
        if not email:
            return None
        return AuthSubject(
            provider="dev_header",
            subject=email,
            email=email,
            display_name=request.headers.get("x-agenthub-user-name"),
            avatar_url=request.headers.get("x-agenthub-user-avatar"),
        )


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)
        self.dev_provider = DevHeaderAuthProvider()

    async def resolve_request(self, request: Request) -> User | None:
        token = _access_token_from_request(request)
        if token:
            user = await self._resolve_access_token(token)
            if user:
                return user

        subject = await self.dev_provider.resolve_request(request)
        if subject:
            return await self.get_or_create_identity_user(subject)
        return None

    async def require_request_user(self, request: Request) -> User:
        user = await self.resolve_request(request)
        if not user:
            raise AuthRequiredError("not authenticated")
        return user

    async def require_user(
        self,
        email: str | None,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        if not dev_header_auth_enabled():
            raise AuthRequiredError("dev header auth is disabled")
        clean_email = (email or "").strip().lower()
        if not clean_email:
            raise AuthRequiredError("not authenticated")
        return await self.get_or_create_identity_user(AuthSubject(
            provider="dev_header",
            subject=clean_email,
            email=clean_email,
            display_name=display_name,
            avatar_url=avatar_url,
        ))

    async def login(
        self,
        *,
        email: str,
        display_name: str | None,
        avatar_url: str | None,
        request: Request,
        provider: str = "local_email",
    ) -> AuthSessionResult:
        clean_provider = (provider or settings.agenthub_auth_provider or "local_email").strip()
        if clean_provider != "local_email":
            raise AuthInvalidError("auth provider is not enabled")
        subject = AuthSubject(
            provider=clean_provider,
            subject=email.strip().lower(),
            email=email.strip().lower(),
            display_name=display_name,
            avatar_url=avatar_url,
        )
        user = await self.get_or_create_identity_user(subject, commit=False)
        refresh_token = secrets.token_urlsafe(48)
        now = china_now()
        auth_session = AuthSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            refresh_token_hash=_hash_refresh_token(refresh_token),
            user_agent=request.headers.get("user-agent"),
            ip_hash=_hash_ip(request.client.host if request.client else None),
            expires_at=now + timedelta(days=settings.agenthub_refresh_token_days),
            created_at=now,
        )
        self.db.add(auth_session)
        await self.audit.record(
            actor_user_id=user.id,
            action="auth.login",
            resource_type="auth_session",
            resource_id=auth_session.id,
            metadata={"provider": clean_provider},
        )
        await self.db.commit()
        await self.db.refresh(user)
        await self.db.refresh(auth_session)
        access_token, expires_at = _make_access_token(auth_session)
        return AuthSessionResult(
            user=user,
            session=auth_session,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

    async def refresh(self, refresh_token: str | None, request: Request) -> AuthSessionResult:
        clean = (refresh_token or _refresh_token_from_request(request) or "").strip()
        if not clean:
            raise AuthRequiredError("refresh token required")
        result = await self.db.execute(
            select(AuthSession).where(AuthSession.refresh_token_hash == _hash_refresh_token(clean))
        )
        auth_session = result.scalars().first()
        if not auth_session or auth_session.revoked_at or auth_session.expires_at <= china_now():
            raise AuthInvalidError("refresh token expired")
        user = await self.db.get(User, auth_session.user_id)
        if not user or user.status != "active":
            raise AuthInvalidError("user disabled")

        new_refresh = secrets.token_urlsafe(48)
        auth_session.refresh_token_hash = _hash_refresh_token(new_refresh)
        await self.audit.record(
            actor_user_id=user.id,
            action="auth.refresh",
            resource_type="auth_session",
            resource_id=auth_session.id,
        )
        await self.db.commit()
        access_token, expires_at = _make_access_token(auth_session)
        return AuthSessionResult(
            user=user,
            session=auth_session,
            access_token=access_token,
            refresh_token=new_refresh,
            expires_at=expires_at,
        )

    async def logout(
        self,
        *,
        request: Request,
        refresh_token: str | None = None,
    ) -> None:
        auth_session = None
        token = _access_token_from_request(request)
        if token:
            payload = _decode_access_token(token)
            session_id = payload.get("sid") if payload else None
            auth_session = await self.db.get(AuthSession, session_id) if session_id else None
        if not auth_session and refresh_token:
            result = await self.db.execute(
                select(AuthSession).where(
                    AuthSession.refresh_token_hash == _hash_refresh_token(refresh_token)
                )
            )
            auth_session = result.scalars().first()
        if not auth_session:
            return
        if not auth_session.revoked_at:
            auth_session.revoked_at = china_now()
            await self.audit.record(
                actor_user_id=auth_session.user_id,
                action="auth.logout",
                resource_type="auth_session",
                resource_id=auth_session.id,
            )
            await self.db.commit()

    async def get_or_create_user(
        self,
        email: str,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        return await self.get_or_create_identity_user(AuthSubject(
            provider="local_email",
            subject=email.strip().lower(),
            email=email.strip().lower(),
            display_name=display_name,
            avatar_url=avatar_url,
        ))

    async def get_or_create_identity_user(
        self,
        subject: AuthSubject,
        *,
        commit: bool = True,
    ) -> User:
        clean_email = subject.email.strip().lower()
        result = await self.db.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == subject.provider,
                AuthIdentity.subject == subject.subject,
            )
        )
        identity = result.scalars().first()
        now = china_now()
        if identity:
            user = await self.db.get(User, identity.user_id)
            if not user or user.status != "active":
                raise AuthInvalidError("user disabled")
            identity.last_login_at = now
            user.last_login_at = now
            if commit:
                await self.db.commit()
                await self.db.refresh(user)
            return user

        result = await self.db.execute(
            select(User).where(func.lower(User.email) == clean_email)
        )
        user = result.scalars().first()
        if not user:
            name = (subject.display_name or "").strip() or clean_email.split("@")[0] or "AgentHub 用户"
            user = User(
                id=str(uuid.uuid4()),
                email=clean_email,
                display_name=name,
                avatar_url=subject.avatar_url,
                status="active",
                last_login_at=now,
            )
            self.db.add(user)
            await self.db.flush()
        else:
            user.last_login_at = now
            if subject.display_name and not user.display_name:
                user.display_name = subject.display_name
            if subject.avatar_url and not user.avatar_url:
                user.avatar_url = subject.avatar_url

        identity = AuthIdentity(
            id=str(uuid.uuid4()),
            user_id=user.id,
            provider=subject.provider,
            subject=subject.subject,
            email=clean_email,
            created_at=now,
            last_login_at=now,
        )
        self.db.add(identity)
        if commit:
            await self.db.commit()
            await self.db.refresh(user)
        return user

    async def _resolve_access_token(self, token: str) -> User | None:
        payload = _decode_access_token(token)
        if not payload:
            return None
        session_id = str(payload.get("sid") or "")
        user_id = str(payload.get("uid") or "")
        exp = int(payload.get("exp") or 0)
        if not session_id or not user_id or exp <= int(china_now().timestamp()):
            return None
        auth_session = await self.db.get(AuthSession, session_id)
        if (
            not auth_session
            or auth_session.user_id != user_id
            or auth_session.revoked_at
            or auth_session.expires_at <= china_now()
        ):
            return None
        user = await self.db.get(User, user_id)
        if not user or user.status != "active":
            return None
        return user


def auth_token_to_read(result: AuthSessionResult, user_read) -> AuthTokenRead:
    return AuthTokenRead(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_at=result.expires_at,
        user=user_read,
    )


def _access_token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("agenthub_access_token")


def _refresh_token_from_request(request: Request) -> str | None:
    return request.cookies.get("agenthub_refresh_token")


def _make_access_token(auth_session: AuthSession) -> tuple[str, datetime]:
    expires_at = china_now() + timedelta(seconds=settings.agenthub_access_token_seconds)
    payload = {
        "sid": auth_session.id,
        "uid": auth_session.user_id,
        "exp": int(expires_at.timestamp()),
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = _sign(body.encode("ascii"))
    return f"{body}.{sig}", expires_at


def _decode_access_token(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 2:
        return None
    body, sig = parts
    expected = _sign(body.encode("ascii"))
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        raw = base64.urlsafe_b64decode(_pad_b64(body))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(f"{settings.agenthub_secret_key}:{token}".encode("utf-8")).hexdigest()


def _hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(f"{settings.agenthub_secret_key}:ip:{ip}".encode("utf-8")).hexdigest()


def _sign(data: bytes) -> str:
    digest = hmac.new(settings.agenthub_secret_key.encode("utf-8"), data, hashlib.sha256).digest()
    return _b64(digest)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _pad_b64(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode("ascii")
