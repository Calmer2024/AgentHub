"""本机静态预览服务。"""

from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import quote

from .workspace_provider import LocalWorkspaceProvider, WorkspaceNotFoundError


class PreviewError(ValueError):
    pass


class PreviewService:
    def __init__(self, provider: LocalWorkspaceProvider | None = None):
        self.provider = provider or LocalWorkspaceProvider()

    def create_static_preview(
        self,
        project_id: str,
        workspace_path: str,
        entry_path: str | None = None,
    ) -> dict:
        try:
            preview_path = self._resolve_entry(workspace_path, entry_path)
        except WorkspaceNotFoundError:
            raise PreviewError("workspace not found")
        if not preview_path.exists() or not preview_path.is_file():
            raise FileNotFoundError("preview file not found")
        preview_id = str(uuid.uuid4())
        rel = preview_path.relative_to(Path(workspace_path).expanduser().resolve()).as_posix()
        return {
            "previewId": preview_id,
            "previewUrl": f"/api/projects/{project_id}/preview/{preview_id}/{quote(rel, safe='/')}",
        }

    def _resolve_entry(self, workspace_path: str, entry_path: str | None):
        candidate = (entry_path or "index.html").replace("\\", "/").strip("/")
        if not candidate:
            candidate = "index.html"
        target = self.provider.safe_resolve(workspace_path, candidate)
        if target.exists() and target.is_dir():
            return self.provider.safe_resolve(workspace_path, f"{candidate}/index.html")
        return target
