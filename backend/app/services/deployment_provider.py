"""Phase 16 真实部署 Provider。

当前内置 static_site provider 面向 SaaS 静态 Web Artifact：把固定 Artifact
版本写入 release 目录，再发布到可由 Nginx/对象存储暴露的静态目录。
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import settings
from ..models import Artifact, Deployment, DeploymentTarget, Project
from .cloud_storage import ensure_cloud_workspace


class DeploymentProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreviewPublishResult:
    url: str
    storage_path: str
    provider_metadata: dict[str, Any]


@dataclass(frozen=True)
class ReleaseBundle:
    release_id: str
    bundle_uri: str
    storage_path: str
    entry_path: str
    size_bytes: int
    provider_metadata: dict[str, Any]


@dataclass(frozen=True)
class PublishResult:
    release_id: str
    url: str
    bundle_uri: str
    provider_metadata: dict[str, Any]


class StaticSiteDeploymentProvider:
    id = "static_site"
    name = "AgentHub Static Site"
    kind = "self_hosted_static"
    capabilities = ["preview", "static_site", "release", "rollback", "verify"]
    requires_secret = False

    async def create_preview(
        self,
        *,
        preview_id: str,
        artifact: Artifact,
        project: Project,
        source: str,
    ) -> PreviewPublishResult:
        content = _artifact_content(artifact, project)
        preview_dir = _safe_storage_child(_deployment_root(), f"previews/{preview_id}")
        _replace_dir(preview_dir)
        entry_path = _entry_path(artifact)
        target = _safe_storage_child(preview_dir, entry_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if entry_path != "index.html":
            (preview_dir / "index.html").write_text(content, encoding="utf-8")
        url = f"{_public_base_url()}/previews/{preview_id}/"
        return PreviewPublishResult(
            url=url,
            storage_path=str(preview_dir),
            provider_metadata={
                "provider": self.id,
                "source": source,
                "entryPath": entry_path,
                "storagePath": str(preview_dir),
            },
        )

    async def build_release(
        self,
        *,
        deployment: Deployment,
        artifact: Artifact,
        project: Project,
    ) -> ReleaseBundle:
        content = _artifact_content(artifact, project)
        size_bytes = len(content.encode("utf-8"))
        if size_bytes > int(settings.agenthub_deployment_max_bytes or 0):
            raise DeploymentProviderError("deployment bundle exceeds maximum size")

        release_id = f"rel_{uuid.uuid4().hex}"
        release_dir = _safe_storage_child(_deployment_root(), f"releases/{release_id}")
        _replace_dir(release_dir)
        entry_path = _entry_path(artifact)
        target = _safe_storage_child(release_dir, entry_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if entry_path != "index.html":
            (release_dir / "index.html").write_text(content, encoding="utf-8")
        bundle_uri = f"static-site://agenthub/releases/{release_id}"
        return ReleaseBundle(
            release_id=release_id,
            bundle_uri=bundle_uri,
            storage_path=str(release_dir),
            entry_path=entry_path,
            size_bytes=size_bytes,
            provider_metadata={
                "provider": self.id,
                "entryPath": entry_path,
                "sizeBytes": size_bytes,
                "storagePath": str(release_dir),
            },
        )

    async def publish(
        self,
        *,
        deployment: Deployment,
        target: DeploymentTarget,
        bundle: ReleaseBundle,
    ) -> PublishResult:
        del deployment
        live_dir = _safe_storage_child(_deployment_root(), f"sites/{target.id}")
        _replace_dir(live_dir)
        shutil.copytree(bundle.storage_path, live_dir, dirs_exist_ok=True)
        self.verify_path(live_dir)
        url = f"{_public_base_url()}/sites/{target.id}/"
        return PublishResult(
            release_id=bundle.release_id,
            url=url,
            bundle_uri=bundle.bundle_uri,
            provider_metadata={
                **bundle.provider_metadata,
                "livePath": str(live_dir),
                "publicBaseUrl": _public_base_url(),
            },
        )

    async def rollback(
        self,
        *,
        deployment: Deployment,
        target: DeploymentTarget,
        target_release_storage_path: str,
        target_release_id: str,
        bundle_uri: str,
    ) -> PublishResult:
        del deployment
        release_dir = Path(target_release_storage_path).resolve()
        self.verify_path(release_dir)
        live_dir = _safe_storage_child(_deployment_root(), f"sites/{target.id}")
        _replace_dir(live_dir)
        shutil.copytree(release_dir, live_dir, dirs_exist_ok=True)
        self.verify_path(live_dir)
        url = f"{_public_base_url()}/sites/{target.id}/"
        return PublishResult(
            release_id=target_release_id,
            url=url,
            bundle_uri=bundle_uri,
            provider_metadata={
                "provider": self.id,
                "livePath": str(live_dir),
                "rolledBackFrom": str(release_dir),
                "publicBaseUrl": _public_base_url(),
            },
        )

    def verify_path(self, root: Path) -> None:
        index = _safe_storage_child(root, "index.html")
        if not index.exists() or not index.is_file():
            raise DeploymentProviderError("published index.html is missing")


def get_deployment_provider(provider_id: str | None = None) -> StaticSiteDeploymentProvider:
    selected = (provider_id or settings.agenthub_deployment_provider or "static_site").strip()
    if selected != "static_site":
        raise DeploymentProviderError(f"unsupported deployment provider: {selected}")
    return StaticSiteDeploymentProvider()


def provider_public_base_url() -> str:
    return _public_base_url()


def _artifact_content(artifact: Artifact, project: Project) -> str:
    content = artifact.content or ""
    if content:
        return content
    if project.workspace_id:
        root = ensure_cloud_workspace(str(project.workspace_id), {"projectId": project.id})
        path = _safe_workspace_child(root, artifact.file_path or "index.html")
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8")
    raise DeploymentProviderError("artifact content not found")


def _entry_path(artifact: Artifact) -> str:
    raw = str(artifact.file_path or "index.html").replace("\\", "/").strip("/")
    if not raw or raw.endswith("/"):
        return "index.html"
    if raw.startswith("../") or "/../" in raw:
        return "index.html"
    return raw


def _deployment_root() -> Path:
    root = Path(settings.agenthub_deployment_root or "./data/deployments").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _public_base_url() -> str:
    configured = (settings.agenthub_deployment_public_base_url or "").strip().rstrip("/")
    if configured:
        return configured
    return f"{settings.agenthub_api_base_url.rstrip('/')}/deployments"


def _replace_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _safe_storage_child(root: Path, subpath: str) -> Path:
    raw = str(subpath or "").replace("\\", "/").strip("/")
    candidate = (root / raw).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise DeploymentProviderError("path outside deployment storage")
    return candidate


def _safe_workspace_child(root: Path, subpath: str) -> Path:
    raw = str(subpath or "").replace("\\", "/").strip("/")
    candidate = (root / (raw or "index.html")).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise DeploymentProviderError("path outside workspace")
    return candidate
