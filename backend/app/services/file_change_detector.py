"""执行前后 hash diff，用于 Workspace Runtime。"""

from __future__ import annotations

import difflib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from .workspace_provider import EXCLUDED_NAMES, hash_file, utc_iso


SNAPSHOT_TEXT_LIMIT = 512 * 1024


@dataclass
class SnapshotResult:
    snapshot_id: str
    label: str
    created_at: str


class FileChangeDetector:
    def create_snapshot(self, workspace_path: str, label: str) -> SnapshotResult:
        root = Path(workspace_path).resolve()
        snapshot_id = str(uuid.uuid4())
        created_at = utc_iso()
        payload = {
            "snapshotId": snapshot_id,
            "label": label,
            "createdAt": created_at,
            "files": self.build_manifest(root),
        }
        snapshot_dir = root / ".agenthub" / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / f"{snapshot_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return SnapshotResult(snapshot_id=snapshot_id, label=label, created_at=created_at)

    def diff_from_snapshot(self, workspace_path: str, snapshot_id: str) -> list[dict]:
        root = Path(workspace_path).resolve()
        snapshot_path = root / ".agenthub" / "snapshots" / f"{snapshot_id}.json"
        if not snapshot_path.exists():
            raise FileNotFoundError("snapshot not found")
        base = json.loads(snapshot_path.read_text(encoding="utf-8"))
        before = base.get("files", {})
        after = self.build_manifest(root)

        changes: list[dict] = []
        all_paths = sorted(set(before.keys()) | set(after.keys()))
        for rel in all_paths:
            old = before.get(rel)
            new = after.get(rel)
            if old and not new:
                change = "deleted"
            elif new and not old:
                change = "created"
            elif old and new and old.get("hash") != new.get("hash"):
                change = "modified"
            else:
                continue
            changes.append({
                "path": rel,
                "change": change,
                "diffPreview": self._diff_preview(rel, old, new),
            })
        return changes

    def build_manifest(self, root: Path) -> dict[str, dict]:
        files: dict[str, dict] = {}
        if not root.exists():
            return files
        for path in sorted(root.rglob("*"), key=lambda p: str(p)):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(root).parts
            if any(part in EXCLUDED_NAMES for part in rel_parts):
                continue
            rel = path.relative_to(root).as_posix()
            size = path.stat().st_size
            files[rel] = {
                "hash": hash_file(path),
                "size": size,
                "content": _read_snapshot_text(path, size),
            }
        return files

    @staticmethod
    def _diff_preview(rel: str, old: dict | None, new: dict | None) -> str:
        old_content = "" if not old else old.get("content") or ""
        new_content = "" if not new else new.get("content") or ""
        if not old_content and not new_content:
            return ""
        return "\n".join(difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            lineterm="",
        ))[:4000]


def _read_snapshot_text(path: Path, size: int) -> str | None:
    if size > SNAPSHOT_TEXT_LIMIT:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
