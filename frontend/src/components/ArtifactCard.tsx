import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { Artifact, ArtifactDiff, ArtifactVersion, BuildLogChunk, BuildRun } from "../types";
import {
  createProjectBuildPreview,
  createProjectPreview,
  fetchArtifactDiff,
  fetchArtifactVersions,
  fetchProjectBuildLogs,
  fetchProjectBuilds,
  projectBuildExportUrl,
  projectSourceExportUrl,
  startProjectBuild,
} from "../api/client";
import {
  Download,
  Eye,
  ExternalLink,
  FilePenLine,
  FileCode2,
  FileText,
  Files,
  GitCompareArrows,
  Globe2,
  Hammer,
  History,
  Loader2,
  Maximize2,
  PackageOpen,
  ScrollText,
  X,
} from "lucide-react";
import { DiffViewer } from "./DiffViewer";
import { FileEditorModal } from "./FileEditorModal";
import { ArtifactVersionManager } from "./ArtifactVersionManager";

interface Props {
  artifact: Artifact;
  onChanged?: () => void;
}

interface FileTreeChange {
  path: string;
  change: string;
  diffPreview?: string;
}

function artifactLabel(artifact: Artifact) {
  if (artifact.type === "code_diff") return "代码变更";
  if (artifact.type === "web_preview") return "网页预览";
  if (artifact.type === "file_tree") return "文件变更";
  return "文档";
}

function artifactIcon(artifact: Artifact, className = "agenthub-muted") {
  const props = { size: 15, className: `shrink-0 ${className}`, "aria-hidden": true };
  if (artifact.type === "code_diff") return <FileCode2 {...props} />;
  if (artifact.type === "web_preview") return <Globe2 {...props} />;
  if (artifact.type === "file_tree") return <Files {...props} />;
  return <FileText {...props} />;
}

function statusText(status: Artifact["status"]) {
  if (status === "rendering") return "生成中";
  if (status === "error") return "异常";
  return "就绪";
}

function statusClass(status: Artifact["status"]) {
  if (status === "rendering") return "agenthub-status-warning";
  if (status === "error") return "agenthub-status-error";
  return "agenthub-status-success";
}

function buildStatusText(status: BuildRun["status"]) {
  if (status === "queued") return "排队中";
  if (status === "running") return "构建中";
  if (status === "succeeded") return "构建成功";
  if (status === "failed") return "构建失败";
  if (status === "cancelled") return "已取消";
  return String(status || "未知");
}

function buildStatusClass(status: BuildRun["status"]) {
  if (status === "succeeded") return "agenthub-status-success";
  if (status === "failed" || status === "cancelled") return "agenthub-status-error";
  return "agenthub-status-warning";
}

function normalizeDiffContent(content: string) {
  return {
    fromVersion: 0,
    toVersion: 1,
    diff: content,
    oldContent: "",
    newContent: "",
  };
}

function changeLabel(change: string) {
  if (change === "created" || change === "added") return "A";
  if (change === "deleted" || change === "removed") return "D";
  if (change === "renamed") return "R";
  return "M";
}

function changeClass(change: string) {
  if (change === "created" || change === "added") return "agenthub-status-success";
  if (change === "deleted" || change === "removed") return "agenthub-status-error";
  if (change === "renamed") return "agenthub-status-info";
  return "agenthub-status-warning";
}

function parseFileTreeChanges(content: string): FileTreeChange[] {
  try {
    const parsed = JSON.parse(content) as unknown;
    if (!parsed || typeof parsed !== "object") return [];
    const changes = (parsed as { changes?: unknown }).changes;
    if (!Array.isArray(changes)) return [];
    return changes.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const data = item as Record<string, unknown>;
      if (typeof data.path !== "string") return [];
      return [{
        path: data.path,
        change: typeof data.change === "string" ? data.change : "modified",
        diffPreview: typeof data.diffPreview === "string" ? data.diffPreview : undefined,
      }];
    });
  } catch {
    return [];
  }
}

export function ArtifactCard({ artifact, onChanged }: Props) {
  const [fullscreen, setFullscreen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingFile, setEditingFile] = useState<FileTreeChange | null>(null);
  const [versionManagerOpen, setVersionManagerOpen] = useState(false);
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [diff, setDiff] = useState<ArtifactDiff | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [builds, setBuilds] = useState<BuildRun[]>([]);
  const [buildsLoading, setBuildsLoading] = useState(false);
  const [buildRunning, setBuildRunning] = useState(false);
  const [buildMessage, setBuildMessage] = useState<string | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [buildLogs, setBuildLogs] = useState<BuildLogChunk[]>([]);
  const [buildLogsOpen, setBuildLogsOpen] = useState(false);
  const [buildLogsLoading, setBuildLogsLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchArtifactVersions(artifact.id)
      .then((items) => {
        if (!alive) return;
        setVersions(items);
      })
      .catch(() => {
        if (alive) setVersions([]);
      });
    return () => { alive = false; };
  }, [artifact.id, artifact.version]);

  const orderedVersions = useMemo(() => {
    return [...versions].sort((left, right) => left.version - right.version);
  }, [versions]);

  const latestVersion = orderedVersions[orderedVersions.length - 1] ?? null;
  const previousVersion = orderedVersions.length >= 2
    ? orderedVersions[orderedVersions.length - 2]
    : null;
  const displayVersion = latestVersion?.version ?? artifact.version;

  useEffect(() => {
    if (!previousVersion || !latestVersion || previousVersion.version === latestVersion.version) {
      setDiff(null);
      return;
    }
    let alive = true;
    fetchArtifactDiff(artifact.id, previousVersion.version, latestVersion.version)
      .then((result) => { if (alive) setDiff(result); })
      .catch(() => { if (alive) setDiff(null); });
    return () => { alive = false; };
  }, [artifact.id, latestVersion?.version, previousVersion?.version]);

  useEffect(() => {
    if (!fullscreen || typeof document === "undefined") return;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullscreen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [fullscreen]);

  useEffect(() => {
    if (artifact.type !== "web_preview" || !artifact.projectId) {
      setPreviewUrl(null);
      setPreviewError(null);
      setPreviewLoading(false);
      return;
    }
    let alive = true;
    setPreviewLoading(true);
    setPreviewError(null);
    createProjectPreview(artifact.projectId, artifact.filePath)
      .then((result) => {
        if (!alive) return;
        setPreviewUrl(result.previewUrl);
      })
      .catch((err) => {
        if (!alive) return;
        setPreviewUrl(null);
        setPreviewError(err instanceof Error ? err.message : "预览加载失败");
      })
      .finally(() => {
        if (alive) setPreviewLoading(false);
      });
    return () => { alive = false; };
  }, [artifact.filePath, artifact.projectId, artifact.type]);

  useEffect(() => {
    if (!artifact.projectId) {
      setBuilds([]);
      setBuildsLoading(false);
      return;
    }
    let alive = true;
    setBuildsLoading(true);
    fetchProjectBuilds(artifact.projectId)
      .then((result) => {
        if (!alive) return;
        setBuilds(Array.isArray(result.items) ? result.items : []);
      })
      .catch(() => {
        if (alive) setBuilds([]);
      })
      .finally(() => {
        if (alive) setBuildsLoading(false);
      });
    return () => { alive = false; };
  }, [artifact.projectId]);

  const displayedContent = useMemo(() => {
    return latestVersion?.content ?? artifact.content;
  }, [artifact.content, latestVersion?.content]);

  const iframeProps = previewUrl
    ? { src: previewUrl }
    : { srcDoc: displayedContent };

  const fileTreeChanges = useMemo(() => parseFileTreeChanges(displayedContent), [displayedContent]);
  const contentDiff = useMemo(() => normalizeDiffContent(displayedContent), [displayedContent]);
  const inspectorDiff = diff;
  const showInspector = artifact.type === "code_diff" || Boolean(inspectorDiff);
  const canEditArtifact = artifact.type !== "file_tree" && (
    artifact.type !== "code_diff" || Boolean(artifact.projectId && artifact.filePath)
  );
  const canManageVersions = true;
  const latestBuild = builds[0] ?? null;
  const latestSucceededBuild = builds.find((build) => build.status === "succeeded") ?? null;
  const projectActionsEnabled = Boolean(artifact.projectId);

  const openExternalPreview = () => {
    if (previewUrl) window.open(previewUrl, "_blank", "noopener,noreferrer");
  };

  const refreshBuilds = async () => {
    if (!artifact.projectId) return [];
    const result = await fetchProjectBuilds(artifact.projectId);
    const items = Array.isArray(result.items) ? result.items : [];
    setBuilds(items);
    return items;
  };

  const handleStartBuild = async () => {
    if (!artifact.projectId) {
      setBuildError("当前产物未绑定 Project，无法构建。");
      return;
    }
    setBuildRunning(true);
    setBuildError(null);
    setBuildMessage("正在执行本机构建...");
    try {
      const result = await startProjectBuild(artifact.projectId);
      const items = await refreshBuilds();
      const build = items.find((item) => item.id === result.buildId) ?? items[0] ?? null;
      const status = build?.status ?? result.status;
      setBuildMessage(buildStatusText(status));
      if (status === "succeeded" && artifact.type === "web_preview") {
        const preview = await createProjectBuildPreview(artifact.projectId, {
          source: "build",
          buildId: result.buildId,
        });
        setPreviewUrl(preview.url);
        setPreviewError(null);
      }
    } catch (error) {
      setBuildError(error instanceof Error ? error.message : "构建失败");
      setBuildMessage(null);
    } finally {
      setBuildRunning(false);
    }
  };

  const handleOpenLogs = async () => {
    if (!artifact.projectId || !latestBuild) return;
    setBuildLogsOpen(true);
    setBuildLogsLoading(true);
    setBuildError(null);
    try {
      const result = await fetchProjectBuildLogs(artifact.projectId, latestBuild.id);
      setBuildLogs(Array.isArray(result.chunks) ? result.chunks : []);
    } catch (error) {
      setBuildError(error instanceof Error ? error.message : "日志加载失败");
      setBuildLogs([]);
    } finally {
      setBuildLogsLoading(false);
    }
  };

  const openSourceExport = () => {
    if (!artifact.projectId) return;
    window.open(projectSourceExportUrl(artifact.projectId), "_blank", "noopener,noreferrer");
  };

  const openBuildExport = () => {
    if (!artifact.projectId || !latestSucceededBuild) return;
    window.open(
      projectBuildExportUrl(artifact.projectId, latestSucceededBuild.id),
      "_blank",
      "noopener,noreferrer",
    );
  };

  const openBuildPreview = async () => {
    if (!artifact.projectId || !latestSucceededBuild) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const preview = await createProjectBuildPreview(artifact.projectId, {
        source: "build",
        buildId: latestSucceededBuild.id,
      });
      setPreviewUrl(preview.url);
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "构建预览加载失败");
    } finally {
      setPreviewLoading(false);
    }
  };

  const renderBuildActions = () => (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={handleStartBuild}
        disabled={!projectActionsEnabled || buildRunning}
        className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
        aria-label="执行项目构建"
        title="执行项目构建"
      >
        {buildRunning ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Hammer size={14} aria-hidden="true" />}
      </button>
      <button
        type="button"
        onClick={handleOpenLogs}
        disabled={!projectActionsEnabled || !latestBuild}
        className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
        aria-label="查看构建日志"
        title="查看构建日志"
      >
        <ScrollText size={14} aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={openSourceExport}
        disabled={!projectActionsEnabled}
        className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
        aria-label="下载源码包"
        title="下载源码包"
      >
        <Download size={14} aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={openBuildExport}
        disabled={!projectActionsEnabled || !latestSucceededBuild}
        className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
        aria-label="下载构建产物"
        title="下载构建产物"
      >
        <PackageOpen size={14} aria-hidden="true" />
      </button>
      {artifact.type === "web_preview" && (
        <button
          type="button"
          onClick={openBuildPreview}
          disabled={!projectActionsEnabled || !latestSucceededBuild}
          className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
          aria-label="打开构建预览"
          title="打开构建预览"
        >
          <Eye size={14} aria-hidden="true" />
        </button>
      )}
    </div>
  );

  const fullscreenDialog = fullscreen && typeof document !== "undefined"
    ? createPortal(
      <div
        className="agenthub-backdrop fixed inset-0 z-[1000] flex items-center justify-center p-3 md:p-6"
        role="dialog"
        aria-modal="true"
        aria-label={`${artifactLabel(artifact)}：${artifact.title || artifact.filePath || "产物预览"}`}
        onClick={() => setFullscreen(false)}
      >
        <div
          className="agenthub-modal flex max-h-[92dvh] w-full max-w-6xl flex-col overflow-hidden rounded-lg border"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="agenthub-header flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
            <div className="min-w-0">
              <div className="agenthub-muted flex items-center gap-2 text-[11px]">
                {artifactIcon(artifact)}
                <span>{artifactLabel(artifact)}</span>
                <span className={`rounded-md px-1.5 py-0.5 ${statusClass(artifact.status)}`}>
                  {statusText(artifact.status)}
                </span>
                <span className="agenthub-faint font-mono">v{displayVersion}</span>
              </div>
              <h3 className="agenthub-strong mt-1 truncate text-base font-semibold">{artifact.title || "产物预览"}</h3>
              {artifact.filePath && <p className="agenthub-faint mt-0.5 truncate font-mono text-xs">{artifact.filePath}</p>}
            </div>
            <div className="flex items-center gap-2">
              {projectActionsEnabled && renderBuildActions()}
              {previewUrl && artifact.type === "web_preview" && (
                <button
                  type="button"
                  onClick={openExternalPreview}
                  className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
                  aria-label="在浏览器中打开"
                  title="在浏览器中打开"
                >
                  <ExternalLink size={14} />
                </button>
              )}
              {canManageVersions && (
                <button
                  type="button"
                  onClick={() => setVersionManagerOpen(true)}
                  className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
                  aria-label="打开版本管理"
                  title="版本管理"
                >
                  <History size={14} />
                </button>
              )}
              {canEditArtifact && (
                <button
                  type="button"
                  onClick={() => setEditorOpen(true)}
                  className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
                  aria-label="编辑文件"
                  title="编辑文件"
                >
                  <FilePenLine size={14} />
                </button>
              )}
              <button
                type="button"
                onClick={() => setFullscreen(false)}
                className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
                aria-label="关闭产物预览"
                title="关闭"
              >
                <X size={15} />
              </button>
            </div>
          </div>

          <div className={`grid min-h-0 flex-1 gap-0 overflow-hidden ${
            showInspector ? "lg:grid-cols-[minmax(0,1fr)_400px]" : ""
          }`}>
            <div className="min-h-0 overflow-y-auto p-4">
              <ArtifactFullPreview
                artifact={artifact}
                content={displayedContent}
                contentDiff={contentDiff}
                fileTreeChanges={fileTreeChanges}
                iframeProps={iframeProps}
                previewLoading={previewLoading}
                previewError={previewError}
                previewUrl={previewUrl}
                onEditFile={(change) => setEditingFile(change)}
              />
            </div>

            {showInspector && (
              <div className="agenthub-sidebar min-h-0 overflow-y-auto border-t p-3 lg:border-l lg:border-t-0">
                <div className="agenthub-strong mb-3 flex items-center gap-2 text-xs font-medium">
                  <GitCompareArrows size={14} aria-hidden="true" />
                  <span>最新版本与上一版本</span>
                </div>
                <DiffViewer diff={inspectorDiff} />
              </div>
            )}
          </div>
        </div>
      </div>,
      document.body,
    )
    : null;

  const buildLogsDialog = buildLogsOpen && typeof document !== "undefined"
    ? createPortal(
      <div
        className="agenthub-backdrop fixed inset-0 z-[1000] flex items-center justify-center p-3 md:p-6"
        role="dialog"
        aria-modal="true"
        aria-label="构建日志"
        onClick={() => setBuildLogsOpen(false)}
      >
        <div
          className="agenthub-modal flex max-h-[82dvh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="agenthub-header flex items-center justify-between gap-3 border-b px-4 py-3">
            <div className="min-w-0">
              <div className="agenthub-muted flex items-center gap-2 text-[11px]">
                <ScrollText size={14} aria-hidden="true" />
                <span>构建日志</span>
                {latestBuild && (
                  <span className={`rounded-md px-1.5 py-0.5 ${buildStatusClass(latestBuild.status)}`}>
                    {buildStatusText(latestBuild.status)}
                  </span>
                )}
              </div>
              {latestBuild && <p className="agenthub-faint mt-1 truncate font-mono text-xs">{latestBuild.id}</p>}
            </div>
            <button
              type="button"
              onClick={() => setBuildLogsOpen(false)}
              className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
              aria-label="关闭构建日志"
              title="关闭"
            >
              <X size={15} aria-hidden="true" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-3">
            <pre className="agenthub-code-surface min-h-64 whitespace-pre-wrap rounded-lg border p-3 text-xs leading-5">
              {buildLogsLoading
                ? "正在加载日志..."
                : buildLogs.length > 0
                  ? buildLogs.map((chunk) => `[${chunk.stream}] ${chunk.text}`).join("")
                  : "暂无日志"}
            </pre>
          </div>
        </div>
      </div>,
      document.body,
    )
    : null;

  return (
    <>
      <article className="agenthub-card group/card relative min-w-0 max-w-full overflow-visible rounded-2xl border transition hover:border-[color:var(--ah-border-hover)]">
        <div className="flex min-w-0 items-start justify-between gap-3 border-b px-3 py-2" style={{ borderColor: "var(--ah-border)" }}>
          <button
            type="button"
            onClick={() => setFullscreen(true)}
            aria-label={`打开产物预览：${artifact.title || artifact.filePath || "产物"}`}
            className="min-w-0 flex-1 text-left transition active:translate-y-px"
          >
            <div className="agenthub-muted flex items-center gap-2 text-[11px]">
              {artifactIcon(artifact)}
              <span>{artifactLabel(artifact)}</span>
              <span className={`rounded-md px-1.5 py-0.5 ${statusClass(artifact.status)}`}>
                {statusText(artifact.status)}
              </span>
              <span className="font-mono">v{artifact.version}</span>
            </div>
            <div className="agenthub-strong mt-1 truncate text-sm font-medium">
              {artifact.title || artifact.filePath || "产物"}
            </div>
            {artifact.filePath && (
              <div className="agenthub-faint mt-0.5 truncate font-mono text-[11px]">{artifact.filePath}</div>
            )}
          </button>
          <div className="flex shrink-0 items-center gap-1">
            {projectActionsEnabled && renderBuildActions()}
            {canManageVersions && (
              <button
                type="button"
                onClick={() => setVersionManagerOpen(true)}
                className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
                aria-label="版本管理"
                title="版本管理"
              >
                <History size={14} aria-hidden="true" />
              </button>
            )}
            {canEditArtifact && (
              <button
                type="button"
                onClick={() => setEditorOpen(true)}
                className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
                aria-label="编辑文件"
                title="编辑文件"
              >
                <FilePenLine size={14} aria-hidden="true" />
              </button>
            )}
            <button
              type="button"
              onClick={() => setFullscreen(true)}
              className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
              aria-label="打开产物预览"
              title="打开预览"
            >
              <Maximize2 size={14} aria-hidden="true" />
            </button>
          </div>
        </div>

        {projectActionsEnabled && (
          <div className="agenthub-muted flex min-h-8 items-center gap-2 border-b px-3 py-1.5 text-[11px]" style={{ borderColor: "var(--ah-border)" }}>
            {buildsLoading && <Loader2 size={12} className="animate-spin" aria-hidden="true" />}
            {buildError ? (
              <span className="agenthub-status-error rounded-md px-1.5 py-0.5">{buildError}</span>
            ) : buildMessage ? (
              <span className="agenthub-status-info rounded-md px-1.5 py-0.5">{buildMessage}</span>
            ) : latestBuild ? (
              <span className={`rounded-md px-1.5 py-0.5 ${buildStatusClass(latestBuild.status)}`}>
                {buildStatusText(latestBuild.status)}
              </span>
            ) : (
              <span className="agenthub-faint">暂无构建记录</span>
            )}
            {latestBuild?.artifactPath && (
              <span className="agenthub-faint truncate font-mono">{latestBuild.artifactPath}</span>
            )}
          </div>
        )}

        <div className="min-w-0 p-3">
          <ArtifactPreview
            artifact={artifact}
            content={displayedContent}
            contentDiff={contentDiff}
            fileTreeChanges={fileTreeChanges}
            iframeProps={iframeProps}
            previewLoading={previewLoading}
            previewError={previewError}
            onEditFile={(change) => setEditingFile(change)}
          />
        </div>
      </article>
      {fullscreenDialog}
      {buildLogsDialog}
      <FileEditorModal
        open={editorOpen}
        artifact={artifact}
        initialContent={displayedContent}
        onClose={() => setEditorOpen(false)}
        onSaved={onChanged}
      />
      <FileEditorModal
        open={Boolean(editingFile)}
        projectId={artifact.projectId}
        filePath={editingFile?.path ?? null}
        title={editingFile?.path ?? null}
        initialContent={null}
        onClose={() => setEditingFile(null)}
        onSaved={onChanged}
      />
      <ArtifactVersionManager
        artifact={artifact}
        open={versionManagerOpen}
        onClose={() => setVersionManagerOpen(false)}
        onChanged={onChanged}
      />
    </>
  );
}

function ArtifactPreview({
  artifact,
  content,
  contentDiff,
  fileTreeChanges,
  iframeProps,
  previewLoading,
  previewError,
  onEditFile,
}: {
  artifact: Artifact;
  content: string;
  contentDiff: ArtifactDiff;
  fileTreeChanges: FileTreeChange[];
  iframeProps: { src: string } | { srcDoc: string };
  previewLoading: boolean;
  previewError: string | null;
  onEditFile?: (change: FileTreeChange) => void;
}) {
  if (artifact.type === "code_diff") {
    return <DiffViewer diff={contentDiff} compact title={artifact.filePath ?? artifact.title ?? "差异"} />;
  }

  if (artifact.type === "file_tree") {
    return <FileTreePreview changes={fileTreeChanges} compact onEditFile={onEditFile} />;
  }

  if (artifact.type === "web_preview") {
    return (
      <div className="relative h-80 overflow-hidden rounded-2xl border bg-white md:h-96" style={{ borderColor: "var(--ah-border)" }}>
        {previewLoading && (
          <div className="agenthub-backdrop absolute inset-0 z-10 flex items-center justify-center text-xs">
            <Loader2 size={14} className="mr-2 animate-spin" />
            正在加载本机预览
          </div>
        )}
        {previewError && (
          <div className="agenthub-status-warning absolute left-2 top-2 z-10 rounded-full border px-2 py-1 text-[11px]">
            已回退到内容快照
          </div>
        )}
        <iframe {...iframeProps} sandbox="allow-scripts" className="h-full w-full border-0" title="preview" />
      </div>
    );
  }

  return (
    <pre className="agenthub-code-surface max-h-48 overflow-auto whitespace-pre-wrap rounded-2xl border p-3 text-xs">
      {content}
    </pre>
  );
}

function ArtifactFullPreview({
  artifact,
  content,
  contentDiff,
  fileTreeChanges,
  iframeProps,
  previewLoading,
  previewError,
  previewUrl,
  onEditFile,
}: {
  artifact: Artifact;
  content: string;
  contentDiff: ArtifactDiff;
  fileTreeChanges: FileTreeChange[];
  iframeProps: { src: string } | { srcDoc: string };
  previewLoading: boolean;
  previewError: string | null;
  previewUrl: string | null;
  onEditFile?: (change: FileTreeChange) => void;
}) {
  if (artifact.type === "web_preview") {
    return (
      <div className="flex h-[76vh] min-h-0 flex-col overflow-hidden rounded-2xl border bg-white" style={{ borderColor: "var(--ah-border)" }}>
        {(previewUrl || previewError || previewLoading) && (
          <div className="agenthub-code-header flex items-center justify-between gap-3 border-b px-3 py-2">
              <div className="min-w-0 truncate text-xs">
              {previewLoading
                ? "正在连接本机预览"
                : previewUrl
                  ? "本机工作区预览"
                  : "真实预览不可用，已显示内容快照"}
              {artifact.filePath && (
                <span className="ml-2 font-mono">{artifact.filePath}</span>
              )}
            </div>
          </div>
        )}
        <iframe
          {...iframeProps}
          sandbox="allow-scripts"
          className="min-h-0 flex-1 border-0 bg-white"
          title="网页预览"
        />
      </div>
    );
  }

  if (artifact.type === "file_tree") {
    return <FileTreePreview changes={fileTreeChanges} expanded onEditFile={onEditFile} />;
  }

  if (artifact.type === "code_diff") {
    return <DiffViewer diff={contentDiff} title={artifact.filePath ?? artifact.title ?? "差异"} />;
  }

  return (
    <pre className="agenthub-code-surface min-h-80 overflow-auto rounded-2xl border p-3 text-xs leading-5">
      <code>{content}</code>
    </pre>
  );
}

function FileTreePreview({
  changes,
  compact = false,
  expanded = false,
  onEditFile,
}: {
  changes: FileTreeChange[];
  compact?: boolean;
  expanded?: boolean;
  onEditFile?: (change: FileTreeChange) => void;
}) {
  if (changes.length === 0) {
    return (
      <div className="agenthub-code-surface rounded-2xl border px-3 py-2 text-xs">
        暂无文件变更详情
      </div>
    );
  }

  const visible = expanded ? changes : changes.slice(0, compact ? 4 : 8);
  const hiddenCount = changes.length - visible.length;

  return (
    <div className="space-y-1.5">
      {visible.map((change) => (
        <FileChangeRow
          key={`${change.change}:${change.path}`}
          change={change}
          expanded={expanded}
          onEditFile={onEditFile}
        />
      ))}
      {hiddenCount > 0 && (
        <div className="agenthub-code-surface rounded-2xl border px-3 py-2 text-xs">
          还有 {hiddenCount} 个文件，点击打开完整变更
        </div>
      )}
    </div>
  );
}

function FileChangeRow({
  change,
  expanded,
  onEditFile,
}: {
  change: FileTreeChange;
  expanded: boolean;
  onEditFile?: (change: FileTreeChange) => void;
}) {
  const hasDiff = Boolean(change.diffPreview?.trim());

  return (
    <div className="group/row relative">
      <div className="agenthub-code-surface flex min-h-9 items-center gap-2 rounded-xl border px-2.5 py-1.5 text-xs transition group-hover/row:border-[color:var(--ah-border-strong)]">
        <span className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded border font-mono text-[10px] ${changeClass(change.change)}`}>
          {changeLabel(change.change)}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono">{change.path}</span>
        {hasDiff && (
          <span className="agenthub-faint shrink-0 text-[11px]">{expanded ? "差异" : "悬停"}</span>
        )}
        {onEditFile && change.change !== "deleted" && change.change !== "removed" && (
          <button
            type="button"
            onClick={() => onEditFile(change)}
            className="agenthub-icon-button inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full"
            aria-label={`编辑文件 ${change.path}`}
            title="编辑文件"
          >
            <FilePenLine size={13} aria-hidden="true" />
          </button>
        )}
      </div>
      {hasDiff && !expanded && (
        <div className="pointer-events-none absolute left-0 top-[calc(100%+6px)] z-20 hidden w-[min(620px,calc(100vw-3rem))] group-hover/row:block">
          <DiffViewer
            diff={normalizeDiffContent(change.diffPreview ?? "")}
            compact
            title={change.path}
          />
        </div>
      )}
      {hasDiff && expanded && (
        <div className="mt-1.5">
          <DiffViewer
            diff={normalizeDiffContent(change.diffPreview ?? "")}
            title={change.path}
          />
        </div>
      )}
    </div>
  );
}
