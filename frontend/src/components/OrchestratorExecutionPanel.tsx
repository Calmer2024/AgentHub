import { useEffect, useMemo, useState } from "react";
import { Activity, CheckCircle2, ChevronDown, ChevronRight, Clock3, GitBranch, Play, Square, Trash2, XCircle } from "lucide-react";
import {
  cancelOrchestratorExecution,
  fetchOrchestratorExecution,
  interruptOrchestratorExecution,
  resumeOrchestratorExecution,
} from "../api/client";
import type { OrchestratorExecution, OrchestratorExecutionTask } from "../types";

interface Props {
  initialExecution: OrchestratorExecution;
}

export function OrchestratorExecutionPanel({ initialExecution }: Props) {
  const [execution, setExecution] = useState(initialExecution);
  const [showEvents, setShowEvents] = useState(false);
  const [pollingLost, setPollingLost] = useState(false);
  const [controlBusy, setControlBusy] = useState<"interrupt" | "resume" | "cancel" | null>(null);
  const isLive = !pollingLost && ["pending", "running", "cancelling"].includes(execution.status);
  const canInterrupt = !pollingLost && !controlBusy && ["pending", "running", "cancelling"].includes(execution.status);
  const canResume = !pollingLost && !controlBusy && execution.status === "interrupted";
  const canAbandon = !pollingLost && !controlBusy && execution.status === "interrupted";
  const completed = execution.tasks.filter((task) => task.status === "completed").length;
  const progress = execution.tasks.length ? Math.round((completed / execution.tasks.length) * 100) : 0;
  const phases = useMemo(() => groupTasksByPhase(execution.tasks), [execution.tasks]);

  useEffect(() => {
    setExecution(initialExecution);
    setPollingLost(false);
    setControlBusy(null);
  }, [initialExecution.executionId, initialExecution.updatedAt, initialExecution.status]);

  useEffect(() => {
    if (!isLive) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const next = await fetchOrchestratorExecution(execution.executionId);
        if (!cancelled) {
          setExecution(next);
          if (["cancelled", "interrupted", "completed", "failed"].includes(next.status)) {
            setControlBusy(null);
          }
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "";
        if (!cancelled && (message.includes("404") || message.includes("Execution 不存在"))) {
          setPollingLost(true);
        }
      }
    }, 700);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [execution.executionId, isLive]);

  return (
    <section className="mt-3 overflow-hidden rounded-lg border border-slate-200 bg-white text-slate-950 shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50 px-3 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <GitBranch size={15} className="text-indigo-600" />
              <span>{execution.planId}</span>
            </div>
            <p className="mt-1 font-mono text-[11px] text-slate-500">{execution.executionId}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <StatusBadge status={execution.status} live={isLive} stale={pollingLost} />
            {canInterrupt && (
              <button
                type="button"
                onClick={async () => {
                  setControlBusy("interrupt");
                  try {
                    const next = await interruptOrchestratorExecution(
                      execution.executionId,
                      "用户在调度执行面板停止运行",
                    );
                    setExecution(next);
                    window.dispatchEvent(new CustomEvent("agenthub:orchestrator-execution-interrupted", {
                      detail: { sessionId: next.sessionId, executionId: next.executionId, runId: next.runId ?? null },
                    }));
                  } finally {
                    setControlBusy(null);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-700 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={Boolean(controlBusy)}
                title="中断当前调度执行，稍后可继续"
              >
                <Square size={12} />
                {controlBusy === "interrupt" ? "停止中" : "停止"}
              </button>
            )}
            {canResume && (
              <button
                type="button"
                onClick={async () => {
                  setControlBusy("resume");
                  try {
                    const next = await resumeOrchestratorExecution(execution.executionId);
                    setExecution(next);
                    window.dispatchEvent(new CustomEvent("agenthub:orchestrator-execution-resumed", {
                      detail: { sessionId: next.sessionId, executionId: next.executionId, runId: next.runId ?? null },
                    }));
                  } finally {
                    setControlBusy(null);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] font-semibold text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={Boolean(controlBusy)}
                title="从未完成任务继续调度执行"
              >
                <Play size={12} />
                {controlBusy === "resume" ? "恢复中" : "继续执行"}
              </button>
            )}
            {canAbandon && (
              <button
                type="button"
                onClick={async () => {
                  setControlBusy("cancel");
                  try {
                    const next = await cancelOrchestratorExecution(execution.executionId);
                    setExecution(next);
                    window.dispatchEvent(new CustomEvent("agenthub:orchestrator-execution-cancelled", {
                      detail: { sessionId: next.sessionId, executionId: next.executionId, runId: next.runId ?? null },
                    }));
                  } finally {
                    setControlBusy(null);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={Boolean(controlBusy)}
                title="放弃本次执行，进入不可恢复的取消状态"
              >
                <Trash2 size={12} />
                {controlBusy === "cancel" ? "放弃中" : "放弃执行"}
              </button>
            )}
          </div>
        </div>
        <div className="mt-3">
          <div className="flex items-center justify-between text-[11px] text-slate-500">
            <span>{completed}/{execution.tasks.length} 任务完成</span>
            <span>{progress}%</span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                execution.status === "failed" || execution.status === "error"
                  ? "bg-red-500"
                  : execution.status === "cancelled"
                    ? "bg-slate-400"
                    : "bg-indigo-600"
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="grid gap-2 p-3">
        {execution.status === "interrupted" && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
            执行已中断，已完成任务会保留；点击“继续执行”将从未完成任务恢复调度。
          </div>
        )}
        {phases.map((phase) => (
          <div key={phase.index} className="rounded-md border border-slate-100 bg-slate-50 p-2">
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Phase {phase.index}
              </p>
              <span className="rounded bg-white px-2 py-0.5 text-[11px] text-slate-500">
                {phase.tasks.length > 1 ? "并行" : "串行"}
              </span>
            </div>
            <div className="space-y-2">
              {phase.tasks.map((task) => (
                <TaskRow key={task.taskId} task={task} />
              ))}
            </div>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setShowEvents((value) => !value)}
        className="flex w-full items-center justify-between gap-2 border-t border-slate-100 px-3 py-2 text-left text-xs font-semibold text-slate-600 hover:bg-slate-50"
      >
        <span>事件日志 · {execution.events.length}</span>
        {showEvents ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {showEvents && (
        <div className="max-h-56 overflow-auto border-t border-slate-100 bg-slate-950 p-3">
          {execution.events.map((event, index) => (
            <p key={`${event.type}-${index}`} className="border-b border-white/10 py-1.5 text-[11px] leading-5 text-slate-200 last:border-b-0">
              <span className="font-mono text-indigo-200">{event.type}</span>
              {typeof event.phase === "number" && <span className="text-slate-400"> · phase {event.phase}</span>}
              <span className="text-slate-400"> · </span>
              <span>{event.message}</span>
            </p>
          ))}
        </div>
      )}
    </section>
  );
}

function TaskRow({ task }: { task: OrchestratorExecutionTask }) {
  return (
    <article className="rounded-md border border-slate-200 bg-white px-2.5 py-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-slate-950">{task.taskId} · {task.title}</p>
          <p className="mt-1 text-[11px] leading-5 text-slate-500">
            @{task.assignedAgentName ?? task.assignedAgentId ?? "未分配"} · 依赖：{task.dependsOn.length ? task.dependsOn.join(" / ") : "无"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
            task.runnerType === "cli" ? "bg-indigo-50 text-indigo-700" : "bg-slate-100 text-slate-500"
          }`}>
            {task.runnerType ?? "mock"}
          </span>
          <TaskStatus status={task.status} />
        </div>
      </div>
      {task.summary && (
        <p className="mt-2 rounded bg-emerald-50 px-2 py-1.5 text-[11px] leading-5 text-emerald-800">
          {task.summary}
        </p>
      )}
    </article>
  );
}

function StatusBadge({ status, live, stale }: { status: string; live: boolean; stale: boolean }) {
  const cls = status === "completed"
    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
    : status === "failed" || status === "error"
      ? "border-red-200 bg-red-50 text-red-700"
      : status === "interrupted"
        ? "border-amber-200 bg-amber-50 text-amber-700"
      : status === "cancelled"
        ? "border-slate-200 bg-slate-100 text-slate-600"
      : "border-indigo-200 bg-indigo-50 text-indigo-700";
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-semibold ${cls}`}>
      {status === "completed" ? <CheckCircle2 size={12} /> : status === "failed" || status === "error" || status === "cancelled" ? <XCircle size={12} /> : <Activity size={12} className={live ? "animate-pulse" : ""} />}
      {statusLabel(status)}
      {live && <span className="font-normal opacity-70">自动刷新</span>}
      {stale && <span className="font-normal opacity-70">历史快照</span>}
    </span>
  );
}

function TaskStatus({ status }: { status: string }) {
  const cls = status === "completed"
    ? "text-emerald-700"
    : status === "failed" || status === "error"
      ? "text-red-700"
      : status === "interrupted"
        ? "text-amber-700"
      : status === "cancelled"
        ? "text-slate-500"
      : status === "running"
        ? "text-indigo-700"
        : "text-slate-500";
  const icon = status === "completed"
    ? <CheckCircle2 size={13} />
    : status === "running"
      ? <Clock3 size={13} className="animate-pulse" />
      : status === "failed" || status === "error" || status === "cancelled"
        ? <XCircle size={13} />
        : <Clock3 size={13} />;
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold ${cls}`}>
      {icon}
      {statusLabel(status)}
    </span>
  );
}

function statusLabel(status: string) {
  if (status === "completed") return "completed";
  if (status === "running") return "running";
  if (status === "cancelling") return "cancelling";
  if (status === "interrupted") return "interrupted";
  if (status === "cancelled") return "cancelled";
  if (status === "pending") return "pending";
  if (status === "failed" || status === "error") return "failed";
  return status;
}

function groupTasksByPhase(tasks: OrchestratorExecutionTask[]) {
  const taskById = new Map(tasks.map((task) => [task.taskId, task]));
  const depthCache = new Map<string, number>();
  const depth = (taskId: string, seen = new Set<string>()): number => {
    if (depthCache.has(taskId)) return depthCache.get(taskId) ?? 0;
    if (seen.has(taskId)) return 0;
    seen.add(taskId);
    const task = taskById.get(taskId);
    const value = !task || task.dependsOn.length === 0
      ? 0
      : 1 + Math.max(...task.dependsOn.map((dep) => depth(dep, new Set(seen))));
    depthCache.set(taskId, value);
    return value;
  };

  const grouped = new Map<number, OrchestratorExecutionTask[]>();
  for (const task of tasks) {
    const phase = depth(task.taskId);
    grouped.set(phase, [...(grouped.get(phase) ?? []), task]);
  }
  return [...grouped.entries()]
    .sort(([a], [b]) => a - b)
    .map(([index, phaseTasks]) => ({ index, tasks: phaseTasks }));
}
