import { Download, Eye, Hammer, Loader2, PackageOpen, ScrollText } from "lucide-react";

export function LocalArtifactActions({
  canBuildExport,
  canPreview,
  buildRunning,
  hasLatestBuild,
  hasSucceededBuild,
  onStartBuild,
  onOpenLogs,
  onOpenSourceExport,
  onOpenBuildExport,
  onOpenBuildPreview,
}: {
  canBuildExport: boolean;
  canPreview: boolean;
  buildRunning: boolean;
  hasLatestBuild: boolean;
  hasSucceededBuild: boolean;
  onStartBuild: () => void;
  onOpenLogs: () => void;
  onOpenSourceExport: () => void;
  onOpenBuildExport: () => void;
  onOpenBuildPreview: () => void;
}) {
  return (
    <div className="flex items-center gap-1">
      {canBuildExport && (
        <>
          <button
            type="button"
            onClick={onStartBuild}
            disabled={buildRunning}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
            aria-label="执行项目构建"
            title="执行项目构建"
          >
            {buildRunning ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Hammer size={14} aria-hidden="true" />}
          </button>
          <button
            type="button"
            onClick={onOpenLogs}
            disabled={!hasLatestBuild}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
            aria-label="查看构建日志"
            title="查看构建日志"
          >
            <ScrollText size={14} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onOpenSourceExport}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
            aria-label="下载源码包"
            title="下载源码包"
          >
            <Download size={14} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onOpenBuildExport}
            disabled={!hasSucceededBuild}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
            aria-label="下载构建产物"
            title="下载构建产物"
          >
            <PackageOpen size={14} aria-hidden="true" />
          </button>
        </>
      )}
      {canPreview && (
        <button
          type="button"
          onClick={onOpenBuildPreview}
          disabled={!hasSucceededBuild}
          className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
          aria-label="打开构建预览"
          title="打开构建预览"
        >
          <Eye size={14} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
