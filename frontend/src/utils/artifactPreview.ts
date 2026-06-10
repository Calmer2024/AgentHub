import type { Artifact } from "../types";

export interface ArtifactPreviewInfo {
  kind: string;
  label: string;
  shortLabel: string;
  extension: string | null;
  mediaType: string | null;
  rawUrl: string | null;
  downloadUrl: string | null;
  canInline: boolean;
  isBinary: boolean;
}

const imageExtensions = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"]);
const markdownExtensions = new Set([".md", ".markdown", ".mdx"]);
const presentationExtensions = new Set([".ppt", ".pptx", ".key"]);
const wordExtensions = new Set([".doc", ".docx", ".rtf"]);
const spreadsheetExtensions = new Set([".xls", ".xlsx", ".csv", ".tsv"]);

export function getArtifactPreviewInfo(artifact: Artifact): ArtifactPreviewInfo {
  const extension = normalizeExtension(artifact.fileExtension) ?? extensionFromPath(artifact.filePath ?? artifact.title);
  const rawKind = artifact.previewKind ?? inferPreviewKind(artifact, extension);
  const kind = normalizeKind(rawKind);
  const label = artifact.previewLabel ?? labelForKind(kind, artifact.type);
  return {
    kind,
    label,
    shortLabel: shortLabelForKind(kind, artifact.type),
    extension,
    mediaType: artifact.mediaType ?? mediaTypeForKind(kind, extension),
    rawUrl: artifact.rawUrl ?? null,
    downloadUrl: artifact.downloadUrl ?? artifact.rawUrl ?? null,
    canInline: artifact.canInlinePreview ?? canInlineKind(kind),
    isBinary: artifact.isBinary ?? isBinaryKind(kind),
  };
}

export function artifactDisplayTitle(artifact: Artifact): string {
  return artifact.title || artifact.filePath || "产物";
}

export function isMetadataOnlyContent(content: string): boolean {
  try {
    const parsed = JSON.parse(content) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return false;
    const data = parsed as Record<string, unknown>;
    return typeof data.path === "string" && typeof data.previewKind === "string";
  } catch {
    return false;
  }
}

function inferPreviewKind(artifact: Artifact, extension: string | null): string {
  if (artifact.type === "code_diff") return "diff";
  if (artifact.type === "file_tree") return "file_tree";
  if (artifact.type === "web_preview") return "html";
  if (extension && markdownExtensions.has(extension)) return "markdown";
  if (extension === ".pdf") return "pdf";
  if (extension && imageExtensions.has(extension)) return "image";
  if (extension && presentationExtensions.has(extension)) return "presentation";
  if (extension && wordExtensions.has(extension)) return "word";
  if (extension && spreadsheetExtensions.has(extension)) return "spreadsheet";
  if (/^#{1,6}\s+\S+/m.test(artifact.content)) return "markdown";
  return "text";
}

function normalizeKind(kind: string): string {
  if (kind === "md") return "markdown";
  if (kind === "docx" || kind === "doc") return "word";
  if (kind === "ppt" || kind === "pptx") return "presentation";
  if (kind === "xls" || kind === "xlsx") return "spreadsheet";
  return kind;
}

function labelForKind(kind: string, type: Artifact["type"]): string {
  if (kind === "diff") return "代码变更";
  if (kind === "file_tree") return "文件变更";
  if (kind === "html") return type === "web_preview" ? "网页预览" : "HTML";
  if (kind === "markdown") return "Markdown 文档";
  if (kind === "pdf") return "PDF 文档";
  if (kind === "image") return "图片预览";
  if (kind === "presentation") return "演示文稿";
  if (kind === "word") return "Word 文档";
  if (kind === "spreadsheet") return "表格文件";
  return "文档";
}

function shortLabelForKind(kind: string, type: Artifact["type"]): string {
  if (kind === "diff") return "Diff";
  if (kind === "file_tree") return "文件";
  if (kind === "html") return type === "web_preview" ? "网页" : "HTML";
  if (kind === "markdown") return "MD";
  if (kind === "pdf") return "PDF";
  if (kind === "image") return "图片";
  if (kind === "presentation") return "PPT";
  if (kind === "word") return "DOCX";
  if (kind === "spreadsheet") return "表格";
  return "文档";
}

function canInlineKind(kind: string): boolean {
  return ["diff", "file_tree", "html", "markdown", "pdf", "image", "text", "spreadsheet"].includes(kind);
}

function isBinaryKind(kind: string): boolean {
  return ["pdf", "image", "presentation", "word"].includes(kind);
}

function mediaTypeForKind(kind: string, extension: string | null): string | null {
  if (kind === "html") return "text/html";
  if (kind === "markdown") return "text/markdown";
  if (kind === "pdf") return "application/pdf";
  if (kind === "image") return extension === ".svg" ? "image/svg+xml" : "image/*";
  if (kind === "diff") return "text/x-diff";
  if (kind === "file_tree") return "application/json";
  if (kind === "spreadsheet" && extension === ".csv") return "text/csv";
  return null;
}

function extensionFromPath(path: string | null | undefined): string | null {
  if (!path) return null;
  const match = /\.([A-Za-z0-9]+)$/.exec(path.trim());
  return match ? `.${match[1].toLowerCase()}` : null;
}

function normalizeExtension(extension: string | null | undefined): string | null {
  if (!extension) return null;
  const clean = extension.trim().toLowerCase();
  return clean.startsWith(".") ? clean : `.${clean}`;
}
