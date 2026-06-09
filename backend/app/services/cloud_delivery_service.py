"""Phase 11 Cloud Preview 与 Deployment 服务。"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..event_bus.event_types import EventType
from ..models import (
    Artifact,
    Deployment,
    DeploymentLog,
    PreviewSession,
    Project,
    TeamMember,
    User,
)
from .cloud_storage import ensure_cloud_workspace
from .phase11_schemas import (
    DeploymentCreate,
    DeploymentLogChunkRead,
    DeploymentLogsRead,
    DeploymentRead,
    PreviewCreate,
    PreviewSessionRead,
)
from .team_service import PermissionDeniedError, TeamService


PREVIEW_SOURCES = {"static", "build", "dev_server"}
DEPLOYMENT_TARGETS = {"static_hosting", "third_party"}
DELIVERY_VISIBILITIES = {"public", "team", "private"}
RUNNING_DEPLOYMENT_STATUSES = {"queued", "running"}


class CloudDeliveryNotFoundError(LookupError):
    pass


class CloudDeliveryValidationError(ValueError):
    pass


class PreviewExpiredError(CloudDeliveryValidationError):
    pass


class DeploymentConflictError(CloudDeliveryValidationError):
    pass


class CloudDeliveryService:
    def __init__(self, db: AsyncSession, event_bus: Any = None):
        self.db = db
        self.event_bus = event_bus
        self.team_service = TeamService(db)

    async def create_preview(
        self,
        artifact_id: str,
        data: PreviewCreate,
        actor: User,
    ) -> PreviewSessionRead:
        if data.source not in PREVIEW_SOURCES:
            raise CloudDeliveryValidationError("unsupported preview source")
        if data.visibility not in DELIVERY_VISIBILITIES:
            raise CloudDeliveryValidationError("unsupported preview visibility")
        artifact, project = await self._artifact_project(artifact_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        self._ensure_cloud_project(project)
        await self._ensure_preview_source(project, artifact, data.source)

        ttl = data.ttl_seconds if data.ttl_seconds is not None else 3600
        if ttl <= 0:
            raise CloudDeliveryValidationError("ttlSeconds must be positive")

        preview_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(18)
        expires_at = china_now() + timedelta(seconds=min(ttl, 24 * 60 * 60))
        preview = PreviewSession(
            id=preview_id,
            artifact_id=artifact.id,
            artifact_version_id=data.artifact_version_id or artifact.id,
            workspace_id=str(project.workspace_id),
            source=data.source,
            status="ready",
            url=f"https://preview.agenthub.local/p/{preview_id}?token={token}",
            visibility=data.visibility,
            auth_token=token,
            expires_at=expires_at,
            created_by=actor.id,
            created_at=china_now(),
        )
        self.db.add(preview)
        await self.db.commit()
        await self.db.refresh(preview)
        await self._publish(EventType.PREVIEW_CREATED, {
            "previewId": preview.id,
            "artifactId": artifact.id,
            "url": preview.url,
            "expiresAt": preview.expires_at.isoformat() if preview.expires_at else None,
            "visibility": preview.visibility,
        })
        return preview_to_read(preview)

    async def get_preview(self, preview_id: str, actor: User) -> PreviewSessionRead:
        preview = await self._get_preview(preview_id)
        artifact, project = await self._artifact_project(preview.artifact_id)
        if preview.visibility != "public":
            await self.team_service.assert_workspace_read_allowed(project, actor)
        if preview.status == "revoked":
            raise PreviewExpiredError("preview link revoked")
        if preview.expires_at and preview.expires_at <= china_now():
            preview.status = "expired"
            await self.db.commit()
            raise PreviewExpiredError("preview link expired")
        return preview_to_read(preview)

    async def revoke_preview(self, preview_id: str, actor: User, reason: str | None = None) -> str:
        preview = await self._get_preview(preview_id)
        _artifact, project = await self._artifact_project(preview.artifact_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        preview.status = "revoked"
        await self.db.commit()
        await self._publish(EventType.PREVIEW_REVOKED, {
            "previewId": preview.id,
            "reason": reason,
        })
        return preview.status

    async def create_deployment(self, data: DeploymentCreate, actor: User) -> DeploymentRead:
        if data.target not in DEPLOYMENT_TARGETS:
            raise CloudDeliveryValidationError("unsupported deployment target")
        if data.visibility not in DELIVERY_VISIBILITIES:
            raise CloudDeliveryValidationError("unsupported deployment visibility")
        artifact, project = await self._artifact_project(data.artifact_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        self._ensure_cloud_project(project)
        await self._ensure_no_active_deployment(artifact.id, data.artifact_version_id)

        deployment = Deployment(
            id=str(uuid.uuid4()),
            artifact_id=artifact.id,
            artifact_version_id=data.artifact_version_id,
            project_id=project.id,
            target=data.target,
            visibility=data.visibility,
            status="queued",
            stage="queued",
            created_by=actor.id,
            created_at=china_now(),
            updated_at=china_now(),
        )
        self.db.add(deployment)
        await self.db.commit()
        await self.db.refresh(deployment)
        await self._publish(EventType.DEPLOYMENT_QUEUED, {
            "deploymentId": deployment.id,
            "artifactId": artifact.id,
            "target": deployment.target,
        })
        await self._run_deployment_pipeline(deployment, artifact, actor, fail_marker="DEPLOY_FAIL" in artifact.content)
        return deployment_to_read(deployment)

    async def get_deployment(self, deployment_id: str, actor: User) -> DeploymentRead:
        deployment = await self._get_deployment(deployment_id)
        project = await self._get_project(deployment.project_id)
        await self.team_service.assert_workspace_read_allowed(project, actor)
        return deployment_to_read(deployment)

    async def get_deployment_logs(self, deployment_id: str, actor: User) -> DeploymentLogsRead:
        await self.get_deployment(deployment_id, actor)
        result = await self.db.execute(
            select(DeploymentLog)
            .where(DeploymentLog.deployment_id == deployment_id)
            .order_by(DeploymentLog.sequence.asc(), DeploymentLog.id.asc())
        )
        return DeploymentLogsRead(chunks=[
            DeploymentLogChunkRead(
                sequence=log.sequence,
                stream=log.stream,
                text=log.text,
                created_at=log.created_at,
            )
            for log in result.scalars().all()
        ])

    async def retry_deployment(self, deployment_id: str, actor: User, from_stage: str | None = None) -> DeploymentRead:
        deployment = await self._get_deployment(deployment_id)
        if deployment.status != "failed":
            raise DeploymentConflictError("only failed deployment can retry")
        artifact, project = await self._artifact_project(deployment.artifact_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        deployment.status = "queued"
        deployment.stage = from_stage or deployment.stage or "queued"
        deployment.error_summary = None
        deployment.updated_at = china_now()
        await self.db.commit()
        await self._run_deployment_pipeline(deployment, artifact, actor, fail_marker=False)
        return deployment_to_read(deployment)

    async def rollback_deployment(
        self,
        deployment_id: str,
        actor: User,
        target_deployment_id: str,
    ) -> DeploymentRead:
        deployment = await self._get_deployment(deployment_id)
        target = await self._get_deployment(target_deployment_id)
        if target.status not in {"published", "rolled_back"} or not target.url:
            raise CloudDeliveryValidationError("target deployment is not published")
        if deployment.project_id != target.project_id:
            raise CloudDeliveryValidationError("target deployment belongs to another project")
        project = await self._get_project(deployment.project_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        deployment.status = "rolled_back"
        deployment.stage = "verify"
        deployment.url = target.url
        deployment.error_summary = None
        deployment.updated_at = china_now()
        await self.db.commit()
        await self._append_deploy_log(deployment.id, "system", f"rolled back to {target.id}\n")
        await self._publish(EventType.DEPLOYMENT_ROLLED_BACK, {
            "deploymentId": deployment.id,
            "targetDeploymentId": target.id,
            "url": target.url,
        })
        await self._notify_project(project, actor, "deployment", deployment.id, "部署已回滚", target.url)
        return deployment_to_read(deployment)

    async def _run_deployment_pipeline(
        self,
        deployment: Deployment,
        artifact: Artifact,
        actor: User,
        *,
        fail_marker: bool,
    ) -> None:
        for stage in ["install", "build", "upload", "publish", "verify"]:
            deployment.status = "running"
            deployment.stage = stage
            deployment.updated_at = china_now()
            await self.db.commit()
            await self._append_deploy_log(deployment.id, "system", f"{stage} completed\n")
            await self._publish(EventType.DEPLOYMENT_STAGE_CHANGED, {
                "deploymentId": deployment.id,
                "stage": stage,
                "status": "running",
            })
            if fail_marker and stage == "build":
                deployment.status = "failed"
                deployment.error_summary = "发布构建失败"
                deployment.updated_at = china_now()
                await self.db.commit()
                await self._append_deploy_log(deployment.id, "stderr", "build failed: DEPLOY_FAIL marker\n")
                await self._publish(EventType.DEPLOYMENT_FAILED, {
                    "deploymentId": deployment.id,
                    "stage": stage,
                    "errorSummary": deployment.error_summary,
                })
                await self._notify_project(
                    await self._get_project(deployment.project_id),
                    actor,
                    "deployment",
                    deployment.id,
                    "部署失败",
                    deployment.error_summary,
                )
                return

        deployment.status = "published"
        deployment.stage = "verify"
        deployment.url = f"https://deploy.agenthub.local/d/{deployment.id}"
        deployment.updated_at = china_now()
        await self.db.commit()
        await self._append_deploy_log(deployment.id, "system", f"published {deployment.url}\n")
        await self._publish(EventType.DEPLOYMENT_PUBLISHED, {
            "deploymentId": deployment.id,
            "url": deployment.url,
            "artifactVersionId": deployment.artifact_version_id,
        })
        await self._notify_project(
            await self._get_project(deployment.project_id),
            actor,
            "deployment",
            deployment.id,
            "部署已发布",
            deployment.url,
        )

    async def _artifact_project(self, artifact_id: str) -> tuple[Artifact, Project]:
        artifact = await self.db.get(Artifact, artifact_id)
        if not artifact:
            raise CloudDeliveryNotFoundError("artifact not found")
        project_id = artifact.project_id
        if not project_id:
            raise CloudDeliveryValidationError("artifact is not bound to project")
        project = await self._get_project(project_id)
        return artifact, project

    async def _get_project(self, project_id: str) -> Project:
        project = await self.db.get(Project, project_id)
        if not project or project.status == "archived":
            raise CloudDeliveryNotFoundError("project not found")
        return project

    async def _get_preview(self, preview_id: str) -> PreviewSession:
        preview = await self.db.get(PreviewSession, preview_id)
        if not preview:
            raise CloudDeliveryNotFoundError("preview not found")
        return preview

    async def _get_deployment(self, deployment_id: str) -> Deployment:
        deployment = await self.db.get(Deployment, deployment_id)
        if not deployment:
            raise CloudDeliveryNotFoundError("deployment not found")
        return deployment

    def _ensure_cloud_project(self, project: Project) -> None:
        if project.workspace_mode != "cloud" or not project.workspace_id:
            raise CloudDeliveryValidationError("cloud delivery requires cloud project")

    async def _ensure_preview_source(self, project: Project, artifact: Artifact, source: str) -> None:
        if source == "dev_server":
            return
        root = ensure_cloud_workspace(str(project.workspace_id), {"projectId": project.id})
        path = _safe_workspace_child(root, artifact.file_path or "index.html")
        if source == "build":
            path = _safe_workspace_child(root, artifact.file_path or "dist/index.html")
        if not path.exists():
            raise CloudDeliveryValidationError("preview source not found")

    async def _ensure_no_active_deployment(self, artifact_id: str, version_id: str) -> None:
        result = await self.db.execute(
            select(Deployment).where(
                Deployment.artifact_id == artifact_id,
                Deployment.artifact_version_id == version_id,
                Deployment.status.in_(RUNNING_DEPLOYMENT_STATUSES),
            )
        )
        if result.scalars().first():
            raise DeploymentConflictError("deployment already running for this artifact version")

    async def _append_deploy_log(self, deployment_id: str, stream: str, text: str) -> None:
        result = await self.db.execute(
            select(DeploymentLog)
            .where(DeploymentLog.deployment_id == deployment_id)
            .order_by(DeploymentLog.sequence.desc())
            .limit(1)
        )
        latest = result.scalars().first()
        sequence = 1 if not latest else latest.sequence + 1
        self.db.add(DeploymentLog(
            id=str(uuid.uuid4()),
            deployment_id=deployment_id,
            sequence=sequence,
            stream=stream,
            text=text,
            created_at=china_now(),
        ))
        await self.db.commit()
        await self._publish(EventType.DEPLOYMENT_LOG, {
            "deploymentId": deployment_id,
            "sequence": sequence,
            "stream": stream,
            "text": text,
        })

    async def _notify_project(
        self,
        project: Project,
        actor: User,
        notification_type: str,
        resource_id: str,
        title: str,
        body: str | None,
    ) -> None:
        from ..models import Notification

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
                resource_type="deployment",
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


def preview_to_read(preview: PreviewSession) -> PreviewSessionRead:
    return PreviewSessionRead.model_validate(preview)


def deployment_to_read(deployment: Deployment) -> DeploymentRead:
    return DeploymentRead.model_validate(deployment)


def _safe_workspace_child(root: Path, subpath: str) -> Path:
    raw = str(subpath or "").replace("\\", "/").strip("/")
    if not raw:
        raw = "index.html"
    candidate = (root / raw).resolve()
    root = root.resolve()
    if candidate != root and root not in candidate.parents:
        raise CloudDeliveryValidationError("path outside workspace")
    return candidate
