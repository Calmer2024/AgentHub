"""Phase 10 云端 workspace 的本机隔离存储实现。"""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path

from ..config import settings
from .workspace_provider import utc_iso


class CloudStorageError(ValueError):
    pass


def cloud_storage_root() -> Path:
    root = Path(settings.agenthub_workspace_root).expanduser().resolve() / ".cloud-workspaces"
    root.mkdir(parents=True, exist_ok=True)
    return root


def cloud_workspace_path(workspace_id: str) -> Path:
    return _safe_child(cloud_storage_root(), workspace_id)


def cloud_snapshot_path(workspace_id: str, snapshot_id: str) -> Path:
    return _safe_child(cloud_storage_root() / ".snapshots" / workspace_id, snapshot_id)


def ensure_cloud_workspace(workspace_id: str, metadata: dict | None = None) -> Path:
    path = cloud_workspace_path(workspace_id)
    path.mkdir(parents=True, exist_ok=True)
    marker = path / ".agenthub" / "cloud-workspace.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        marker.write_text(
            json.dumps({
                "workspaceId": workspace_id,
                "workspaceMode": "cloud",
                "createdAt": utc_iso(),
                **(metadata or {}),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return path


def copy_workspace_snapshot(workspace_id: str, snapshot_id: str) -> Path:
    source = ensure_cloud_workspace(workspace_id)
    target = cloud_snapshot_path(workspace_id, snapshot_id)
    _replace_directory(source, target)
    return target


def restore_workspace_snapshot(workspace_id: str, snapshot_id: str) -> Path:
    source = cloud_snapshot_path(workspace_id, snapshot_id)
    if not source.exists() or not source.is_dir():
        raise CloudStorageError("snapshot storage not found")
    target = ensure_cloud_workspace(workspace_id)
    _replace_directory(source, target)
    return target


def extract_zip_to_workspace(workspace_id: str, data: bytes) -> list[str]:
    target = ensure_cloud_workspace(workspace_id)
    extracted: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                name = _safe_zip_name(info.filename)
                if not name:
                    continue
                dest = _safe_child(target, name)
                if info.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, dest.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
                extracted.append(name)
    except zipfile.BadZipFile as exc:
        raise CloudStorageError("invalid zip file") from exc
    return extracted


def workspace_disk_bytes(workspace_id: str) -> int:
    root = ensure_cloud_workspace(workspace_id)
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def _replace_directory(source: Path, target: Path) -> None:
    root = cloud_storage_root()
    resolved_target = target.resolve()
    if root != resolved_target and root not in resolved_target.parents:
        raise CloudStorageError("target outside cloud storage root")
    if resolved_target.exists():
        shutil.rmtree(resolved_target)
    resolved_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, resolved_target)


def _safe_child(root: Path, name: str) -> Path:
    if not str(name).strip():
        raise CloudStorageError("empty path segment")
    candidate = (root / str(name)).resolve()
    root = root.resolve()
    if candidate != root and root not in candidate.parents:
        raise CloudStorageError("path escapes cloud storage root")
    return candidate


def _safe_zip_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("../") or "/../" in normalized:
        raise CloudStorageError("zip file contains unsafe path")
    if Path(normalized).is_absolute():
        raise CloudStorageError("zip file contains absolute path")
    return normalized
