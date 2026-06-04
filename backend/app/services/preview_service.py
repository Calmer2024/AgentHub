"""本机静态预览服务。"""

from __future__ import annotations

import uuid

from .workspace_provider import LocalWorkspaceProvider, WorkspaceNotFoundError


class PreviewError(ValueError):
    pass


class PreviewService:
    def __init__(self, provider: LocalWorkspaceProvider | None = None):
        self.provider = provider or LocalWorkspaceProvider()

    def create_static_preview(self, project_id: str, workspace_path: str) -> dict:
        try:
            index_path = self.provider.safe_resolve(workspace_path, "index.html")
        except WorkspaceNotFoundError:
            raise PreviewError("workspace not found")
        if not index_path.exists() or not index_path.is_file():
            raise FileNotFoundError("index.html not found")
        preview_id = str(uuid.uuid4())
        return {
            "previewId": preview_id,
            "previewUrl": f"/api/projects/{project_id}/preview/{preview_id}/index.html",
        }
