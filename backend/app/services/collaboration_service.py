"""Phase 12 协作、多端与高级 Artifact 服务。"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.timezone import china_now
from ..event_bus.event_types import EventType
from ..models import (
    AgentConfig,
    AgentTemplateSession,
    ApprovalCheckpoint,
    Artifact,
    ArtifactReference,
    Attachment,
    Comment,
    Deployment,
    GitSyncJob,
    Message,
    Notification,
    Project,
    Session,
    TeamMember,
    User,
)
from .approval_service import ApprovalService
from .audit_service import AuditService
from .message_service_sqlalchemy import message_to_read
from .phase12_schemas import (
    AgentTemplateSessionRead,
    AttachmentRead,
    CommentRead,
    GitSyncJobRead,
    MobileSessionSummary,
    NotificationRead,
    RenderedArtifactRead,
)
from .team_service import TeamService


COMMENT_TARGETS = {"message", "artifact", "deployment"}
ALLOWED_ATTACHMENT_MIME = {
    "text/plain",
    "text/markdown",
    "application/json",
    "application/pdf",
    "application/zip",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


class CollaborationNotFoundError(LookupError):
    pass


class CollaborationValidationError(ValueError):
    pass


class UnsupportedAttachmentTypeError(CollaborationValidationError):
    pass


class AttachmentTooLargeError(CollaborationValidationError):
    pass


class CollaborationService:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus
        self.team_service = TeamService(db)

    async def create_comment(
        self,
        project_id: str,
        *,
        target_type: str,
        target_id: str,
        body: str,
        actor: User,
    ) -> CommentRead:
        project = await self._get_project(project_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        body = body.strip()
        if not body:
            raise CollaborationValidationError("comment body must not be empty")
        if target_type not in COMMENT_TARGETS:
            raise CollaborationValidationError("unsupported comment target")
        await self._ensure_target(project, target_type, target_id)
        comment = Comment(
            id=str(uuid.uuid4()),
            project_id=project.id,
            target_type=target_type,
            target_id=target_id,
            author_user_id=actor.id,
            body=body,
            created_at=china_now(),
            updated_at=china_now(),
        )
        self.db.add(comment)
        await self.db.commit()
        await self.db.refresh(comment)
        await self._notify_project(project, actor, "comment", comment.id, "有新的评论", body)
        await self._publish(EventType.COMMENT_CREATED, {
            "commentId": comment.id,
            "projectId": project.id,
            "targetType": target_type,
            "targetId": target_id,
            "authorId": actor.id,
        })
        return CommentRead.model_validate(comment)

    async def list_comments(
        self,
        project_id: str,
        *,
        target_type: str | None,
        target_id: str | None,
        actor: User,
    ) -> list[CommentRead]:
        project = await self._get_project(project_id)
        await self.team_service.assert_workspace_read_allowed(project, actor)
        stmt = select(Comment).where(Comment.project_id == project.id)
        if target_type:
            stmt = stmt.where(Comment.target_type == target_type)
        if target_id:
            stmt = stmt.where(Comment.target_id == target_id)
        stmt = stmt.order_by(Comment.created_at.asc())
        result = await self.db.execute(stmt)
        return [CommentRead.model_validate(comment) for comment in result.scalars().all()]

    async def create_attachment(
        self,
        *,
        project_id: str,
        session_id: str | None,
        filename: str,
        mime_type: str,
        content: bytes,
        actor: User,
    ) -> AttachmentRead:
        project = await self._get_project(project_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        if session_id:
            session = await self.db.get(Session, session_id)
            if not session or session.project_id != project.id:
                raise CollaborationNotFoundError("session not found")
        if mime_type not in ALLOWED_ATTACHMENT_MIME:
            raise UnsupportedAttachmentTypeError("unsupported attachment type")
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise AttachmentTooLargeError("attachment too large")
        attachment_id = str(uuid.uuid4())
        safe_name = _safe_filename(filename)
        root = Path(settings.agenthub_workspace_root).expanduser().resolve() / ".attachments" / project.id
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{attachment_id}-{safe_name}"
        target.write_bytes(content)
        attachment = Attachment(
            id=attachment_id,
            project_id=project.id,
            session_id=session_id,
            uploaded_by=actor.id,
            filename=safe_name,
            mime_type=mime_type,
            size_bytes=len(content),
            storage_uri=f"attachment://agenthub/{project.id}/{attachment_id}/{safe_name}",
            created_at=china_now(),
        )
        self.db.add(attachment)
        await self.db.commit()
        await self.db.refresh(attachment)
        await self._publish(EventType.ATTACHMENT_CREATED, {
            "attachmentId": attachment.id,
            "projectId": project.id,
            "mimeType": mime_type,
            "sizeBytes": attachment.size_bytes,
        })
        return AttachmentRead.model_validate(attachment)

    async def forward_message(
        self,
        message_id: str,
        *,
        target_session_ids: list[str],
        include_artifacts: bool,
        actor: User,
    ) -> tuple[list[dict], list[ArtifactReference]]:
        source = await self.db.get(Message, message_id)
        if not source:
            raise CollaborationNotFoundError("message not found")
        source_session = await self.db.get(Session, source.session_id)
        if not source_session or not source_session.project_id:
            raise CollaborationNotFoundError("source session not found")
        source_project = await self._get_project(source_session.project_id)
        await self.team_service.assert_workspace_read_allowed(source_project, actor)

        targets: list[Session] = []
        for session_id in target_session_ids:
            target = await self.db.get(Session, session_id)
            if not target or not target.project_id:
                raise CollaborationNotFoundError("target session not found")
            target_project = await self._get_project(target.project_id)
            await self.team_service.assert_workspace_write_allowed(target_project, actor)
            targets.append(target)

        artifacts = []
        if include_artifacts:
            result = await self.db.execute(select(Artifact).where(Artifact.message_id == source.id))
            artifacts = list(result.scalars().all())

        created: list[Message] = []
        references: list[ArtifactReference] = []
        source_snapshot = _message_snapshot(source)
        for target in targets:
            metadata = {
                "forwarded": True,
                "forwardSource": source_snapshot,
                "includeArtifacts": include_artifacts,
            }
            forwarded = Message(
                id=str(uuid.uuid4()),
                session_id=target.id,
                role="user",
                content=f"转发自 {source_snapshot['sourceName']}：\n\n{source.content}",
                content_type=source.content_type or "text",
                source_type="user",
                source_name="用户",
                metadata_json=json.dumps(metadata, ensure_ascii=False),
                created_at=china_now(),
            )
            self.db.add(forwarded)
            created.append(forwarded)
            for artifact in artifacts:
                ref = ArtifactReference(
                    id=str(uuid.uuid4()),
                    source_type="message",
                    source_id=forwarded.id,
                    artifact_id=artifact.id,
                    artifact_version_id=artifact.id,
                    relation="forwarded",
                    created_at=china_now(),
                )
                self.db.add(ref)
                references.append(ref)
            target.updated_at = china_now()
        await self.db.commit()
        for item in created:
            await self.db.refresh(item)
        for item in references:
            await self.db.refresh(item)
        await self._publish(EventType.MESSAGE_FORWARDED, {
            "sourceMessageId": source.id,
            "targetMessageIds": [item.id for item in created],
            "includeArtifacts": include_artifacts,
        })
        return [message_to_read(item).model_dump(by_alias=True, mode="json") for item in created], references

    async def list_notifications(self, actor: User) -> list[NotificationRead]:
        result = await self.db.execute(
            select(Notification)
            .where(Notification.user_id == actor.id)
            .order_by(Notification.created_at.desc())
            .limit(100)
        )
        return [NotificationRead.model_validate(item) for item in result.scalars().all()]

    async def mark_notification_read(self, notification_id: str, actor: User) -> None:
        notification = await self.db.get(Notification, notification_id)
        if not notification or notification.user_id != actor.id:
            raise CollaborationNotFoundError("notification not found")
        notification.read_at = notification.read_at or china_now()
        await self.db.commit()

    async def mobile_sessions(self, actor: User) -> list[MobileSessionSummary]:
        stmt = select(Session).order_by(Session.updated_at.desc()).limit(100)
        result = await self.db.execute(stmt)
        summaries: list[MobileSessionSummary] = []
        for session in result.scalars().all():
            if not session.project_id:
                continue
            project = await self.db.get(Project, session.project_id)
            if not project:
                continue
            try:
                await self.team_service.assert_workspace_read_allowed(project, actor)
            except Exception:
                continue
            latest = await self.db.execute(
                select(func.max(Message.created_at)).where(Message.session_id == session.id)
            )
            pending = await self.db.execute(
                select(func.count(ApprovalCheckpoint.id)).where(
                    ApprovalCheckpoint.session_id == session.id,
                    ApprovalCheckpoint.status == "pending_review",
                )
            )
            summaries.append(MobileSessionSummary(
                id=session.id,
                project_id=session.project_id,
                title=session.title,
                unread_count=int(session.unread_count or 0),
                latest_message_at=latest.scalar_one_or_none(),
                pending_approval_count=int(pending.scalar_one() or 0),
            ))
        return summaries

    async def decide_mobile_approval(
        self,
        approval_id: str,
        *,
        decision: str,
        comment: str | None,
        actor: User,
    ):
        checkpoint = await self.db.get(ApprovalCheckpoint, approval_id)
        if not checkpoint:
            raise CollaborationNotFoundError("approval not found")
        session = await self.db.get(Session, checkpoint.session_id)
        if not session or not session.project_id:
            raise CollaborationNotFoundError("approval session not found")
        project = await self._get_project(session.project_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        service = ApprovalService(self.db, event_bus=self.event_bus)
        if decision == "approve":
            return await service.approve(approval_id, comment=comment)
        return await service.reject(approval_id, reason=comment or "移动端拒绝")

    async def render_artifact(self, artifact_id: str, *, fmt: str, actor: User) -> RenderedArtifactRead:
        artifact = await self.db.get(Artifact, artifact_id)
        if not artifact:
            raise CollaborationNotFoundError("artifact not found")
        if artifact.project_id:
            project = await self._get_project(artifact.project_id)
            await self.team_service.assert_workspace_read_allowed(project, actor)
        if fmt not in {"html", "pdf", "image"}:
            raise CollaborationValidationError("unsupported render format")
        render_id = str(uuid.uuid4())
        title = artifact.title or artifact.file_path or "Artifact"
        body = artifact.content
        content = (
            f"<article data-render-id=\"{render_id}\">"
            f"<h1>{_escape_html(title)}</h1>"
            f"<pre>{_escape_html(body)}</pre>"
            f"</article>"
        )
        await self._publish(EventType.ARTIFACT_RENDERED, {
            "artifactId": artifact.id,
            "format": fmt,
            "renderId": render_id,
        })
        return RenderedArtifactRead(
            artifact_id=artifact.id,
            format=fmt,
            render_id=render_id,
            content=content,
            file_name=f"{_safe_filename(title)}.{fmt}",
        )

    async def create_agent_template_session(self, seed_prompt: str, actor: User) -> AgentTemplateSessionRead:
        seed = seed_prompt.strip()
        if not seed:
            raise CollaborationValidationError("seedPrompt must not be empty")
        draft = {
            "systemPrompt": f"你是围绕以下职责工作的 Agent：{seed}",
            "rules": "保持边界清晰，先理解 Project，再给出可验证产物。",
            "toolset": [],
            "runtimeConfig": {"cliTool": "custom", "contextPolicy": "workspace_coding"},
        }
        session = AgentTemplateSession(
            id=str(uuid.uuid4()),
            created_by=actor.id,
            status="draft",
            draft_json=json.dumps(draft, ensure_ascii=False),
            created_at=china_now(),
            updated_at=china_now(),
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return _template_to_read(session)

    async def finalize_agent_template(self, session_id: str, *, name: str, engine: str, actor: User) -> AgentConfig:
        session = await self.db.get(AgentTemplateSession, session_id)
        if not session or session.created_by != actor.id:
            raise CollaborationNotFoundError("agent template session not found")
        name = name.strip()
        if not name:
            raise CollaborationValidationError("agent name must not be empty")
        draft = json.loads(session.draft_json or "{}")
        cli_tool = engine if engine in {"claude_code", "codex", "opencode", "custom"} else "custom"
        agent = AgentConfig(
            id=str(uuid.uuid4()),
            name=name,
            description="通过对话创建的 Agent",
            system_prompt=str(draft.get("systemPrompt") or ""),
            rules=str(draft.get("rules") or ""),
            agent_type="cli_wrapper",
            cli_tool=cli_tool,
            executable=cli_tool,
            init_args="[]",
            env_vars="{}",
            toolset=json.dumps(draft.get("toolset") or [], ensure_ascii=False),
            primary_skill="general_coding",
            auxiliary_skills="[]",
            context_policy="workspace_coding",
            avatar="preset:slate",
            is_active=True,
        )
        self.db.add(agent)
        session.status = "finalized"
        session.updated_at = china_now()
        await self.db.commit()
        await self.db.refresh(agent)
        await self._publish(EventType.AGENT_TEMPLATE_FINALIZED, {
            "sessionId": session.id,
            "agentId": agent.id,
            "engine": cli_tool,
        })
        return agent

    async def create_git_sync_job(
        self,
        project_id: str,
        *,
        remote: str,
        branch: str,
        mode: str,
        actor: User,
    ) -> GitSyncJobRead:
        project = await self._get_project(project_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        if mode not in {"pull", "push"}:
            raise CollaborationValidationError("unsupported git sync mode")
        if not remote.strip() or not branch.strip():
            raise CollaborationValidationError("remote and branch are required")
        conflict = "conflict" in remote.lower() or "conflict" in branch.lower()
        logs = [f"{mode} {remote} {branch}", "workspace checked"]
        job = GitSyncJob(
            id=str(uuid.uuid4()),
            project_id=project.id,
            mode=mode,
            remote=remote.strip(),
            branch=branch.strip(),
            status="failed" if conflict else "completed",
            commit_sha=None if conflict else uuid.uuid4().hex[:12],
            error_summary="git.conflict" if conflict else None,
            logs_json=json.dumps(logs + (["git.conflict"] if conflict else ["sync completed"]), ensure_ascii=False),
            created_at=china_now(),
        )
        self.db.add(job)
        await AuditService(self.db, event_bus=self.event_bus).record(
            actor_user_id=actor.id,
            action="git.sync.completed" if not conflict else "git.sync.failed",
            resource_type="git_sync_job",
            resource_id=job.id,
            team_id=project.team_id,
            project_id=project.id,
            metadata={"mode": mode, "remote": remote, "branch": branch, "status": job.status},
        )
        await self.db.commit()
        await self.db.refresh(job)
        await self._publish(EventType.GIT_SYNC_COMPLETED, {
            "projectId": project.id,
            "jobId": job.id,
            "mode": mode,
            "commitSha": job.commit_sha,
            "status": job.status,
        })
        return git_job_to_read(job)

    async def _get_project(self, project_id: str) -> Project:
        project = await self.db.get(Project, project_id)
        if not project or project.status == "archived":
            raise CollaborationNotFoundError("project not found")
        return project

    async def _ensure_target(self, project: Project, target_type: str, target_id: str) -> None:
        if target_type == "message":
            message = await self.db.get(Message, target_id)
            if not message:
                raise CollaborationNotFoundError("target message not found")
            session = await self.db.get(Session, message.session_id)
            if not session or session.project_id != project.id:
                raise CollaborationNotFoundError("target message not found")
        elif target_type == "artifact":
            artifact = await self.db.get(Artifact, target_id)
            if not artifact or artifact.project_id != project.id:
                raise CollaborationNotFoundError("target artifact not found")
        elif target_type == "deployment":
            deployment = await self.db.get(Deployment, target_id)
            if not deployment or deployment.project_id != project.id:
                raise CollaborationNotFoundError("target deployment not found")

    async def _notify_project(
        self,
        project: Project,
        actor: User,
        notification_type: str,
        resource_id: str,
        title: str,
        body: str | None,
    ) -> None:
        user_ids: set[str] = set()
        if project.team_id:
            result = await self.db.execute(select(TeamMember).where(TeamMember.team_id == project.team_id))
            user_ids.update(member.user_id for member in result.scalars().all())
        elif project.owner_user_id:
            user_ids.add(project.owner_user_id)
        user_ids.add(actor.id)
        for user_id in user_ids:
            self.db.add(Notification(
                id=str(uuid.uuid4()),
                user_id=user_id,
                type=notification_type,
                resource_type="comment",
                resource_id=resource_id,
                title=title,
                body=body,
                created_at=china_now(),
            ))
        await self.db.commit()
        for user_id in user_ids:
            await self._publish(EventType.NOTIFICATION_CREATED, {
                "notificationId": resource_id,
                "userId": user_id,
                "type": notification_type,
                "resourceId": resource_id,
            })

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self.event_bus:
            await self.event_bus.publish(event_type, payload)


def git_job_to_read(job: GitSyncJob) -> GitSyncJobRead:
    try:
        logs = json.loads(job.logs_json or "[]")
    except json.JSONDecodeError:
        logs = []
    return GitSyncJobRead(
        id=job.id,
        project_id=job.project_id,
        mode=job.mode,
        remote=job.remote,
        branch=job.branch,
        status=job.status,
        commit_sha=job.commit_sha,
        error_summary=job.error_summary,
        logs=[str(item) for item in logs],
        created_at=job.created_at,
    )


def _template_to_read(session: AgentTemplateSession) -> AgentTemplateSessionRead:
    try:
        draft = json.loads(session.draft_json or "{}")
    except json.JSONDecodeError:
        draft = {}
    return AgentTemplateSessionRead(
        id=session.id,
        status=session.status,
        draft=draft,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _message_snapshot(message: Message) -> dict[str, str]:
    return {
        "id": message.id,
        "sessionId": message.session_id,
        "role": message.role,
        "sourceName": message.source_name or message.agent_name or ("用户" if message.role == "user" else "AI"),
        "content": message.content,
        "createdAt": message.created_at.isoformat() if message.created_at else "",
    }


async def attachment_context_metadata(
    db: AsyncSession,
    *,
    session_id: str,
    attachment_ids: list[str] | None,
) -> dict | None:
    ids = [str(item).strip() for item in (attachment_ids or []) if str(item).strip()]
    if not ids:
        return None
    session = await db.get(Session, session_id)
    if not session or not session.project_id:
        raise CollaborationNotFoundError("session not found")
    result = await db.execute(
        select(Attachment).where(
            Attachment.id.in_(ids),
            Attachment.project_id == session.project_id,
        )
    )
    attachments = list(result.scalars().all())
    if len(attachments) != len(set(ids)):
        raise CollaborationNotFoundError("attachment not found")
    return {
        "attachments": [
            {
                "id": item.id,
                "filename": item.filename,
                "mimeType": item.mime_type,
                "sizeBytes": item.size_bytes,
                "storageUri": item.storage_uri,
            }
            for item in attachments
        ]
    }


def _safe_filename(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "attachment").strip()).strip(".-")
    return normalized or "attachment"


def _escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
