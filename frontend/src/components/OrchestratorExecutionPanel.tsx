import { useEffect, useMemo, useState } from "react";
import { Activity, CheckCircle2, ChevronDown, ChevronRight, Clock3, GitBranch, XCircle } from "lucide-react";
import { fetchOrchestratorExecution } from "../api/client";
import type { OrchestratorExecution, OrchestratorExecutionTask } from "../types";

interface Props {
  initialExecution: OrchestratorExecution;
}

export function OrchestratorExecutionPanel({ initialExecution }: Props) {
  const [execution, setExecution] = useState(initialExecution);
  const [showEvents, setShowEvents] = useState(false);
  const isLive = execution.status === "pending" || execution.status === "running";
  const completed = execution.tasks.filter((task) => task.status === "completed").length;
  const progress = execution.tasks.length ? Math.round((completed / execution.tasks.length) * 100) : 0;
  const phases = useMemo(() => groupTasksByPhase(execution.tasks), [execution.tasks]);

  useEffect(() => {
    setExecution(initialExecution);
  }, [initialExecution.executionId, initialExecution.updatedAt, initialExecution.status]);

  useEffect(() => {
    if (!isLive) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const next = await fetchOrchestratorExecution(execution.executionId);
        if (!cancelled) setExecution(next);
      } catch {
        // Keep the last known execution snapshot; chat should not flicker on transient polling failures.
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
          <StatusBadge status={execution.status} live={isLive} />
        </div>
        <div className="mt-3">
          <div className="flex items-center justify-between text-[11px] text-slate-500">
            <span>{completed}/{execution.tasks.length} 任务完成</span>
            <span>{progress}%</span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                execution.status === "failed" || execution.status === "error" ? "bg-red-500" : "bg-indigo-600"
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="grid gap-2 p-3">
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

function StatusBadge({ status, live }: { status: string; live: boolean }) {
  const cls = status === "completed"
    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
    : status === "failed" || status === "error"
      ? "border-red-200 bg-red-50 text-red-700"
      : "border-indigo-200 bg-indigo-50 text-indigo-700";
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-semibold ${cls}`}>
      {status === "completed" ? <CheckCircle2 size={12} /> : status === "failed" || status === "error" ? <XCircle size={12} /> : <Activity size={12} className={live ? "animate-pulse" : ""} />}
      {statusLabel(status)}
      {live && <span className="font-normal opacity-70">自动刷新</span>}
    </span>
  );
}

function TaskStatus({ status }: { status: string }) {
  const cls = status === "completed"
    ? "text-emerald-700"
    : status === "failed" || status === "error"
      ? "text-red-700"
      : status === "running"
        ? "text-indigo-700"
        : "text-slate-500";
  const icon = status === "completed"
    ? <CheckCircle2 size={13} />
    : status === "running"
      ? <Clock3 size={13} className="animate-pulse" />
      : status === "failed" || status === "error"
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
