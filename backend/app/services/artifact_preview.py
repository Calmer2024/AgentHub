"""Artifact 预览格式推断。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
}

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}
PDF_EXTENSIONS = {".pdf"}
PRESENTATION_EXTENSIONS = {".ppt", ".pptx", ".key"}
WORD_EXTENSIONS = {".doc", ".docx", ".rtf"}
SPREADSHEET_EXTENSIONS = {".xls", ".xlsx", ".csv", ".tsv"}
TEXT_EXTENSIONS = {
    ".txt",
    ".log",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".css",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".py",
    ".sql",
    ".sh",
    ".ps1",
}


@dataclass(frozen=True)
class ArtifactPreviewInfo:
    kind: str
    label: str
    media_type: str | None
    extension: str | None
    can_inline: bool
    is_binary: bool

    def to_payload(self, artifact_id: str, has_file: bool) -> dict[str, str | bool | None]:
        raw_url = f"/api/artifacts/{quote(artifact_id, safe='')}/raw" if has_file else None
        return {
            "previewKind": self.kind,
            "previewLabel": self.label,
            "mediaType": self.media_type,
            "fileExtension": self.extension,
            "canInlinePreview": self.can_inline,
            "isBinary": self.is_binary,
            "rawUrl": raw_url,
            "downloadUrl": f"{raw_url}?download=true" if raw_url else None,
        }


def infer_artifact_preview(
    *,
    artifact_type: str,
    title: str | None,
    content: str | None,
    file_path: str | None,
) -> ArtifactPreviewInfo:
    extension = _extension(file_path or title)
    clean_type = (artifact_type or "").strip()
    body = content or ""

    if clean_type == "code_diff":
        return ArtifactPreviewInfo("diff", "代码 Diff", "text/x-diff", extension, True, False)
    if clean_type == "file_tree":
        return ArtifactPreviewInfo("file_tree", "文件变更", "application/json", extension, True, False)
    if clean_type == "web_preview":
        return ArtifactPreviewInfo("html", "网页预览", "text/html", extension or ".html", True, False)

    if extension in MARKDOWN_EXTENSIONS:
        return ArtifactPreviewInfo("markdown", "Markdown 文档", "text/markdown", extension, True, False)
    if extension in PDF_EXTENSIONS:
        return ArtifactPreviewInfo("pdf", "PDF 文档", "application/pdf", extension, True, True)
    if extension in IMAGE_MEDIA_TYPES:
        return ArtifactPreviewInfo("image", "图片", IMAGE_MEDIA_TYPES[extension], extension, True, True)
    if extension in PRESENTATION_EXTENSIONS:
        return ArtifactPreviewInfo(
            "presentation",
            "演示文稿",
            _office_media_type(extension),
            extension,
            False,
            True,
        )
    if extension in WORD_EXTENSIONS:
        return ArtifactPreviewInfo("word", "Word 文档", _office_media_type(extension), extension, False, True)
    if extension in SPREADSHEET_EXTENSIONS:
        media_type = "text/csv" if extension in {".csv", ".tsv"} else _office_media_type(extension)
        return ArtifactPreviewInfo("spreadsheet", "表格文件", media_type, extension, extension in {".csv", ".tsv"}, extension not in {".csv", ".tsv"})
    if extension in TEXT_EXTENSIONS:
        return ArtifactPreviewInfo("text", "文本文件", _text_media_type(extension), extension, True, False)
    if _looks_like_markdown(body):
        return ArtifactPreviewInfo("markdown", "Markdown 文档", "text/markdown", extension, True, False)
    if _looks_like_pdf(body):
        return ArtifactPreviewInfo("pdf", "PDF 文档", "application/pdf", extension, True, True)
    return ArtifactPreviewInfo("text", "文档", "text/plain", extension, True, False)


def artifact_preview_payload(artifact) -> dict[str, str | bool | None]:
    info = infer_artifact_preview(
        artifact_type=str(getattr(artifact, "type", "") or ""),
        title=str(getattr(artifact, "title", "") or ""),
        content=str(getattr(artifact, "content", "") or ""),
        file_path=getattr(artifact, "file_path", None),
    )
    return info.to_payload(str(getattr(artifact, "id")), bool(getattr(artifact, "file_path", None)))


def _extension(path_or_title: str | None) -> str | None:
    if not path_or_title:
        return None
    suffix = Path(path_or_title.strip()).suffix.lower()
    return suffix or None


def _looks_like_markdown(content: str) -> bool:
    return bool(re.search(r"^#{1,6}\s+\S+", content, re.MULTILINE))


def _looks_like_pdf(content: str) -> bool:
    return content.startswith("%PDF")


def _text_media_type(extension: str | None) -> str:
    if extension == ".json":
        return "application/json"
    if extension in {".yaml", ".yml"}:
        return "application/yaml"
    if extension == ".xml":
        return "application/xml"
    if extension == ".css":
        return "text/css"
    if extension in {".js", ".jsx", ".ts", ".tsx"}:
        return "text/javascript"
    return "text/plain"


def _office_media_type(extension: str | None) -> str:
    if extension == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if extension == ".pptx":
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if extension == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if extension == ".doc":
        return "application/msword"
    if extension == ".ppt":
        return "application/vnd.ms-powerpoint"
    if extension == ".xls":
        return "application/vnd.ms-excel"
    if extension == ".rtf":
        return "application/rtf"
    return "application/octet-stream"
