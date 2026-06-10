import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  Artifact,
  ArtifactDiff,
  ArtifactVersion,
  BuildLogChunk,
  BuildRun,
  Deployment,
  DeploymentLogChunk,
  PreviewSession,
} from "../types";
import {
  createArtifactPreview,
  createDeployment,
  createProjectBuildPreview,
  createProjectPreview,
  fetchArtifactDiff,
  fetchArtifactVersions,
  fetchDeploymentLogs,
  fetchProjectBuildLogs,
  fetchProjectBuilds,
  projectBuildExportUrl,
  projectSourceExportUrl,
  retryDeployment,
  startProjectBuild,
} from "../api/client";
import {
  Download,
  ExternalLink,
  FilePenLine,
  FileCode2,
  FileImage,
  FileText,
  Files,
  GitCompareArrows,
  Globe2,
  History,
  Loader2,
  Maximize2,
  Rocket,
  ScrollText,
  X,
} from "lucide-react";
import { DiffViewer } from "./DiffViewer";
import { FileEditorModal } from "./FileEditorModal";
import { ArtifactVersionManager } from "./ArtifactVersionManager";
import { useCapabilities } from "../app/ShellProvider";
import { LocalArtifactActions } from "../features/artifacts/LocalArtifactActions";
import { CloudArtifactActions } from "../features/artifacts/CloudArtifactActions";
import { artifactDisplayTitle, getArtifactPreviewInfo, isMetadataOnlyContent } from "../utils/artifactPreview";

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
  return getArtifactPreviewInfo(artifact).label;
}

function artifactIcon(artifact: Artifact, className = "agenthub-muted") {
  const props = { size: 15, className: `shrink-0 ${className}`, "aria-hidden": true };
  const preview = getArtifactPreviewInfo(artifact);
  if (preview.kind === "diff" || artifact.type === "code_diff") return <FileCode2 {...props} />;
  if (preview.kind === "html" || artifact.type === "web_preview") return <Globe2 {...props} />;
  if (preview.kind === "file_tree" || artifact.type === "file_tree") return <Files {...props} />;
  if (preview.kind === "image") return <FileImage {...props} />;
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

function deploymentStatusText(status: Deployment["status"]) {
  if (status === "queued") return "等待发布";
  if (status === "building") return "发布中";
  if (status === "published") return "已发布";
  if (status === "failed") return "发布失败";
  if (status === "rolled_back") return "已回滚";
  return String(status || "未知");
}

function deploymentStatusClass(status: Deployment["status"]) {
  if (status === "published") return "agenthub-status-success";
  if (status === "failed") return "agenthub-status-error";
  if (status === "rolled_back") return "agenthub-status-info";
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
  const { capabilities } = useCapabilities();
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
  const [cloudPreview, setCloudPreview] = useState<PreviewSession | null>(null);
  const [deployment, setDeployment] = useState<Deployment | null>(null);
  const [deploymentLogs, setDeploymentLogs] = useState<DeploymentLogChunk[]>([]);
  const [deploymentLogsOpen, setDeploymentLogsOpen] = useState(false);
  const [deploymentLogsLoading, setDeploymentLogsLoading] = useState(false);
  const [deliveryRunning, setDeliveryRunning] = useState(false);
  const [deliveryMessage, setDeliveryMessage] = useState<string | null>(null);
  const [deliveryError, setDeliveryError] = useState<string | null>(null);
  const canUseLocalPreview = capabilities.features.localPreview;
  const canUseLocalBuildExport = capabilities.features.localBuildExport;
  const canUseCloudPreview = capabilities.features.cloudPreview;
  const canUseDeployment = capabilities.features.deployment;

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
    if (!canUseLocalPreview || artifact.type !== "web_preview" || !artifact.projectId) {
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
  }, [artifact.filePath, artifact.projectId, artifact.type, canUseLocalPreview]);

  useEffect(() => {
    if (!canUseLocalBuildExport || !artifact.projectId) {
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
  }, [artifact.projectId, canUseLocalBuildExport]);

  const displayedContent = useMemo(() => {
    return latestVersion?.content ?? artifact.content;
  }, [artifact.content, latestVersion?.content]);

  const previewInfo = useMemo(() => getArtifactPreviewInfo(artifact), [artifact]);
  const artifactFileUrl = previewUrl ?? previewInfo.rawUrl;
  const iframeProps = artifactFileUrl && previewInfo.kind === "html"
    ? { src: artifactFileUrl }
    : { srcDoc: displayedContent };

  const fileTreeChanges = useMemo(() => parseFileTreeChanges(displayedContent), [displayedContent]);
  const contentDiff = useMemo(() => normalizeDiffContent(displayedContent), [displayedContent]);
  const inspectorDiff = diff;
  const showInspector = artifact.type === "code_diff" || Boolean(inspectorDiff);
  const canEditArtifact = !previewInfo.isBinary && artifact.type !== "file_tree" && (
    artifact.type !== "code_diff" || Boolean(artifact.projectId && artifact.filePath)
  );
  const canManageVersions = true;
  const latestBuild = builds[0] ?? null;
  const latestSucceededBuild = builds.find((build) => build.status === "succeeded") ?? null;
  const projectActionsEnabled = Boolean(artifact.projectId);
  const showLocalActions = projectActionsEnabled && (canUseLocalPreview || canUseLocalBuildExport);
  const showCloudActions = projectActionsEnabled && (canUseCloudPreview || canUseDeployment);
  const canEditInShell = capabilities.surface !== "mobile";
  const previewLabel = showCloudActions && !showLocalActions ? "云端预览" : "工作区预览";

  const openExternalPreview = () => {
    const url = artifactFileUrl ?? previewInfo.downloadUrl;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
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

  const handleCloudPreview = async () => {
    if (!artifact.projectId) {
      setDeliveryError("当前产物未绑定 Project，无法创建云端预览。");
      return;
    }
    setDeliveryRunning(true);
    setDeliveryError(null);
    setDeliveryMessage("正在创建云端预览...");
    try {
      const preview = await createArtifactPreview(artifact.id, {
        source: "static",
        artifactVersionId: latestVersion?.id ?? artifact.id,
        ttlSeconds: 3600,
        visibility: "team",
      });
      setCloudPreview(preview);
      setPreviewUrl(preview.url);
      setPreviewError(null);
      setDeliveryMessage("云端预览已就绪");
    } catch (error) {
      setDeliveryError(error instanceof Error ? error.message : "云端预览创建失败");
      setDeliveryMessage(null);
    } finally {
      setDeliveryRunning(false);
    }
  };

  const handleCreateDeployment = async () => {
    if (!artifact.projectId) {
      setDeliveryError("当前产物未绑定 Project，无法发布。");
      return;
    }
    setDeliveryRunning(true);
    setDeliveryError(null);
    setDeliveryMessage("正在发布...");
    try {
      const result = await createDeployment({
        artifactId: artifact.id,
        artifactVersionId: latestVersion?.id ?? artifact.id,
        target: "static_hosting",
        visibility: "team",
      });
      setDeployment(result);
      setDeliveryMessage(deploymentStatusText(result.status));
      if (result.url) {
        setPreviewUrl(result.url);
        setPreviewError(null);
      }
    } catch (error) {
      setDeliveryError(error instanceof Error ? error.message : "发布失败");
      setDeliveryMessage(null);
    } finally {
      setDeliveryRunning(false);
    }
  };

  const handleRetryDeployment = async () => {
    if (!deployment) return;
    setDeliveryRunning(true);
    setDeliveryError(null);
    setDeliveryMessage("正在重试发布...");
    try {
      const result = await retryDeployment(deployment.id, deployment.stage);
      setDeployment(result);
      setDeliveryMessage(deploymentStatusText(result.status));
      if (result.url) {
        setPreviewUrl(result.url);
        setPreviewError(null);
      }
    } catch (error) {
      setDeliveryError(error instanceof Error ? error.message : "重试发布失败");
      setDeliveryMessage(null);
    } finally {
      setDeliveryRunning(false);
    }
  };

  const handleOpenDeploymentLogs = async () => {
    if (!deployment) return;
    setDeploymentLogsOpen(true);
    setDeploymentLogsLoading(true);
    setDeliveryError(null);
    try {
      const result = await fetchDeploymentLogs(deployment.id);
      setDeploymentLogs(Array.isArray(result.chunks) ? result.chunks : []);
    } catch (error) {
      setDeliveryError(error instanceof Error ? error.message : "发布日志加载失败");
      setDeploymentLogs([]);
    } finally {
      setDeploymentLogsLoading(false);
    }
  };

  const openDeploymentUrl = () => {
    const url = deployment?.url ?? cloudPreview?.url ?? null;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  };

  const renderBuildActions = () => (
    <LocalArtifactActions
      canBuildExport={canUseLocalBuildExport}
      canPreview={canUseLocalPreview && artifact.type === "web_preview"}
      buildRunning={buildRunning}
      hasLatestBuild={Boolean(latestBuild)}
      hasSucceededBuild={Boolean(latestSucceededBuild)}
      onStartBuild={handleStartBuild}
      onOpenLogs={handleOpenLogs}
      onOpenSourceExport={openSourceExport}
      onOpenBuildExport={openBuildExport}
      onOpenBuildPreview={openBuildPreview}
    />
  );

  const renderDeliveryActions = () => (
    <CloudArtifactActions
      canPreview={canUseCloudPreview}
      canDeploy={canUseDeployment}
      deliveryRunning={deliveryRunning}
      hasDeployment={Boolean(deployment)}
      deploymentFailed={deployment?.status === "failed"}
      hasOpenableUrl={Boolean(deployment?.url || cloudPreview?.url)}
      onCreatePreview={handleCloudPreview}
      onCreateDeployment={handleCreateDeployment}
      onOpenDeploymentLogs={handleOpenDeploymentLogs}
      onRetryDeployment={handleRetryDeployment}
      onOpenUrl={openDeploymentUrl}
    />
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
          className="agenthub-modal agenthub-modal-pop flex max-h-[92dvh] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border"
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
              {showLocalActions && renderBuildActions()}
              {showCloudActions && renderDeliveryActions()}
              {artifactFileUrl && (
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
              {canEditInShell && canEditArtifact && (
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
                previewUrl={artifactFileUrl}
                previewLabel={previewLabel}
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
          className="agenthub-modal agenthub-modal-pop flex max-h-[82dvh] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border"
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

  const deploymentLogsDialog = deploymentLogsOpen && typeof document !== "undefined"
    ? createPortal(
      <div
        className="agenthub-backdrop fixed inset-0 z-[1000] flex items-center justify-center p-3 md:p-6"
        role="dialog"
        aria-modal="true"
        aria-label="发布日志"
        onClick={() => setDeploymentLogsOpen(false)}
      >
        <div
          className="agenthub-modal agenthub-modal-pop flex max-h-[82dvh] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="agenthub-header flex items-center justify-between gap-3 border-b px-4 py-3">
            <div className="min-w-0">
              <div className="agenthub-muted flex items-center gap-2 text-[11px]">
                <Rocket size={14} aria-hidden="true" />
                <span>发布日志</span>
                {deployment && (
                  <span className={`rounded-md px-1.5 py-0.5 ${deploymentStatusClass(deployment.status)}`}>
                    {deploymentStatusText(deployment.status)}
                  </span>
                )}
              </div>
              {deployment && <p className="agenthub-faint mt-1 truncate font-mono text-xs">{deployment.id}</p>}
            </div>
            <button
              type="button"
              onClick={() => setDeploymentLogsOpen(false)}
              className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
              aria-label="关闭发布日志"
              title="关闭"
            >
              <X size={15} aria-hidden="true" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-3">
            <pre className="agenthub-code-surface min-h-64 whitespace-pre-wrap rounded-lg border p-3 text-xs leading-5">
              {deploymentLogsLoading
                ? "正在加载日志..."
                : deploymentLogs.length > 0
                  ? deploymentLogs.map((chunk) => `[${chunk.stream}] ${chunk.text}`).join("")
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
            {showLocalActions && renderBuildActions()}
            {showCloudActions && renderDeliveryActions()}
            {previewInfo.downloadUrl && previewInfo.downloadUrl !== artifactFileUrl && (
              <button
                type="button"
                onClick={() => window.open(previewInfo.downloadUrl ?? "", "_blank", "noopener,noreferrer")}
                className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
                aria-label="下载原文件"
                title="下载原文件"
              >
                <Download size={14} />
              </button>
            )}
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
            {canEditInShell && canEditArtifact && (
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

        {(showLocalActions || showCloudActions) && (
          <div className="agenthub-muted flex min-h-8 flex-wrap items-center gap-2 border-b px-3 py-1.5 text-[11px]" style={{ borderColor: "var(--ah-border)" }}>
            {showLocalActions && buildsLoading && <Loader2 size={12} className="animate-spin" aria-hidden="true" />}
            {showLocalActions && buildError ? (
              <span className="agenthub-status-error rounded-md px-1.5 py-0.5">{buildError}</span>
            ) : showLocalActions && buildMessage ? (
              <span className="agenthub-status-info rounded-md px-1.5 py-0.5">{buildMessage}</span>
            ) : showLocalActions && latestBuild ? (
              <span className={`rounded-md px-1.5 py-0.5 ${buildStatusClass(latestBuild.status)}`}>
                {buildStatusText(latestBuild.status)}
              </span>
            ) : showLocalActions ? (
              <span className="agenthub-faint">暂无构建记录</span>
            ) : null}
            {showLocalActions && latestBuild?.artifactPath && (
              <span className="agenthub-faint truncate font-mono">{latestBuild.artifactPath}</span>
            )}
            {showCloudActions && deliveryError ? (
              <span className="agenthub-status-error rounded-md px-1.5 py-0.5">{deliveryError}</span>
            ) : showCloudActions && deliveryMessage ? (
              <span className="agenthub-status-info rounded-md px-1.5 py-0.5">{deliveryMessage}</span>
            ) : showCloudActions && deployment ? (
              <span className={`rounded-md px-1.5 py-0.5 ${deploymentStatusClass(deployment.status)}`}>
                {deploymentStatusText(deployment.status)} · {deployment.stage}
              </span>
            ) : showCloudActions && cloudPreview ? (
              <span className="agenthub-status-success rounded-md px-1.5 py-0.5">云端预览就绪</span>
            ) : null}
            {showCloudActions && deployment?.url && <span className="agenthub-faint max-w-72 truncate font-mono">{deployment.url}</span>}
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
            previewUrl={artifactFileUrl}
            previewLabel={previewLabel}
            onEditFile={(change) => setEditingFile(change)}
          />
        </div>
      </article>
      {fullscreenDialog}
      {buildLogsDialog}
      {deploymentLogsDialog}
      <FileEditorModal
        open={canEditInShell && editorOpen}
        artifact={artifact}
        initialContent={displayedContent}
        onClose={() => setEditorOpen(false)}
        onSaved={onChanged}
      />
      <FileEditorModal
        open={canEditInShell && Boolean(editingFile)}
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
  previewUrl,
  previewLabel,
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
  previewLabel: string;
  onEditFile?: (change: FileTreeChange) => void;
}) {
  if (artifact.type === "code_diff") {
    return <DiffViewer diff={contentDiff} compact title={artifact.filePath ?? artifact.title ?? "差异"} />;
  }

  if (artifact.type === "file_tree") {
    return <FileTreePreview changes={fileTreeChanges} compact onEditFile={onEditFile} />;
  }

  const preview = getArtifactPreviewInfo(artifact);

  if (preview.kind === "html") {
    return (
      <div className="relative h-80 overflow-hidden rounded-2xl border bg-white md:h-96" style={{ borderColor: "var(--ah-border)" }}>
        {previewLoading && (
          <div className="agenthub-backdrop absolute inset-0 z-10 flex items-center justify-center text-xs">
            <Loader2 size={14} className="mr-2 animate-spin" />
            正在加载{previewLabel}
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

  if (preview.kind === "image") {
    return <ImageArtifactPreview artifact={artifact} previewUrl={previewUrl} compact />;
  }

  if (preview.kind === "pdf") {
    return <PdfArtifactPreview artifact={artifact} previewUrl={previewUrl} compact />;
  }

  if (preview.kind === "markdown") {
    return <MarkdownArtifactPreview content={content} compact />;
  }

  if (["presentation", "word", "spreadsheet"].includes(preview.kind)) {
    return <DocumentFilePreview artifact={artifact} content={content} previewUrl={previewUrl} compact />;
  }

  return (
    <pre className="agenthub-code-surface max-h-48 overflow-auto whitespace-pre-wrap rounded-2xl border p-3 text-xs">
      {isMetadataOnlyContent(content) ? `${preview.label} · ${artifact.filePath ?? artifact.title}` : content}
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
  previewLabel,
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
  previewLabel: string;
  onEditFile?: (change: FileTreeChange) => void;
}) {
  const preview = getArtifactPreviewInfo(artifact);

  if (preview.kind === "html") {
    return (
      <div className="flex h-[76vh] min-h-0 flex-col overflow-hidden rounded-2xl border bg-white" style={{ borderColor: "var(--ah-border)" }}>
        {(previewUrl || previewError || previewLoading) && (
          <div className="agenthub-code-header flex items-center justify-between gap-3 border-b px-3 py-2">
              <div className="min-w-0 truncate text-xs">
              {previewLoading
                ? `正在连接${previewLabel}`
                : previewUrl
                  ? previewLabel
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

  if (preview.kind === "image") {
    return <ImageArtifactPreview artifact={artifact} previewUrl={previewUrl} />;
  }

  if (preview.kind === "pdf") {
    return <PdfArtifactPreview artifact={artifact} previewUrl={previewUrl} />;
  }

  if (preview.kind === "markdown") {
    return <MarkdownArtifactPreview content={content} />;
  }

  if (["presentation", "word", "spreadsheet"].includes(preview.kind)) {
    return <DocumentFilePreview artifact={artifact} content={content} previewUrl={previewUrl} />;
  }

  if (artifact.type === "file_tree") {
    return <FileTreePreview changes={fileTreeChanges} expanded onEditFile={onEditFile} />;
  }

  if (artifact.type === "code_diff") {
    return <DiffViewer diff={contentDiff} title={artifact.filePath ?? artifact.title ?? "差异"} />;
  }

  return (
    <pre className="agenthub-code-surface min-h-80 overflow-auto rounded-2xl border p-3 text-xs leading-5">
      <code>{isMetadataOnlyContent(content) ? `${preview.label} · ${artifact.filePath ?? artifact.title}` : content}</code>
    </pre>
  );
}

function MarkdownArtifactPreview({ content, compact = false }: { content: string; compact?: boolean }) {
  return (
    <div
      className={`agent-markdown agenthub-code-surface overflow-auto rounded-2xl border p-4 text-sm ${
        compact ? "max-h-56" : "min-h-80"
      }`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || "暂无 Markdown 内容"}</ReactMarkdown>
    </div>
  );
}

function ImageArtifactPreview({
  artifact,
  previewUrl,
  compact = false,
}: {
  artifact: Artifact;
  previewUrl: string | null;
  compact?: boolean;
}) {
  if (!previewUrl) {
    return <DocumentFilePreview artifact={artifact} content={artifact.content} previewUrl={previewUrl} compact={compact} />;
  }
  return (
    <div className={`agenthub-code-surface flex items-center justify-center overflow-hidden rounded-2xl border bg-white ${compact ? "h-56" : "min-h-[70vh]"}`}>
      <img
        src={previewUrl}
        alt={artifactDisplayTitle(artifact)}
        className="max-h-full max-w-full object-contain"
      />
    </div>
  );
}

function PdfArtifactPreview({
  artifact,
  previewUrl,
  compact = false,
}: {
  artifact: Artifact;
  previewUrl: string | null;
  compact?: boolean;
}) {
  if (!previewUrl) {
    return <DocumentFilePreview artifact={artifact} content={artifact.content} previewUrl={previewUrl} compact={compact} />;
  }
  if (compact) {
    return (
      <div className="agenthub-code-surface rounded-2xl border p-3 text-xs">
        <div className="agenthub-strong flex items-center gap-2 font-medium">
          <FileText size={15} aria-hidden="true" />
          <span className="truncate">{artifactDisplayTitle(artifact)}</span>
        </div>
        <div className="agenthub-faint mt-2 line-clamp-2">
          PDF 可在完整预览中阅读，也可在新标签页打开。
        </div>
      </div>
    );
  }
  return (
    <object
      data={previewUrl}
      type="application/pdf"
      className="h-[74vh] w-full rounded-2xl border bg-white"
      aria-label={artifactDisplayTitle(artifact)}
    >
      <DocumentFilePreview artifact={artifact} content={artifact.content} previewUrl={previewUrl} />
    </object>
  );
}

function DocumentFilePreview({
  artifact,
  content,
  previewUrl,
  compact = false,
}: {
  artifact: Artifact;
  content: string;
  previewUrl: string | null;
  compact?: boolean;
}) {
  const preview = getArtifactPreviewInfo(artifact);
  const title = artifactDisplayTitle(artifact);
  const summary = isMetadataOnlyContent(content)
    ? `${preview.label}${artifact.filePath ? ` · ${artifact.filePath}` : ""}`
    : content.trim().slice(0, compact ? 160 : 480);
  return (
    <div className={`agenthub-code-surface rounded-2xl border p-4 ${compact ? "" : "min-h-72"}`}>
      <div className="flex min-w-0 items-start gap-3">
        <span className="agenthub-soft inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border">
          {artifactIcon(artifact, "agenthub-strong")}
        </span>
        <div className="min-w-0 flex-1">
          <div className="agenthub-strong truncate text-sm font-semibold">{title}</div>
          <div className="agenthub-faint mt-1 truncate text-xs">
            {preview.label}
            {preview.extension ? ` · ${preview.extension.replace(".", "").toUpperCase()}` : ""}
            {preview.mediaType ? ` · ${preview.mediaType}` : ""}
          </div>
        </div>
      </div>
      {summary && (
        <p className={`agenthub-muted mt-3 whitespace-pre-wrap text-xs leading-5 ${compact ? "line-clamp-3" : ""}`}>
          {summary}
        </p>
      )}
      {previewUrl && (
        <div className="mt-4 flex flex-wrap gap-2">
          <a
            href={previewUrl}
            target="_blank"
            rel="noreferrer"
            className="agenthub-icon-button inline-flex h-8 items-center gap-2 rounded-md px-3 text-xs"
          >
            <ExternalLink size={13} aria-hidden="true" />
            打开原文件
          </a>
          {preview.downloadUrl && (
            <a
              href={preview.downloadUrl}
              target="_blank"
              rel="noreferrer"
              className="agenthub-icon-button inline-flex h-8 items-center gap-2 rounded-md px-3 text-xs"
            >
              <Download size={13} aria-hidden="true" />
              下载
            </a>
          )}
        </div>
      )}
    </div>
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

