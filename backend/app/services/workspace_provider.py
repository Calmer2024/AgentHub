"""本机 workspace 文件系统访问能力。"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import re
import time
import zipfile
from dataclasses import dataclass
from io import BytesIO
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
MAX_SEARCH_FILE_BYTES = 1024 * 1024
TEXT_MEDIA_PREFIXES = ("text/",)
TEXT_MEDIA_TYPES = {
    "application/json",
    "application/javascript",
    "application/typescript",
    "application/xml",
    "application/x-yaml",
}
EDITABLE_EXTENSIONS = {
    ".bat",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".env",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".less",
    ".lock",
    ".log",
    ".md",
    ".mjs",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
PROTECTED_NAMES = {".agenthub", ".git"}


class WorkspaceSecurityError(ValueError):
    pass


class WorkspaceFileTooLargeError(ValueError):
    pass


class WorkspaceNotFoundError(ValueError):
    pass


class WorkspaceFileConflictError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        current_content: str = "",
        current_etag: str | None = None,
        current_mtime: float | None = None,
    ):
        super().__init__(message)
        self.current_content = current_content
        self.current_etag = current_etag
        self.current_mtime = current_mtime


class WorkspaceFileExistsError(ValueError):
    pass


@dataclass
class FileEntry:
    path: str
    name: str
    type: str
    size: int
    mtime: float | None = None
    etag: str | None = None
    media_type: str | None = None
    extension: str | None = None
    editable: bool = False
    previewable: bool = False
    preview_kind: str = "file"
    readonly_reason: str | None = None
    has_children: bool = False

    def to_api(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "type": self.type,
            "size": self.size,
            "mtime": self.mtime,
            "etag": self.etag,
            "mediaType": self.media_type,
            "extension": self.extension,
            "editable": self.editable,
            "previewable": self.previewable,
            "previewKind": self.preview_kind,
            "readonlyReason": self.readonly_reason,
            "hasChildren": self.has_children,
        }


class LocalWorkspaceProvider:
    """只允许在单个 Project workspace 内解析和读取路径。"""

    def ensure_workspace(self, workspace_path: str, metadata: dict[str, Any]) -> None:
        root = Path(workspace_path)
        root.mkdir(parents=True, exist_ok=True)
        agenthub = root / ".agenthub"
        (agenthub / "snapshots").mkdir(parents=True, exist_ok=True)
        (agenthub / "build-logs").mkdir(parents=True, exist_ok=True)
        (agenthub / "trash").mkdir(parents=True, exist_ok=True)
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
            if not _is_inside(path, root):
                continue
            rel_parts = path.relative_to(root).parts
            if any(part in EXCLUDED_NAMES for part in rel_parts):
                continue
            entries.append(self._entry_for_path(root, path, include_hash=False))
        return entries

    def stat_path(self, workspace_path: str, path: str) -> FileEntry:
        target = self.safe_resolve(workspace_path, path)
        if not target.exists():
            raise WorkspaceNotFoundError("path not found")
        return self._entry_for_path(Path(workspace_path).resolve(), target, include_hash=True)

    def read_text_file(self, workspace_path: str, path: str) -> tuple[str, FileEntry]:
        target = self.safe_resolve(workspace_path, path)
        if not target.exists() or not target.is_file():
            raise WorkspaceNotFoundError("file not found")
        size = target.stat().st_size
        if size > MAX_FILE_READ_BYTES:
            raise WorkspaceFileTooLargeError("file too large")
        entry = self._entry_for_path(Path(workspace_path).resolve(), target, include_hash=True)
        if entry.readonly_reason == "binary":
            return "", entry
        return target.read_text(encoding="utf-8", errors="replace"), entry

    def write_text_file(
        self,
        workspace_path: str,
        path: str,
        content: str,
        *,
        base_etag: str | None = None,
        force: bool = False,
    ) -> tuple[str, FileEntry]:
        target = self.safe_resolve(workspace_path, path)
        root = Path(workspace_path).resolve()
        self._assert_mutable_path(root, target)
        if target.exists() and target.is_dir():
            raise WorkspaceSecurityError("path must be a file")

        if target.exists() and base_etag and not force:
            current_etag = hash_file(target)
            if current_etag != base_etag:
                current_content = ""
                try:
                    if target.stat().st_size <= MAX_FILE_READ_BYTES and not _looks_binary(target):
                        current_content = target.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    current_content = ""
                raise WorkspaceFileConflictError(
                    "file changed since it was opened",
                    current_content=current_content,
                    current_etag=current_etag,
                    current_mtime=target.stat().st_mtime,
                )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return content, self._entry_for_path(root, target, include_hash=True)

    def create_text_file(
        self,
        workspace_path: str,
        path: str,
        content: str = "",
        *,
        overwrite: bool = False,
    ) -> tuple[str, FileEntry]:
        target = self.safe_resolve(workspace_path, path)
        root = Path(workspace_path).resolve()
        self._assert_mutable_path(root, target)
        if target.exists() and not overwrite:
            raise WorkspaceFileExistsError("file already exists")
        if target.exists() and target.is_dir():
            raise WorkspaceFileExistsError("directory already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return content, self._entry_for_path(root, target, include_hash=True)

    def create_directory(self, workspace_path: str, path: str) -> FileEntry:
        target = self.safe_resolve(workspace_path, path)
        root = Path(workspace_path).resolve()
        self._assert_mutable_path(root, target)
        if target.exists() and not target.is_dir():
            raise WorkspaceFileExistsError("file already exists")
        target.mkdir(parents=True, exist_ok=True)
        return self._entry_for_path(root, target, include_hash=False)

    def move_path(
        self,
        workspace_path: str,
        source_path: str,
        target_path: str,
        *,
        overwrite: bool = False,
    ) -> FileEntry:
        root = Path(workspace_path).resolve()
        source = self.safe_resolve(workspace_path, source_path)
        target = self.safe_resolve(workspace_path, target_path)
        if not source.exists():
            raise WorkspaceNotFoundError("source path not found")
        self._assert_mutable_path(root, source)
        self._assert_mutable_path(root, target)
        if source.is_dir() and (target == source or source in target.parents):
            raise WorkspaceSecurityError("cannot move a directory into itself")
        if target.exists() and not overwrite:
            raise WorkspaceFileExistsError("target path already exists")
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        return self._entry_for_path(root, target, include_hash=target.is_file())

    def delete_paths(
        self,
        workspace_path: str,
        paths: list[str],
        *,
        use_trash: bool = True,
    ) -> list[dict[str, Any]]:
        root = Path(workspace_path).resolve()
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        deleted: list[dict[str, Any]] = []
        for raw_path in paths:
            target = self.safe_resolve(workspace_path, raw_path)
            if not target.exists():
                raise WorkspaceNotFoundError("path not found")
            self._assert_mutable_path(root, target)
            rel = target.relative_to(root).as_posix()
            if use_trash:
                trash_target = root / ".agenthub" / "trash" / timestamp / rel
                trash_target = _next_collision_free_path(trash_target)
                trash_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(trash_target))
                deleted.append({
                    "path": rel,
                    "status": "trashed",
                    "trashPath": trash_target.relative_to(root).as_posix(),
                })
            else:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                deleted.append({"path": rel, "status": "deleted", "trashPath": None})
        return deleted

    def search_paths(
        self,
        workspace_path: str,
        query: str,
        *,
        include_content: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        needle = query.strip().lower()
        if not needle:
            return []

        results: list[dict[str, Any]] = []
        for entry in self.list_tree(workspace_path):
            if len(results) >= limit:
                break
            if needle in entry.path.lower():
                results.append({
                    "path": entry.path,
                    "type": entry.type,
                    "matchType": "path",
                    "line": None,
                    "snippet": entry.path,
                })
                continue
            if not include_content or entry.type != "file" or not entry.editable or entry.size > MAX_SEARCH_FILE_BYTES:
                continue
            try:
                target = self.safe_resolve(workspace_path, entry.path)
                for index, line in enumerate(target.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                    if needle in line.lower():
                        results.append({
                            "path": entry.path,
                            "type": "file",
                            "matchType": "content",
                            "line": index,
                            "snippet": line.strip()[:240],
                        })
                        break
            except (OSError, UnicodeError, WorkspaceSecurityError, WorkspaceNotFoundError):
                continue
        return results

    def zip_path(self, workspace_path: str, path: str | None = None) -> tuple[bytes, str]:
        target = self.safe_resolve(workspace_path, path)
        if not target.exists():
            raise WorkspaceNotFoundError("path not found")
        root = Path(workspace_path).resolve()
        base_name = target.name or root.name or "workspace"
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            targets = [target] if target.is_file() else sorted(target.rglob("*"), key=lambda p: str(p))
            for item in targets:
                if not item.is_file() or not _is_inside(item, root):
                    continue
                rel_parts = item.relative_to(root).parts
                if any(part in EXCLUDED_NAMES for part in rel_parts):
                    continue
                archive.write(item, item.relative_to(root).as_posix())
        return buffer.getvalue(), f"{base_name}.zip"

    def _entry_for_path(self, root: Path, path: Path, *, include_hash: bool) -> FileEntry:
        rel = _to_posix(path.relative_to(root))
        name = path.name or root.name
        is_dir = path.is_dir()
        stat = path.stat()
        extension = "" if is_dir else path.suffix.lower()
        media_type = None if is_dir else _media_type_for_path(path)
        size = 0 if is_dir else stat.st_size
        binary = False if is_dir else _looks_binary(path)
        editable = False if is_dir else not binary and size <= MAX_FILE_READ_BYTES and (
            extension in EDITABLE_EXTENSIONS
            or (media_type or "").startswith(TEXT_MEDIA_PREFIXES)
            or media_type in TEXT_MEDIA_TYPES
        )
        preview_kind = _preview_kind(path, media_type, is_dir, binary)
        previewable = is_dir or editable or preview_kind in {"image", "pdf"}
        readonly_reason = None
        if not is_dir and size > MAX_FILE_READ_BYTES:
            readonly_reason = "too_large"
        elif binary:
            readonly_reason = "binary"
        return FileEntry(
            path=rel,
            name=name,
            type="dir" if is_dir else "file",
            size=size,
            mtime=stat.st_mtime,
            etag=hash_file(path) if include_hash and not is_dir else None,
            media_type=media_type,
            extension=extension[1:] if extension.startswith(".") else extension,
            editable=editable,
            previewable=previewable,
            preview_kind=preview_kind,
            readonly_reason=readonly_reason,
            has_children=_has_visible_children(root, path) if is_dir else False,
        )

    def _assert_mutable_path(self, root: Path, target: Path) -> None:
        if target == root:
            raise WorkspaceSecurityError("cannot modify workspace root")
        rel_parts = target.relative_to(root).parts
        if any(part in PROTECTED_NAMES for part in rel_parts):
            raise WorkspaceSecurityError("cannot modify protected workspace metadata")


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


def _is_inside(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return resolved == root or root in resolved.parents


def _media_type_for_path(path: Path) -> str:
    if path.suffix.lower() == ".js":
        return "text/javascript"
    if path.suffix.lower() == ".css":
        return "text/css"
    media_type, _ = mimetypes.guess_type(path.name)
    return media_type or "application/octet-stream"


def _looks_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(8192)
    except OSError:
        return True
    return b"\0" in sample


def _preview_kind(path: Path, media_type: str | None, is_dir: bool, binary: bool) -> str:
    if is_dir:
        return "directory"
    extension = path.suffix.lower()
    if extension in {".md", ".markdown"}:
        return "markdown"
    if extension in {".html", ".htm"}:
        return "html"
    if extension == ".json":
        return "json"
    if extension in IMAGE_EXTENSIONS or (media_type or "").startswith("image/"):
        return "image"
    if extension == ".pdf" or media_type == "application/pdf":
        return "pdf"
    if binary:
        return "binary"
    if extension in EDITABLE_EXTENSIONS:
        return "code"
    return "text"


def _has_visible_children(root: Path, path: Path) -> bool:
    try:
        for child in path.iterdir():
            if not _is_inside(child, root):
                continue
            rel_parts = child.relative_to(root).parts
            if any(part in EXCLUDED_NAMES for part in rel_parts):
                continue
            return True
    except OSError:
        return False
    return False


def _next_collision_free_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(2, 1000):
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    return parent / f"{stem}-{int(time.time())}{suffix}"
