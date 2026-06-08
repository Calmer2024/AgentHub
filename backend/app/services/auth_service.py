"""Phase 9 开发态登录态服务。

P2 最终会接真实 Auth Provider；Phase 9 先用请求头建立可持久化用户，
同时保持缺少登录态时返回 401 的契约。
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User


class AuthRequiredError(PermissionError):
    pass


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def require_user(
        self,
        email: str | None,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        clean_email = (email or "").strip().lower()
        if not clean_email:
            raise AuthRequiredError("not authenticated")
        return await self.get_or_create_user(clean_email, display_name, avatar_url)

    async def get_or_create_user(
        self,
        email: str,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        clean_email = email.strip().lower()
        result = await self.db.execute(
            select(User).where(func.lower(User.email) == clean_email)
        )
        user = result.scalars().first()
        if user:
            return user

        name = (display_name or "").strip() or clean_email.split("@")[0] or "AgentHub 用户"
        user = User(
            id=str(uuid.uuid4()),
            email=clean_email,
            display_name=name,
            avatar_url=avatar_url,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user
