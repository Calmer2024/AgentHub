from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..services.cli_credential_schemas import (
    CliCredentialConfigRead,
    CliCredentialListRead,
    CliCredentialUpsert,
    CliModelListRead,
    CliTool,
)
from ..services.cli_credential_service import CliCredentialError, CliCredentialService
from .auth import require_current_user

router = APIRouter(prefix="/cli-credentials", tags=["cli-credentials"])


@router.get("", response_model=CliCredentialListRead)
async def list_cli_credentials(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    return await CliCredentialService(db).list_for_user(user)


@router.get("/{cli_tool}/models", response_model=CliModelListRead)
async def list_cli_credential_models(
    cli_tool: CliTool,
    providerId: str = "openai",
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_current_user),
):
    return await CliCredentialService(db).list_models(cli_tool, providerId)


@router.put("/{cli_tool}", response_model=CliCredentialConfigRead)
async def save_cli_credential(
    cli_tool: CliTool,
    data: CliCredentialUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        return await CliCredentialService(db).save(cli_tool, data, user)
    except CliCredentialError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
