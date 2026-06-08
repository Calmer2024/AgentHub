"""本机 workspace 文件系统访问能力。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.timezone import china_now_iso

EXCLUDED_NAMES = {
    ".agenthub",
    ".agenthub-cli-stdin.txt",
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
}
MAX_FILE_READ_BYTES = 10 * 1024 * 1024


class WorkspaceSecurityError(ValueError):
    pass


class WorkspaceFileTooLargeError(ValueError):
    pass


class WorkspaceNotFoundError(ValueError):
    pass


@dataclass
class FileEntry:
    path: str
    type: str
    size: int


class LocalWorkspaceProvider:
    """只允许在单个 Project workspace 内解析和读取路径。"""

    def ensure_workspace(self, workspace_path: str, metadata: dict[str, Any]) -> None:
        root = Path(workspace_path)
        root.mkdir(parents=True, exist_ok=True)
        agenthub = root / ".agenthub"
        (agenthub / "snapshots").mkdir(parents=True, exist_ok=True)
        (agenthub / "build-logs").mkdir(parents=True, exist_ok=True)
        (agenthub / "project.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def safe_resolve(self, workspace_path: str, subpath: str | None = None) -> Path:
        root = Path(workspace_path).resolve()
        if not root.exists():
            raise WorkspaceNotFoundError("workspace not found")

        raw = (subpath or "").replace("\\", "/").strip()
        if raw.startswith("/") or raw.startswith("~"):
            raise WorkspaceSecurityError("path outside workspace")

        candidate = (root / raw).resolve()
        if candidate != root and root not in candidate.parents:
            raise WorkspaceSecurityError("path outside workspace")
        return candidate

    def list_tree(self, workspace_path: str, subpath: str | None = None) -> list[FileEntry]:
        base = self.safe_resolve(workspace_path, subpath)
        if not base.exists():
            raise WorkspaceNotFoundError("path not found")

        root = Path(workspace_path).resolve()
        entries: list[FileEntry] = []
        targets = [base] if base.is_file() else sorted(base.rglob("*"), key=lambda p: str(p))
        for path in targets:
            rel_parts = path.relative_to(root).parts
            if any(part in EXCLUDED_NAMES for part in rel_parts):
                continue
            rel = _to_posix(path.relative_to(root))
            entries.append(FileEntry(
                path=rel,
                type="dir" if path.is_dir() else "file",
                size=0 if path.is_dir() else path.stat().st_size,
            ))
        return entries

    def read_text_file(self, workspace_path: str, path: str) -> tuple[str, int]:
        target = self.safe_resolve(workspace_path, path)
        if not target.exists() or not target.is_file():
            raise WorkspaceNotFoundError("file not found")
        size = target.stat().st_size
        if size > MAX_FILE_READ_BYTES:
            raise WorkspaceFileTooLargeError("file too large")
        return target.read_text(encoding="utf-8", errors="replace"), size


def sanitize_dir_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip(".-")
    return slug or "project"


def utc_iso() -> str:
    return china_now_iso()


def _to_posix(path: Path) -> str:
    return path.as_posix()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
