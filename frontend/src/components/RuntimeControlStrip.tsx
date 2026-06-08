import { AlertTriangle, CheckCircle2, CircleStop, Clock3, Loader2, XCircle } from "lucide-react";
import type { RunRead, TaskRead } from "../types";

interface Props {
  run?: RunRead | null;
  tasks?: TaskRead[];
  onCancel: (runId: string) => void;
  cancelling?: boolean;
}

const ACTIVE = new Set<RunRead["status"]>(["queued", "running", "pausing", "paused", "cancelling"]);

function statusText(status: RunRead["status"]) {
  if (status === "queued") return "准备执行";
  if (status === "running") return "运行中";
  if (status === "paused") return "等待审批";
  if (status === "interrupted") return "已中断";
  if (status === "cancelling") return "正在停止";
  if (status === "cancelled") return "已取消";
  if (status === "failed") return "执行失败";
  return "已完成";
}

function statusIcon(status: RunRead["status"]) {
  if (status === "running" || status === "queued" || status === "cancelling") {
    return <Loader2 size={13} className="animate-spin" aria-hidden="true" />;
  }
  if (status === "completed") return <CheckCircle2 size={13} aria-hidden="true" />;
  if (status === "failed") return <AlertTriangle size={13} aria-hidden="true" />;
  if (status === "cancelled") return <XCircle size={13} aria-hidden="true" />;
  if (status === "interrupted") return <AlertTriangle size={13} aria-hidden="true" />;
  return <Clock3 size={13} aria-hidden="true" />;
}

function elapsed(startedAt: string, completedAt?: string | null) {
  const start = Date.parse(startedAt);
  const end = completedAt ? Date.parse(completedAt) : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "--:--";
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

export function RuntimeControlStrip({ run, tasks = [], onCancel, cancelling }: Props) {
  if (!run) return null;
  const canCancel = ACTIVE.has(run.status) && run.status !== "paused" && run.status !== "cancelling";
  const primaryTask = tasks.find((task) => task.status === "running")
    ?? tasks.find((task) => task.status === "paused")
    ?? tasks[0];

  return (
    <div className="agenthub-soft mt-3 flex min-h-9 min-w-0 max-w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs">
      <span className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
        run.status === "failed" ? "text-[color:var(--ah-danger)]" : "agenthub-muted"
      }`}>
        {statusIcon(run.status)}
      </span>
      <span className="font-medium">{statusText(run.status)}</span>
      {primaryTask && (
        <span className="agenthub-muted min-w-0 flex-1 truncate">
          {primaryTask.role ?? "executor"} · {primaryTask.name}
        </span>
      )}
      <span className="agenthub-muted font-mono text-[11px]">
        {elapsed(run.startedAt, run.completedAt)}
      </span>
      {canCancel && (
        <button
          type="button"
          onClick={() => onCancel(run.id)}
          disabled={cancelling}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[color:var(--ah-danger)] transition hover:bg-[color:var(--ah-danger-soft)] disabled:cursor-not-allowed disabled:opacity-50"
          style={{ borderColor: "color-mix(in srgb, var(--ah-danger) 35%, transparent)" }}
          aria-label="停止本次运行"
          title="停止本次运行"
        >
          {cancelling ? <Loader2 size={13} className="animate-spin" /> : <CircleStop size={14} />}
        </button>
      )}
    </div>
  );
}
