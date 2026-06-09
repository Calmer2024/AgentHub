"""Phase 14 生产 Auth 与租户边界 API 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .phase9_schemas import CurrentUserRead, TeamRead


class AuthProviderRead(BaseModel):
    id: str
    label: str
    type: Literal["email", "external", "dev_header"] = "email"
    enabled: bool
    dev_only: bool = Field(default=False, alias="devOnly")

    model_config = {"populate_by_name": True}


class AuthProvidersRead(BaseModel):
    items: list[AuthProviderRead]


class AuthLoginRequest(BaseModel):
    email: str
    password: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    provider: str | None = None

    model_config = {"populate_by_name": True}

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        clean = value.strip().lower()
        if "@" not in clean or clean.startswith("@") or clean.endswith("@"):
            raise ValueError("email must be valid")
        return clean


class AuthRefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, alias="refreshToken")

    model_config = {"populate_by_name": True}


class AuthLogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, alias="refreshToken")

    model_config = {"populate_by_name": True}


class AuthDefaultSpaceRead(BaseModel):
    kind: Literal["personal", "team"] = "personal"
    id: str
    name: str


class AuthMeRead(CurrentUserRead):
    status: str = "active"
    last_login_at: datetime | None = Field(default=None, alias="lastLoginAt")
    teams: list[TeamRead] = Field(default_factory=list)
    default_space: AuthDefaultSpaceRead = Field(alias="defaultSpace")

    model_config = {"populate_by_name": True, "from_attributes": True}


class AuthTokenRead(BaseModel):
    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    token_type: Literal["bearer"] = Field(default="bearer", alias="tokenType")
    expires_at: datetime = Field(alias="expiresAt")
    user: AuthMeRead

    model_config = {"populate_by_name": True}
