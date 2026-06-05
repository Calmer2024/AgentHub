"""CLI 回复完成后的 Artifact 桥接服务。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..event_bus.event_types import EventType
from ..models import Artifact, Message, Project, Session as DBSession
from .artifact_service import ArtifactDetection, ArtifactService
from .file_change_detector import FileChangeDetector
from .workspace_provider import WorkspaceSecurityError


MAX_ARTIFACT_BYTES = 1024 * 1024
LOW_CONFIDENCE_THRESHOLD = 0.50
AUTO_CREATE_THRESHOLD = 0.80


class ArtifactBridgeError(ValueError):
    """Artifact 桥接失败。"""


class MessageNotFoundForScanError(ArtifactBridgeError):
    """目标消息不存在。"""


class SessionWithoutProjectError(ArtifactBridgeError):
    """目标消息所在会话没有绑定 Project。"""


@dataclass
class ArtifactCandidate:
    artifact_type: str
    title: str
    content: str
    source: str
    confidence: float
    reason: str
    content_hash: str
    file_path: str | None = None
    status: str = "ready"

    def to_metadata(self) -> dict[str, Any]:
        return {
            "artifactType": self.artifact_type,
            "title": self.title,
            "source": self.source,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "contentPreview": self.content[:500],
        }


@dataclass
class ArtifactScanResult:
    created: list[Artifact]
    candidates: list[ArtifactCandidate]
    skipped: list[dict[str, Any]]


class ArtifactOutputBridge:
    """把已完成的 CLI assistant message 转为 Artifact。"""

    def __init__(
        self,
        db: AsyncSession,
        event_bus: Any = None,
        detector: FileChangeDetector | None = None,
    ):
        self.db = db
        self.event_bus = event_bus
        self.detector = detector or FileChangeDetector()
        self.artifacts = ArtifactService(db, event_bus=event_bus)

    async def scan_message(self, message_id: str, *, force: bool = False) -> ArtifactScanResult:
        message = await self.db.get(Message, message_id)
        if not message:
            raise MessageNotFoundForScanError("message not found")
        session, project, workspace_path = await self._message_project(message)
        metadata = _metadata_dict(message)
        trace = metadata.get("executionTrace") if isinstance(metadata.get("executionTrace"), dict) else None
        return await self.scan_completed_message(
            session=session,
            message=message,
            project=project,
            workspace_path=workspace_path,
            visible_content=message.content,
            raw_output_preview=str(metadata.get("rawOutputPreview") or ""),
            execution_trace=trace,
            snapshot_id=None,
            force=force,
        )

    async def scan_completed_message(
        self,
        *,
        session: DBSession,
        message: Message,
        project: Project | None = None,
        workspace_path: str | None = None,
        visible_content: str | None = None,
        raw_output_preview: str | None = None,
        execution_trace: dict[str, Any] | None = None,
        snapshot_id: str | None = None,
        force: bool = False,
    ) -> ArtifactScanResult:
        if not session.project_id:
            raise SessionWithoutProjectError("message session has no project")
        project = project or await self.db.get(Project, session.project_id)
        if not project:
            raise SessionWithoutProjectError("project not found")
        workspace_path = workspace_path or project.workspace_path
        content = visible_content if visible_content is not None else message.content
        trace = execution_trace or _message_trace(message)

        skipped: list[dict[str, Any]] = []
        candidates: list[ArtifactCandidate] = []
        if snapshot_id:
            try:
                changes = self.detector.diff_from_snapshot(workspace_path, snapshot_id)
                candidates.extend(_workspace_candidates(workspace_path, changes))
            except Exception as exc:
                skipped.append({"reason": "workspace_diff_failed", "detail": str(exc)})
        elif force:
            candidates.extend(_workspace_hint_candidates(
                workspace_path,
                content,
                trace,
                source="manual_rescan",
            ))

        candidates.extend(_message_code_block_candidates(content))
        if raw_output_preview:
            candidates.extend(_message_code_block_candidates(raw_output_preview, source="cli_artifact_signal"))

        boosted = [_apply_trace_boost(candidate, trace) for candidate in candidates]
        merged = _merge_candidates(boosted)

        created: list[Artifact] = []
        low_confidence: list[ArtifactCandidate] = []
        for candidate in merged:
            if candidate.confidence >= AUTO_CREATE_THRESHOLD:
                await self._publish_detected(session, message, project, candidate)
                detection = ArtifactDetection(
                    session_id=session.id,
                    message_id=message.id,
                    project_id=project.id,
                    artifact_type=candidate.artifact_type,
                    title=candidate.title,
                    content=candidate.content,
                    status=candidate.status,
                    file_path=candidate.file_path,
                    source=candidate.source,
                    confidence=candidate.confidence,
                    content_hash=candidate.content_hash,
                    task_id=candidate.content_hash,
                    reason=candidate.reason,
                )
                try:
                    artifact, did_create = await self.artifacts.create_from_detection(detection)
                    if did_create:
                        created.append(artifact)
                    else:
                        skipped.append({
                            "reason": "duplicate",
                            "artifactId": artifact.id,
                            "title": artifact.title,
                        })
                except Exception as exc:
                    skipped.append({
                        "reason": "create_failed",
                        "title": candidate.title,
                        "detail": str(exc),
                    })
            elif candidate.confidence >= LOW_CONFIDENCE_THRESHOLD:
                await self._publish_detected(session, message, project, candidate)
                low_confidence.append(candidate)

        _merge_scan_metadata(message, created, low_confidence, skipped)
        await self.db.commit()
        for artifact in created:
            await self.db.refresh(artifact)
        return ArtifactScanResult(created=created, candidates=low_confidence, skipped=skipped)

    async def _message_project(self, message: Message) -> tuple[DBSession, Project, str]:
        session = await self.db.get(DBSession, message.session_id)
        if not session or not session.project_id:
            raise SessionWithoutProjectError("message session has no project")
        project = await self.db.get(Project, session.project_id)
        if not project:
            raise SessionWithoutProjectError("project not found")
        return session, project, project.workspace_path

    async def _publish_detected(
        self,
        session: DBSession,
        message: Message,
        project: Project,
        candidate: ArtifactCandidate,
    ) -> None:
        if not self.event_bus:
            return
        await self.event_bus.publish(EventType.ARTIFACT_DETECTED, {
            "sessionId": session.id,
            "messageId": message.id,
            "projectId": project.id,
            "agentId": message.source_id,
            "artifactType": candidate.artifact_type,
            "title": candidate.title,
            "source": candidate.source,
            "confidence": round(candidate.confidence, 2),
            "filePath": candidate.file_path,
            "contentHash": candidate.content_hash,
            "reason": candidate.reason,
        })


def artifact_to_event_payload(artifact: Artifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "sessionId": artifact.session_id,
        "messageId": artifact.message_id,
        "projectId": artifact.project_id,
        "type": artifact.type,
        "title": artifact.title,
        "content": artifact.content,
        "status": artifact.status,
        "version": artifact.version or 1,
        "parentArtifactId": artifact.parent_artifact_id,
        "filePath": artifact.file_path,
        "previewId": artifact.preview_id,
        "source": artifact.source,
        "createdAt": artifact.created_at.isoformat() if artifact.created_at else "",
    }


def _workspace_candidates(workspace_path: str, changes: list[dict]) -> list[ArtifactCandidate]:
    candidates: list[ArtifactCandidate] = []
    root = Path(workspace_path).resolve()
    changed = [_normalized_change(change) for change in changes]
    changed = [change for change in changed if change["path"]]
    text_changes = [change for change in changed if change["change"] in {"created", "modified"}]

    for change in text_changes:
        path = str(change["path"])
        if Path(path).suffix.lower() not in {".html", ".htm"}:
            continue
        content, status, reason = _read_workspace_text(root, path)
        if status == "ready" and not _looks_like_html(content):
            continue
        candidates.append(_candidate(
            artifact_type="web_preview",
            title=Path(path).name or "网页预览",
            content=content if status == "ready" else reason,
            source="workspace_diff",
            confidence=0.90,
            reason=reason if status == "error" else "workspace html file changed",
            file_path=path,
            status=status,
        ))

    if len(changed) >= 2 and any(_is_frontend_entry(str(item["path"])) for item in changed):
        payload = {
            "changes": [
                {
                    "path": item["path"],
                    "change": item["change"],
                    "diffPreview": str(item.get("diffPreview") or "")[:4000],
                }
                for item in sorted(changed, key=lambda value: str(value["path"]))
            ],
        }
        candidates.append(_candidate(
            artifact_type="file_tree",
            title="本次文件变更",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            source="workspace_diff",
            confidence=0.90,
            reason="multiple project files changed",
            content_hash_basis="workspace_diff:" + "|".join(
                f"{item['change']}:{item['path']}:{item.get('diffPreview') or ''}"
                for item in sorted(changed, key=lambda value: str(value["path"]))
            ),
        ))

    diff_parts = [
        str(item.get("diffPreview") or "")
        for item in changed
        if _looks_like_diff(str(item.get("diffPreview") or ""))
    ]
    combined_diff = "\n".join(part for part in diff_parts if part)
    if combined_diff and len(combined_diff.encode("utf-8")) <= MAX_ARTIFACT_BYTES:
        file_path = str(changed[0]["path"]) if len(changed) == 1 else None
        title = (
            f"{Path(str(changed[0]['path'])).name} Diff"
            if len(changed) == 1 else "本次代码 Diff"
        )
        candidates.append(_candidate(
            artifact_type="code_diff",
            title=title,
            content=combined_diff,
            source="workspace_diff",
            confidence=0.86,
            reason="workspace unified diff",
            file_path=file_path,
        ))

    return candidates


def _workspace_hint_candidates(
    workspace_path: str,
    text: str,
    trace: dict[str, Any] | None,
    *,
    source: str,
) -> list[ArtifactCandidate]:
    """Build workspace candidates during manual rescan when the original snapshot is gone."""
    root = Path(workspace_path).resolve()
    paths = _extract_workspace_path_hints(text, trace)
    candidates: list[ArtifactCandidate] = []
    existing_paths: list[str] = []
    for rel_path in paths:
        target = (root / rel_path).resolve()
        if not target.exists() or not target.is_file():
            continue
        existing_paths.append(rel_path)
        suffix = Path(rel_path).suffix.lower()
        if suffix in {".html", ".htm"}:
            content, status, reason = _read_workspace_text(root, rel_path)
            if status == "ready" and not _looks_like_html(content):
                continue
            candidates.append(_candidate(
                artifact_type="web_preview",
                title=Path(rel_path).name or "网页预览",
                content=content if status == "ready" else reason,
                source=source,
                confidence=0.82,
                reason=reason if status == "error" else "workspace file hint matched",
                file_path=rel_path,
                status=status,
            ))
        elif suffix in {".md", ".markdown"}:
            content, status, reason = _read_workspace_text(root, rel_path)
            if status == "ready" and not _looks_like_document(content):
                continue
            candidates.append(_candidate(
                artifact_type="document",
                title=_document_title(content) or Path(rel_path).name,
                content=content if status == "ready" else reason,
                source=source,
                confidence=0.80,
                reason=reason if status == "error" else "workspace document hint matched",
                file_path=rel_path,
                status=status,
            ))

    if len(existing_paths) >= 2 and any(_is_frontend_entry(path) for path in existing_paths):
        payload = {
            "changes": [
                {"path": path, "change": "present", "diffPreview": ""}
                for path in sorted(existing_paths)
            ],
        }
        candidates.append(_candidate(
            artifact_type="file_tree",
            title="当前文件变更线索",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            source=source,
            confidence=0.80,
            reason="multiple workspace file hints matched",
            content_hash_basis="manual_rescan:" + "|".join(sorted(existing_paths)),
        ))
    return candidates


def _message_code_block_candidates(
    text: str,
    *,
    source: str = "message_code_block",
) -> list[ArtifactCandidate]:
    candidates: list[ArtifactCandidate] = []
    for index, match in enumerate(_closed_code_blocks(text), start=1):
        language = match["language"].lower()
        content = match["content"].strip("\n")
        if not content:
            continue
        size = len(content.encode("utf-8"))
        if size > MAX_ARTIFACT_BYTES:
            continue
        if language in {"html", "htm"} and _looks_like_html(content):
            candidates.append(_candidate(
                artifact_type="web_preview",
                title=_numbered_title("网页预览", index),
                content=content,
                source=source,
                confidence=0.85,
                reason="complete fenced html block",
            ))
        elif language in {"jsx", "tsx", "vue", "svelte"} and _looks_like_component(content):
            candidates.append(_candidate(
                artifact_type="web_preview",
                title=_numbered_title("组件预览", index),
                content=content,
                source=source,
                confidence=0.82,
                reason="complete fenced component block",
            ))
        elif language in {"diff", "patch"} and _looks_like_diff(content):
            candidates.append(_candidate(
                artifact_type="code_diff",
                title=_numbered_title("代码 Diff", index),
                content=content,
                source=source,
                confidence=0.86,
                reason="complete fenced diff block",
            ))
        elif language in {"md", "markdown"} and _looks_like_document(content):
            candidates.append(_candidate(
                artifact_type="document",
                title=_document_title(content) or _numbered_title("文档候选", index),
                content=content,
                source=source,
                confidence=0.65,
                reason="markdown heading structure without explicit output",
            ))
    return candidates


def _closed_code_blocks(text: str) -> list[dict[str, str]]:
    pattern = re.compile(r"```([A-Za-z0-9_-]*)[^\n]*\n(.*?)```", re.DOTALL)
    return [
        {
            "language": match.group(1) or "",
            "content": match.group(2),
        }
        for match in pattern.finditer(text or "")
    ]


def _candidate(
    *,
    artifact_type: str,
    title: str,
    content: str,
    source: str,
    confidence: float,
    reason: str,
    file_path: str | None = None,
    status: str = "ready",
    content_hash_basis: str | None = None,
) -> ArtifactCandidate:
    hash_basis = content_hash_basis if content_hash_basis is not None else content
    content_hash = hashlib.sha256(hash_basis.encode("utf-8", errors="replace")).hexdigest()
    return ArtifactCandidate(
        artifact_type=artifact_type,
        title=title,
        content=content,
        source=source,
        confidence=max(0.0, min(1.0, confidence)),
        reason=reason,
        content_hash=content_hash,
        file_path=file_path.replace("\\", "/") if file_path else None,
        status=status,
    )


def _apply_trace_boost(candidate: ArtifactCandidate, trace: dict[str, Any] | None) -> ArtifactCandidate:
    if not trace:
        return candidate
    items = trace.get("items")
    if not isinstance(items, list):
        return candidate
    boost = 0.0
    for item in items:
        if not isinstance(item, dict):
            continue
        haystack = "\n".join(
            str(item.get(key) or "")
            for key in ("kind", "target", "command", "title", "detail", "text", "action")
        ).lower()
        if candidate.file_path and _path_matches(candidate.file_path, haystack):
            boost = max(boost, 0.10)
            action = str(item.get("action") or "").lower()
            if action in {"write", "edit", "run"} or any(word in haystack for word in ("write", "edit", "cat >")):
                boost = max(boost, 0.15)
        elif candidate.source == "message_code_block" and "artifact" in haystack:
            boost = max(boost, 0.05)
    if boost <= 0:
        return candidate
    candidate.confidence = max(0.0, min(1.0, candidate.confidence + boost))
    candidate.reason = f"{candidate.reason}; trace corroborated"
    return candidate


def _merge_candidates(candidates: list[ArtifactCandidate]) -> list[ArtifactCandidate]:
    merged: dict[tuple[str, str, str], ArtifactCandidate] = {}
    for candidate in candidates:
        key = (
            candidate.artifact_type,
            candidate.file_path or "",
            candidate.content_hash,
        )
        current = merged.get(key)
        if not current or candidate.confidence > current.confidence:
            merged[key] = candidate
    return sorted(
        merged.values(),
        key=lambda item: (item.confidence, item.source == "workspace_diff"),
        reverse=True,
    )


def _merge_scan_metadata(
    message: Message,
    created: list[Artifact],
    candidates: list[ArtifactCandidate],
    skipped: list[dict[str, Any]],
) -> None:
    metadata = _metadata_dict(message)
    metadata["artifactBridge"] = {
        "status": "completed",
        "createdCount": len(created),
        "candidateCount": len(candidates),
        "skippedCount": len(skipped),
        "completedAt": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }
    if candidates:
        metadata["artifactCandidates"] = [candidate.to_metadata() for candidate in candidates]
    else:
        metadata.pop("artifactCandidates", None)
    message.metadata_json = json.dumps(metadata, ensure_ascii=False)


def _message_trace(message: Message) -> dict[str, Any] | None:
    metadata = _metadata_dict(message)
    trace = metadata.get("executionTrace")
    return trace if isinstance(trace, dict) else None


def _metadata_dict(message: Message) -> dict[str, Any]:
    raw = getattr(message, "metadata_json", None)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalized_change(change: dict) -> dict[str, Any]:
    return {
        "path": str(change.get("path") or "").replace("\\", "/"),
        "change": str(change.get("change") or ""),
        "diffPreview": str(change.get("diffPreview") or ""),
    }


def _read_workspace_text(root: Path, rel_path: str) -> tuple[str, str, str]:
    try:
        target = (root / rel_path).resolve()
        if target != root and root not in target.parents:
            raise WorkspaceSecurityError("path outside workspace")
        size = target.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            return "", "error", "内容过大，无法在线预览"
        return target.read_text(encoding="utf-8", errors="replace"), "ready", "workspace file read"
    except Exception as exc:
        return "", "error", f"文件读取失败: {exc}"


def _looks_like_html(content: str) -> bool:
    return bool(re.search(r"<!doctype\s+html|<html\b|<body\b|<div\b|<main\b|<section\b", content, re.I))


def _looks_like_component(content: str) -> bool:
    return bool(re.search(r"export\s+default|function\s+\w+|return\s*\(", content)) and "<" in content and ">" in content


def _looks_like_diff(content: str) -> bool:
    return "@@" in content or "--- a/" in content or "+++ b/" in content


def _looks_like_document(content: str) -> bool:
    return bool(re.search(r"^#{1,3}\s+\S+", content, re.MULTILINE)) and len(content.strip()) >= 120


def _document_title(content: str) -> str | None:
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip()[:80] if match else None


def _is_frontend_entry(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    names = {
        "package.json",
        "vite.config.ts",
        "vite.config.js",
        "index.html",
        "src/main.tsx",
        "src/main.jsx",
        "src/app.tsx",
        "src/app.jsx",
    }
    return normalized in names or normalized.endswith(("/src/app.tsx", "/src/main.tsx", "/index.html"))


def _path_matches(path: str, haystack: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    basename = Path(normalized).name
    return normalized in haystack.replace("\\", "/") or bool(basename and basename in haystack)


def _numbered_title(base: str, index: int) -> str:
    return base if index == 1 else f"{base} {index}"


def _extract_workspace_path_hints(text: str, trace: dict[str, Any] | None) -> list[str]:
    haystacks = [text or ""]
    if trace and isinstance(trace.get("items"), list):
        for item in trace["items"]:
            if not isinstance(item, dict):
                continue
            haystacks.append("\n".join(
                str(item.get(key) or "")
                for key in ("target", "command", "title", "detail", "text", "raw")
            ))
    seen: set[str] = set()
    paths: list[str] = []
    pattern = re.compile(
        r"(?<![\w./\\-])([A-Za-z0-9_.@/\\-]+\.(?:html?|md|markdown|tsx|jsx|js|ts|json|css))(?![\w.-])",
        re.I,
    )
    for haystack in haystacks:
        for match in pattern.finditer(haystack):
            value = match.group(1).replace("\\", "/").strip("/ ")
            if not value or value.startswith((".", "/")) or ".." in Path(value).parts:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            paths.append(value)
    return paths
