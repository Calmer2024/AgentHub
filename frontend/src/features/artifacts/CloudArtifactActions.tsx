import { ExternalLink, Globe2, Loader2, Rocket, RotateCcw, ScrollText } from "lucide-react";

export function CloudArtifactActions({
  canPreview,
  canDeploy,
  deliveryRunning,
  hasDeployment,
  deploymentFailed,
  hasOpenableUrl,
  onCreatePreview,
  onCreateDeployment,
  onOpenDeploymentLogs,
  onRetryDeployment,
  onOpenUrl,
}: {
  canPreview: boolean;
  canDeploy: boolean;
  deliveryRunning: boolean;
  hasDeployment: boolean;
  deploymentFailed: boolean;
  hasOpenableUrl: boolean;
  onCreatePreview: () => void;
  onCreateDeployment: () => void;
  onOpenDeploymentLogs: () => void;
  onRetryDeployment: () => void;
  onOpenUrl: () => void;
}) {
  return (
    <div className="flex items-center gap-1">
      {canPreview && (
        <button
          type="button"
          onClick={onCreatePreview}
          disabled={deliveryRunning}
          className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
          aria-label="创建云端预览"
          title="创建云端预览"
        >
          {deliveryRunning && !hasDeployment ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Globe2 size={14} aria-hidden="true" />}
        </button>
      )}
      {canDeploy && (
        <>
          <button
            type="button"
            onClick={onCreateDeployment}
            disabled={deliveryRunning}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
            aria-label="发布云端版本"
            title="发布云端版本"
          >
            {deliveryRunning && hasDeployment ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Rocket size={14} aria-hidden="true" />}
          </button>
          <button
            type="button"
            onClick={onOpenDeploymentLogs}
            disabled={!hasDeployment}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
            aria-label="查看发布日志"
            title="查看发布日志"
          >
            <ScrollText size={14} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onRetryDeployment}
            disabled={!deploymentFailed || deliveryRunning}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
            aria-label="重试发布"
            title="重试发布"
          >
            <RotateCcw size={14} aria-hidden="true" />
          </button>
        </>
      )}
      <button
        type="button"
        onClick={onOpenUrl}
        disabled={!hasOpenableUrl}
        className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:cursor-not-allowed disabled:opacity-45"
        aria-label="打开云端地址"
        title="打开云端地址"
      >
        <ExternalLink size={14} aria-hidden="true" />
      </button>
    </div>
  );
}
