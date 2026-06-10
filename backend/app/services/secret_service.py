"""Phase 10 Secret 存储、注入与日志脱敏。"""

from __future__ import annotations

import base64
import hashlib
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Project, Secret, User
from .phase10_schemas import SecretCreate, SecretRefRead
from .team_service import PermissionDeniedError, TeamService


SECRET_ENV_NAME = re.compile(r"[^A-Za-z0-9_]+")


class SecretValidationError(ValueError):
    pass


class SecretService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.team_service = TeamService(db)

    async def create_secret(self, data: SecretCreate, actor: User) -> SecretRefRead:
        name = _normalize_secret_name(data.name)
        if not data.value:
            raise SecretValidationError("secret value must not be empty")
        scope, owner_id = await self._resolve_owner(data, actor)
        encrypted = _encrypt(data.value)

        result = await self.db.execute(
            select(Secret).where(
                Secret.scope == scope,
                Secret.owner_id == owner_id,
                Secret.name == name,
            )
        )
        secret = result.scalars().first()
        if secret:
            secret.encrypted_value = encrypted
        else:
            secret = Secret(
                id=str(uuid.uuid4()),
                scope=scope,
                owner_id=owner_id,
                name=name,
                encrypted_value=encrypted,
            )
            self.db.add(secret)
        await self.db.commit()
        await self.db.refresh(secret)
        return secret_to_read(secret)

    async def env_for_project(self, *, actor: User, project: Project) -> dict[str, str]:
        secrets = await self._visible_secrets(actor=actor, project=project)
        return {secret.name: _decrypt(secret.encrypted_value) for secret in secrets}

    async def redactor_for_project(self, *, actor: User, project: Project) -> "SecretRedactor":
        env = await self.env_for_project(actor=actor, project=project)
        return SecretRedactor(list(env.values()))

    async def _visible_secrets(self, *, actor: User, project: Project) -> list[Secret]:
        owner_ids = [("user", actor.id)]
        if project.team_id:
            try:
                await self.team_service.role_for_user(project.team_id, actor.id)
                owner_ids.append(("team", project.team_id))
            except PermissionDeniedError:
                pass
        if project.id:
            owner_ids.append(("project", project.id))

        result = await self.db.execute(
            select(Secret).where(
                tuple_filter(Secret.scope, Secret.owner_id, owner_ids)
            )
        )
        return list(result.scalars().all())

    async def _resolve_owner(self, data: SecretCreate, actor: User) -> tuple[str, str]:
        if data.scope == "user":
            return "user", actor.id
        owner_id = (data.owner_id or "").strip()
        if not owner_id:
            raise SecretValidationError("ownerId is required for team/project secret")
        if data.scope == "team":
            await self.team_service.assert_team_admin(owner_id, actor.id)
        if data.scope == "project":
            project = await self.db.get(Project, owner_id)
            if not project:
                raise SecretValidationError("project not found")
            await self.team_service.assert_workspace_write_allowed(project, actor)
        return data.scope, owner_id


@dataclass
class SecretRedactor:
    values: list[str]

    def redact(self, text: str | None) -> str:
        result = str(text or "")
        for value in sorted((item for item in self.values if item), key=len, reverse=True):
            if len(value) < 3:
                continue
            result = result.replace(value, "[REDACTED]")
        return result


def secret_to_read(secret: Secret) -> SecretRefRead:
    return SecretRefRead(
        id=secret.id,
        name=secret.name,
        scope=secret.scope,
        owner_id=secret.owner_id,
        created_at=secret.created_at,
    )


def tuple_filter(scope_column, owner_column, pairs: list[tuple[str, str]]):
    from sqlalchemy import or_

    return or_(*[
        (scope_column == scope) & (owner_column == owner_id)
        for scope, owner_id in pairs
    ])


def _normalize_secret_name(name: str) -> str:
    clean = SECRET_ENV_NAME.sub("_", (name or "").strip()).strip("_").upper()
    if not clean:
        raise SecretValidationError("secret name must not be empty")
    if clean[0].isdigit():
        clean = f"SECRET_{clean}"
    return clean


def _key_stream(length: int) -> bytes:
    seed = hashlib.sha256(settings.agenthub_secret_key.encode("utf-8")).digest()
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(hashlib.sha256(seed + str(counter).encode("ascii")).digest())
        counter += 1
    return bytes(output[:length])


def _encrypt(value: str) -> str:
    raw = value.encode("utf-8")
    stream = _key_stream(len(raw))
    encrypted = bytes(a ^ b for a, b in zip(raw, stream))
    return "v1:" + base64.urlsafe_b64encode(encrypted).decode("ascii")


def _decrypt(value: str) -> str:
    payload = value[3:] if value.startswith("v1:") else value
    raw = base64.urlsafe_b64decode(payload.encode("ascii"))
    stream = _key_stream(len(raw))
    decrypted = bytes(a ^ b for a, b in zip(raw, stream))
    return decrypted.decode("utf-8", errors="replace")
