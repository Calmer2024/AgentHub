"""Phase 11/16 Cloud Preview 与 Deployment 服务。"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now
from ..event_bus.event_types import EventType
from ..models import (
    Artifact,
    Deployment,
    DeploymentLog,
    DeploymentRelease,
    DeploymentTarget,
    PreviewSession,
    Project,
    TeamMember,
    User,
)
from .cloud_storage import ensure_cloud_workspace
from .deployment_provider import (
    DeploymentProviderError,
    get_deployment_provider,
    provider_public_base_url,
)
from .phase11_schemas import (
    DeploymentCreate,
    DeploymentLogChunkRead,
    DeploymentLogsRead,
    DeploymentProviderListRead,
    DeploymentProviderRead,
    DeploymentRead,
    DeploymentRetryRequest,
    DeploymentTargetCreate,
    DeploymentTargetListRead,
    DeploymentTargetRead,
    PreviewCreate,
    PreviewSessionRead,
)
from .team_service import PermissionDeniedError, TeamService


PREVIEW_SOURCES = {"static", "build", "dev_server"}
DEPLOYMENT_TARGETS = {"static_hosting", "third_party"}
DELIVERY_VISIBILITIES = {"public", "team", "private"}
RUNNING_DEPLOYMENT_STATUSES = {"queued", "running"}
TARGET_SCOPES = {"user", "team", "project"}


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

    async def list_deployment_providers(self, actor: User) -> DeploymentProviderListRead:
        del actor
        provider = get_deployment_provider()
        return DeploymentProviderListRead(items=[
            DeploymentProviderRead(
                id=provider.id,
                name=provider.name,
                kind=provider.kind,
                capabilities=provider.capabilities,
                status="available",
                public_base_url=provider_public_base_url(),
                requires_secret=provider.requires_secret,
            )
        ])

    async def list_deployment_targets(self, actor: User) -> DeploymentTargetListRead:
        await self._ensure_user_default_target(actor)
        team_ids = await self._actor_team_ids(actor)
        project_ids = await self._actor_project_ids(actor, team_ids)
        filters = [DeploymentTarget.scope == "user", DeploymentTarget.owner_id == actor.id]
        scope_filters = [
            (DeploymentTarget.scope == "user") & (DeploymentTarget.owner_id == actor.id),
        ]
        if team_ids:
            scope_filters.append((DeploymentTarget.scope == "team") & DeploymentTarget.owner_id.in_(team_ids))
        if project_ids:
            scope_filters.append((DeploymentTarget.scope == "project") & DeploymentTarget.owner_id.in_(project_ids))
        result = await self.db.execute(
            select(DeploymentTarget)
            .where(or_(*scope_filters))
            .order_by(DeploymentTarget.updated_at.desc(), DeploymentTarget.created_at.desc())
        )
        del filters
        return DeploymentTargetListRead(items=[target_to_read(item) for item in result.scalars().all()])

    async def create_deployment_target(
        self,
        data: DeploymentTargetCreate,
        actor: User,
    ) -> DeploymentTargetRead:
        provider = get_deployment_provider(data.provider)
        scope = data.scope.strip().lower()
        if scope not in TARGET_SCOPES:
            raise CloudDeliveryValidationError("unsupported deployment target scope")
        owner_id = data.owner_id or actor.id
        if scope == "user":
            owner_id = actor.id
        elif scope == "team":
            if not data.owner_id:
                raise CloudDeliveryValidationError("ownerId is required for team target")
            await self.team_service.assert_team_admin(owner_id, actor.id)
        elif scope == "project":
            if not data.owner_id:
                raise CloudDeliveryValidationError("ownerId is required for project target")
            project = await self._get_project(owner_id)
            await self.team_service.assert_workspace_write_allowed(project, actor)

        name = data.name.strip()
        if not name:
            raise CloudDeliveryValidationError("target name must not be empty")

        target = DeploymentTarget(
            id=str(uuid.uuid4()),
            scope=scope,
            owner_id=owner_id,
            provider=provider.id,
            name=name,
            config_json=json.dumps(data.config, ensure_ascii=False),
            status="active",
            created_by=actor.id,
            created_at=china_now(),
            updated_at=china_now(),
        )
        self.db.add(target)
        await self.db.commit()
        await self.db.refresh(target)
        return target_to_read(target)

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
        version_artifact = await self._artifact_version(artifact, data.artifact_version_id or artifact.id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        self._ensure_cloud_project(project)
        await self._ensure_preview_source(project, version_artifact, data.source)

        ttl = data.ttl_seconds if data.ttl_seconds is not None else 3600
        if ttl <= 0:
            raise CloudDeliveryValidationError("ttlSeconds must be positive")

        preview_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(18)
        expires_at = china_now() + timedelta(seconds=min(ttl, 24 * 60 * 60))
        provider = get_deployment_provider()
        try:
            result = await provider.create_preview(
                preview_id=preview_id,
                artifact=version_artifact,
                project=project,
                source=data.source,
            )
        except DeploymentProviderError as exc:
            raise CloudDeliveryValidationError(str(exc)) from exc

        preview = PreviewSession(
            id=preview_id,
            artifact_id=artifact.id,
            artifact_version_id=version_artifact.id,
            workspace_id=str(project.workspace_id),
            source=data.source,
            status="ready",
            url=result.url,
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
            "artifactVersionId": version_artifact.id,
            "url": preview.url,
            "expiresAt": preview.expires_at.isoformat() if preview.expires_at else None,
            "visibility": preview.visibility,
        })
        return preview_to_read(preview)

    async def get_preview(self, preview_id: str, actor: User) -> PreviewSessionRead:
        preview = await self._get_preview(preview_id)
        _artifact, project = await self._artifact_project(preview.artifact_id)
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
        version_artifact = await self._artifact_version(artifact, data.artifact_version_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        self._ensure_cloud_project(project)
        await self._ensure_no_active_deployment(artifact.id, version_artifact.id)
        target = await self._deployment_target(data.target_id, actor, project)

        deployment = Deployment(
            id=str(uuid.uuid4()),
            artifact_id=artifact.id,
            artifact_version_id=version_artifact.id,
            project_id=project.id,
            target_id=target.id,
            provider=target.provider,
            target=data.target,
            visibility=data.visibility,
            status="queued",
            stage="queued",
            provider_metadata_json="{}",
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
            "artifactVersionId": version_artifact.id,
            "targetId": target.id,
            "target": deployment.target,
        })
        await self._run_deployment_pipeline(
            deployment,
            version_artifact,
            project,
            target,
            actor,
            fail_marker="DEPLOY_FAIL" in version_artifact.content,
        )
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
        version_artifact = await self._artifact_version(artifact, deployment.artifact_version_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        if not deployment.target_id:
            raise CloudDeliveryValidationError("deployment target missing")
        target = await self._get_target(deployment.target_id)
        await self._assert_target_read_allowed(target, actor)
        deployment.status = "queued"
        deployment.stage = from_stage or deployment.stage or "queued"
        deployment.error_summary = None
        deployment.updated_at = china_now()
        await self.db.commit()
        await self._run_deployment_pipeline(
            deployment,
            version_artifact,
            project,
            target,
            actor,
            fail_marker=False,
        )
        return deployment_to_read(deployment)

    async def rollback_deployment(
        self,
        deployment_id: str,
        actor: User,
        target_deployment_id: str,
    ) -> DeploymentRead:
        deployment = await self._get_deployment(deployment_id)
        target_deployment = await self._get_deployment(target_deployment_id)
        if target_deployment.status not in {"published", "rolled_back"} or not target_deployment.active_release_id:
            raise CloudDeliveryValidationError("target deployment is not published")
        if deployment.project_id != target_deployment.project_id:
            raise CloudDeliveryValidationError("target deployment belongs to another project")
        project = await self._get_project(deployment.project_id)
        await self.team_service.assert_workspace_write_allowed(project, actor)
        target = await self._get_target(target_deployment.target_id or deployment.target_id or "")
        await self._assert_target_read_allowed(target, actor)
        release = await self._get_release(target_deployment.active_release_id)
        metadata = release.provider_metadata
        release_path = str(metadata.get("storagePath") or "")
        if not release_path:
            raise CloudDeliveryValidationError("target release storage path missing")
        provider = get_deployment_provider(target_deployment.provider)
        try:
            result = await provider.rollback(
                deployment=deployment,
                target=target,
                target_release_storage_path=release_path,
                target_release_id=release.id,
                bundle_uri=release.bundle_uri,
            )
        except DeploymentProviderError as exc:
            raise CloudDeliveryValidationError(str(exc)) from exc

        deployment.status = "rolled_back"
        deployment.stage = "verify"
        deployment.target_id = target.id
        deployment.provider = target.provider
        deployment.active_release_id = result.release_id
        deployment.bundle_uri = result.bundle_uri
        deployment.url = result.url
        deployment.provider_metadata_json = json.dumps(result.provider_metadata, ensure_ascii=False)
        deployment.error_summary = None
        deployment.updated_at = china_now()
        await self.db.commit()
        await self._append_deploy_log(deployment.id, "system", f"rolled back to release {release.id}\n")
        await self._publish(EventType.DEPLOYMENT_ROLLED_BACK, {
            "deploymentId": deployment.id,
            "targetDeploymentId": target_deployment.id,
            "activeReleaseId": result.release_id,
            "url": result.url,
        })
        await self._notify_project(project, actor, "deployment", deployment.id, "部署已回滚", result.url)
        return deployment_to_read(deployment)

    async def _run_deployment_pipeline(
        self,
        deployment: Deployment,
        artifact: Artifact,
        project: Project,
        target: DeploymentTarget,
        actor: User,
        *,
        fail_marker: bool,
    ) -> None:
        provider = get_deployment_provider(target.provider)
        bundle = None
        published = None

        for stage in ["install", "build", "package", "upload", "publish", "verify"]:
            deployment.status = "running"
            deployment.stage = stage
            deployment.updated_at = china_now()
            await self.db.commit()
            await self._publish(EventType.DEPLOYMENT_STAGE_CHANGED, {
                "deploymentId": deployment.id,
                "stage": stage,
                "status": "running",
            })
            try:
                if stage == "install":
                    await self._append_deploy_log(deployment.id, "system", "install completed: static artifact has no dependency install\n")
                elif stage == "build":
                    if fail_marker:
                        raise DeploymentProviderError("DEPLOY_FAIL marker")
                    await self._append_deploy_log(deployment.id, "system", "build completed: static artifact version is immutable\n")
                elif stage == "package":
                    bundle = await provider.build_release(
                        deployment=deployment,
                        artifact=artifact,
                        project=project,
                    )
                    await self._append_deploy_log(
                        deployment.id,
                        "system",
                        f"package completed: {bundle.bundle_uri} size={bundle.size_bytes}\n",
                    )
                elif stage == "upload":
                    if not bundle:
                        raise DeploymentProviderError("release bundle missing")
                    await self._append_deploy_log(deployment.id, "system", f"upload completed: {bundle.bundle_uri}\n")
                elif stage == "publish":
                    if not bundle:
                        raise DeploymentProviderError("release bundle missing")
                    published = await provider.publish(deployment=deployment, target=target, bundle=bundle)
                    self.db.add(DeploymentRelease(
                        id=published.release_id,
                        deployment_id=deployment.id,
                        artifact_id=deployment.artifact_id,
                        artifact_version_id=deployment.artifact_version_id,
                        target_id=target.id,
                        bundle_uri=published.bundle_uri,
                        public_url=published.url,
                        status="published",
                        provider_metadata_json=json.dumps(published.provider_metadata, ensure_ascii=False),
                        created_at=china_now(),
                    ))
                    deployment.url = published.url
                    deployment.active_release_id = published.release_id
                    deployment.bundle_uri = published.bundle_uri
                    deployment.provider_metadata_json = json.dumps(published.provider_metadata, ensure_ascii=False)
                    await self.db.commit()
                    await self._append_deploy_log(deployment.id, "system", f"publish completed: {published.url}\n")
                elif stage == "verify":
                    if not published:
                        raise DeploymentProviderError("published release missing")
                    await self._append_deploy_log(deployment.id, "system", f"verify completed: {published.url}\n")
            except DeploymentProviderError as exc:
                deployment.status = "failed"
                deployment.error_summary = "发布构建失败" if stage == "build" else str(exc)
                deployment.updated_at = china_now()
                await self.db.commit()
                await self._append_deploy_log(deployment.id, "stderr", f"{stage} failed: {exc}\n")
                await self._publish(EventType.DEPLOYMENT_FAILED, {
                    "deploymentId": deployment.id,
                    "stage": stage,
                    "errorSummary": deployment.error_summary,
                })
                await self._notify_project(
                    project,
                    actor,
                    "deployment",
                    deployment.id,
                    "部署失败",
                    deployment.error_summary,
                )
                return

        deployment.status = "published"
        deployment.stage = "verify"
        deployment.published_at = china_now()
        deployment.updated_at = deployment.published_at
        await self.db.commit()
        await self._publish(EventType.DEPLOYMENT_PUBLISHED, {
            "deploymentId": deployment.id,
            "releaseId": deployment.active_release_id,
            "url": deployment.url,
            "artifactVersionId": deployment.artifact_version_id,
            "targetId": target.id,
            "provider": provider.id,
        })
        await self._notify_project(
            project,
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

    async def _artifact_version(self, root_artifact: Artifact, version_id: str) -> Artifact:
        artifact = await self.db.get(Artifact, version_id)
        if not artifact:
            raise CloudDeliveryNotFoundError("artifact version not found")
        current: Artifact | None = artifact
        while current:
            if current.id == root_artifact.id:
                return artifact
            if not current.parent_artifact_id:
                break
            current = await self.db.get(Artifact, current.parent_artifact_id)
        raise CloudDeliveryValidationError("artifact version does not belong to artifact")

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

    async def _get_target(self, target_id: str) -> DeploymentTarget:
        target = await self.db.get(DeploymentTarget, target_id)
        if not target or target.status != "active":
            raise CloudDeliveryNotFoundError("deployment target not found")
        return target

    async def _get_release(self, release_id: str) -> DeploymentRelease:
        release = await self.db.get(DeploymentRelease, release_id)
        if not release or release.status != "published":
            raise CloudDeliveryNotFoundError("deployment release not found")
        return release

    async def _deployment_target(self, target_id: str | None, actor: User, project: Project) -> DeploymentTarget:
        if target_id:
            target = await self._get_target(target_id)
            await self._assert_target_read_allowed(target, actor)
            return target
        return await self._ensure_project_default_target(project, actor)

    async def _ensure_user_default_target(self, actor: User) -> DeploymentTarget:
        result = await self.db.execute(
            select(DeploymentTarget).where(
                DeploymentTarget.scope == "user",
                DeploymentTarget.owner_id == actor.id,
                DeploymentTarget.provider == "static_site",
                DeploymentTarget.status == "active",
            )
        )
        target = result.scalars().first()
        if target:
            return target
        target = DeploymentTarget(
            id=str(uuid.uuid4()),
            scope="user",
            owner_id=actor.id,
            provider="static_site",
            name="个人默认静态站点",
            config_json="{}",
            status="active",
            created_by=actor.id,
            created_at=china_now(),
            updated_at=china_now(),
        )
        self.db.add(target)
        await self.db.commit()
        await self.db.refresh(target)
        return target

    async def _ensure_project_default_target(self, project: Project, actor: User) -> DeploymentTarget:
        result = await self.db.execute(
            select(DeploymentTarget).where(
                DeploymentTarget.scope == "project",
                DeploymentTarget.owner_id == project.id,
                DeploymentTarget.provider == "static_site",
                DeploymentTarget.status == "active",
            )
        )
        target = result.scalars().first()
        if target:
            return target
        target = DeploymentTarget(
            id=str(uuid.uuid4()),
            scope="project",
            owner_id=project.id,
            provider="static_site",
            name=f"{project.name or 'Project'} 默认静态站点",
            config_json=json.dumps({"projectId": project.id}, ensure_ascii=False),
            status="active",
            created_by=actor.id,
            created_at=china_now(),
            updated_at=china_now(),
        )
        self.db.add(target)
        await self.db.commit()
        await self.db.refresh(target)
        return target

    async def _assert_target_read_allowed(self, target: DeploymentTarget, actor: User) -> None:
        if target.scope == "user":
            if target.owner_id != actor.id:
                raise PermissionDeniedError("you do not have access to this deployment target")
            return
        if target.scope == "team":
            await self.team_service.role_for_user(target.owner_id, actor.id)
            return
        if target.scope == "project":
            project = await self._get_project(target.owner_id)
            await self.team_service.assert_workspace_read_allowed(project, actor)
            return
        raise CloudDeliveryValidationError("unsupported deployment target scope")

    async def _actor_team_ids(self, actor: User) -> list[str]:
        result = await self.db.execute(select(TeamMember.team_id).where(TeamMember.user_id == actor.id))
        return [str(row[0]) for row in result.fetchall()]

    async def _actor_project_ids(self, actor: User, team_ids: list[str]) -> list[str]:
        filters = [Project.owner_user_id == actor.id]
        if team_ids:
            filters.append(Project.team_id.in_(team_ids))
        result = await self.db.execute(select(Project.id).where(or_(*filters)))
        return [str(row[0]) for row in result.fetchall()]

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


def target_to_read(target: DeploymentTarget) -> DeploymentTargetRead:
    return DeploymentTargetRead.model_validate(target)


def _safe_workspace_child(root: Path, subpath: str) -> Path:
    raw = str(subpath or "").replace("\\", "/").strip("/")
    if not raw:
        raw = "index.html"
    candidate = (root / raw).resolve()
    root = root.resolve()
    if candidate != root and root not in candidate.parents:
        raise CloudDeliveryValidationError("path outside workspace")
    return candidate
