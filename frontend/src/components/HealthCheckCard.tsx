import { AlertCircle, CheckCircle2, Loader2, OctagonAlert, RefreshCw } from "lucide-react";
import type { SystemHealthRead } from "../types";

interface Props {
  health: SystemHealthRead | null;
  loading?: boolean;
  compact?: boolean;
  onRefresh: () => void;
}

function iconFor(overall?: SystemHealthRead["overall"]) {
  if (overall === "ok") return <CheckCircle2 size={15} aria-hidden="true" />;
  if (overall === "error") return <OctagonAlert size={15} aria-hidden="true" />;
  return <AlertCircle size={15} aria-hidden="true" />;
}

function textFor(health: SystemHealthRead | null) {
  if (!health) return "环境未检查";
  if (health.overall === "ok") return "环境就绪";
  if (health.overall === "error") return "环境阻断";
  return "环境有警告";
}

export function HealthCheckCard({ health, loading, compact, onRefresh }: Props) {
  const tone = health?.overall === "ok"
    ? "border-emerald-300/20 bg-emerald-300/[0.06] text-emerald-100"
    : health?.overall === "error"
      ? "border-rose-300/25 bg-rose-300/[0.07] text-rose-100"
      : "border-amber-300/25 bg-amber-300/[0.07] text-amber-100";

  return (
    <div className={`rounded-lg border ${tone}`}>
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-medium">
        {loading ? <Loader2 size={15} className="animate-spin" /> : iconFor(health?.overall)}
        <span className="min-w-0 flex-1 truncate">{textFor(health)}</span>
        <button
          type="button"
          onClick={onRefresh}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md hover:bg-white/10"
          aria-label="刷新环境体检"
          title="刷新环境体检"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      {!compact && health && health.overall !== "ok" && (
        <div className="space-y-1 border-t border-white/10 px-3 py-2">
          {(health.blockingReasons.length > 0
            ? health.blockingReasons
            : health.items.filter((item) => item.severity !== "info").map((item) => item.detail)
          ).slice(0, 3).map((reason) => (
            <div key={reason} className="text-[11px] leading-relaxed text-current/85">
              {reason}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
