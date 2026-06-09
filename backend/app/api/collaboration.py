from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.approval_service import ApprovalNotFoundError, InvalidApprovalStateError, approval_to_read
from ..services.collaboration_service import (
    AttachmentTooLargeError,
    CollaborationNotFoundError,
    CollaborationService,
    CollaborationValidationError,
    UnsupportedAttachmentTypeError,
    git_job_to_read,
)
from ..services.phase12_schemas import (
    AgentTemplateFinalize,
    AgentTemplateSessionCreate,
    AgentTemplateSessionRead,
    AttachmentRead,
    CommentCreate,
    CommentListRead,
    CommentRead,
    GitSyncCreate,
    GitSyncJobRead,
    MessageForwardRead,
    MessageForwardRequest,
    MobileApprovalDecision,
    MobileSessionSummary,
    NotificationListRead,
    RenderedArtifactRead,
)
from ..services.runtime_schemas import ApprovalCheckpointRead
from ..services.team_service import PermissionDeniedError
from .agents import AgentConfigRead
from .auth import require_current_user

router = APIRouter(prefix="", tags=["collaboration"])


def _svc(db: AsyncSession) -> CollaborationService:
    from ..main import _event_bus
    return CollaborationService(db, event_bus=_event_bus)


@router.post("/projects/{project_id}/comments", response_model=CommentRead, status_code=201)
async def create_comment(
    project_id: str,
    data: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).create_comment(
            project_id,
            target_type=data.target_type,
            target_id=data.target_id,
            body=data.body,
            actor=user,
        )
    except CollaborationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except CollaborationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/projects/{project_id}/comments", response_model=CommentListRead)
async def list_comments(
    project_id: str,
    targetType: str | None = Query(default=None),
    targetId: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        items = await _svc(db).list_comments(
            project_id,
            target_type=targetType,
            target_id=targetId,
            actor=user,
        )
        return CommentListRead(items=items)
    except CollaborationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/attachments", response_model=AttachmentRead, status_code=201)
async def upload_attachment(
    projectId: str = Form(...),
    sessionId: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    content = await file.read()
    try:
        return await _svc(db).create_attachment(
            project_id=projectId,
            session_id=sessionId,
            filename=file.filename or "attachment",
            mime_type=file.content_type or "application/octet-stream",
            content=content,
            actor=user,
        )
    except UnsupportedAttachmentTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except AttachmentTooLargeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CollaborationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except CollaborationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/messages/{message_id}/forward", response_model=MessageForwardRead, status_code=201)
async def forward_message(
    message_id: str,
    data: MessageForwardRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        messages, references = await _svc(db).forward_message(
            message_id,
            target_session_ids=data.target_session_ids,
            include_artifacts=data.include_artifacts,
            actor=user,
        )
        return MessageForwardRead(messages=messages, artifactReferences=references)
    except CollaborationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except CollaborationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/notifications", response_model=NotificationListRead)
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    return NotificationListRead(items=await _svc(db).list_notifications(user))


@router.post("/notifications/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        await _svc(db).mark_notification_read(notification_id, user)
    except CollaborationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/mobile/sessions", response_model=list[MobileSessionSummary])
async def mobile_sessions(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    return await _svc(db).mobile_sessions(user)


@router.post("/mobile/approvals/{approval_id}/decision", response_model=ApprovalCheckpointRead, status_code=202)
async def mobile_approval_decision(
    approval_id: str,
    data: MobileApprovalDecision,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        checkpoint = await _svc(db).decide_mobile_approval(
            approval_id,
            decision=data.decision,
            comment=data.comment,
            actor=user,
        )
        return approval_to_read(checkpoint)
    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="approval not found")
    except InvalidApprovalStateError:
        raise HTTPException(status_code=409, detail="APPROVAL_ALREADY_DECIDED")
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/artifacts/{artifact_id}/render", response_model=RenderedArtifactRead)
async def render_artifact(
    artifact_id: str,
    format: str = Query("html"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).render_artifact(artifact_id, fmt=format, actor=user)
    except CollaborationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except CollaborationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/agent-template-sessions", response_model=AgentTemplateSessionRead, status_code=201)
async def create_agent_template_session(
    data: AgentTemplateSessionCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).create_agent_template_session(data.seed_prompt, user)
    except CollaborationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/agent-template-sessions/{session_id}/finalize", response_model=AgentConfigRead, status_code=201)
async def finalize_agent_template_session(
    session_id: str,
    data: AgentTemplateFinalize,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        agent = await _svc(db).finalize_agent_template(session_id, name=data.name, engine=data.engine, actor=user)
        return AgentConfigRead.from_model(agent)
    except CollaborationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CollaborationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/projects/{project_id}/git/sync", response_model=GitSyncJobRead, status_code=202)
async def create_git_sync_job(
    project_id: str,
    data: GitSyncCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_current_user),
):
    try:
        return await _svc(db).create_git_sync_job(
            project_id,
            remote=data.remote,
            branch=data.branch,
            mode=data.mode,
            actor=user,
        )
    except CollaborationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except CollaborationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
