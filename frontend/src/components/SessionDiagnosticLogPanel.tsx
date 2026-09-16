import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy, Pause, Play, RefreshCw, Search } from "lucide-react";
import { fetchSessionDiagnosticLogs } from "../api/client";
import { MenuSelect } from "./MenuSelect";
import type {
  SessionDiagnosticLogEntry,
  SessionDiagnosticLogLevel,
  SessionDiagnosticLogPayload,
} from "../types";

interface Props {
  sessionId: string;
}

const LEVEL_STYLE: Record<SessionDiagnosticLogLevel, { label: string; row: string; badge: string; dot: string }> = {
  input: { label: "输入", row: "border-l-sky-500 bg-sky-500/[0.045]", badge: "bg-sky-500/15 text-sky-600 dark:text-sky-300", dot: "bg-sky-500" },
  output: { label: "输出", row: "border-l-violet-500 bg-violet-500/[0.045]", badge: "bg-violet-500/15 text-violet-600 dark:text-violet-300", dot: "bg-violet-500" },
  info: { label: "运行", row: "border-l-blue-500 bg-blue-500/[0.045]", badge: "bg-blue-500/15 text-blue-600 dark:text-blue-300", dot: "bg-blue-500" },
  success: { label: "成功", row: "border-l-emerald-500 bg-emerald-500/[0.045]", badge: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300", dot: "bg-emerald-500" },
  warning: { label: "警告", row: "border-l-amber-500 bg-amber-500/[0.055]", badge: "bg-amber-500/15 text-amber-700 dark:text-amber-300", dot: "bg-amber-500" },
  error: { label: "错误", row: "border-l-rose-500 bg-rose-500/[0.06]", badge: "bg-rose-500/15 text-rose-600 dark:text-rose-300", dot: "bg-rose-500" },
  debug: { label: "调试", row: "border-l-slate-400 bg-slate-500/[0.035]", badge: "bg-slate-500/15 text-slate-600 dark:text-slate-300", dot: "bg-slate-400" },
};

const CATEGORY_LABEL: Record<string, string> = {
  session: "会话",
  message: "消息",
  run: "运行",
  task: "任务",
  process: "进程",
  artifact: "产物",
  orchestrator: "编排",
  runtime: "运行时",
  stdio: "标准流",
};

export function SessionDiagnosticLogPanel({ sessionId }: Props) {
  const [payload, setPayload] = useState<SessionDiagnosticLogPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState("all");
  const [category, setCategory] = useState("all");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      const next = await fetchSessionDiagnosticLogs(sessionId);
      setPayload(next);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "诊断日志加载失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [sessionId]);

  useEffect(() => {
    setPayload(null);
    setLoading(true);
    setExpanded(new Set());
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => void refresh(true), 2000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, refresh]);

  const categories = useMemo(
    () => [...new Set(payload?.entries.map((entry) => entry.category) ?? [])].sort(),
    [payload],
  );
  const levelOptions = useMemo(() => [
    { value: "all", label: "全部级别" },
    ...Object.entries(LEVEL_STYLE).map(([value, style]) => ({ value, label: style.label })),
  ], []);
  const categoryOptions = useMemo(() => [
    { value: "all", label: "全部来源" },
    ...categories.map((value) => ({ value, label: CATEGORY_LABEL[value] ?? value })),
  ], [categories]);
  const visibleEntries = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return (payload?.entries ?? []).filter((entry) => {
      if (level !== "all" && entry.level !== level) return false;
      if (category !== "all" && entry.category !== category) return false;
      if (!needle) return true;
      return [entry.title, entry.message, entry.source, entry.id, entry.runId, entry.taskId,
        entry.processId, entry.messageId, entry.agentId, JSON.stringify(entry.details)]
        .some((value) => String(value ?? "").toLocaleLowerCase().includes(needle));
    });
  }, [category, level, payload, query]);

  const copy = useCallback(async (text: string, key: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(key);
    window.setTimeout(() => setCopied((current) => current === key ? null : current), 1400);
  }, []);

  const copyAll = useCallback(() => {
    if (!payload) return;
    const lines = [
      `Session ID: ${payload.session.id}`,
      `Project ID: ${payload.session.projectId ?? "-"}`,
      `Generated At: ${payload.generatedAt}`,
      "",
      ...visibleEntries.map((entry) => [
        `[${formatTimestamp(entry.timestamp)}] [${entry.level.toUpperCase()}] [${entry.category}] ${entry.source} · ${entry.title}`,
        entry.message,
        idsText(entry),
        JSON.stringify(entry.details),
      ].filter(Boolean).join(" | ")),
    ];
    void copy(lines.join("\n"), "all");
  }, [copy, payload, visibleEntries]);

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[color:var(--ah-bg)]" aria-label="会话诊断日志">
      <div className="shrink-0 border-b border-[color:var(--ah-border)] bg-[color:var(--ah-panel)] px-4 py-3 md:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${autoRefresh ? "animate-pulse bg-emerald-500" : "bg-slate-400"}`} />
              <h2 className="agenthub-strong text-sm font-semibold">会话诊断日志</h2>
              <span className="agenthub-muted text-xs">{autoRefresh ? "实时更新" : "已暂停"}</span>
            </div>
            <div className="mt-2 flex min-w-0 flex-wrap items-center gap-2 text-xs">
              <span className="agenthub-muted">Session ID</span>
              <code className="max-w-[min(72vw,680px)] select-all truncate rounded-md bg-black/5 px-2 py-1 font-mono dark:bg-white/10">{sessionId}</code>
              <CopyButton copied={copied === "session"} label="复制 Session ID" onClick={() => void copy(sessionId, "session")} />
              {payload?.session.projectId && (
                <><span className="agenthub-muted ml-2">Project</span><code className="font-mono">{payload.session.projectId}</code></>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => setAutoRefresh((value) => !value)} className={`agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-lg ${autoRefresh ? "text-emerald-600 dark:text-emerald-300" : ""}`} aria-label={autoRefresh ? "暂停自动刷新" : "开启自动刷新"} title={autoRefresh ? "暂停自动刷新" : "开启自动刷新"}>
              {autoRefresh ? <Pause size={13} /> : <Play size={13} />}
            </button>
            <button type="button" onClick={() => void refresh()} className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-lg" aria-label="刷新诊断日志" title="刷新诊断日志">
              <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            </button>
            <button type="button" onClick={copyAll} disabled={!payload} className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-lg disabled:opacity-50" aria-label="复制当前日志" title="复制当前日志">
              {copied === "all" ? <Check size={13} /> : <Copy size={13} />}
            </button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="agenthub-muted pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2" size={14} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索内容、来源或任意关联 ID" className="agenthub-search-field h-9 w-full rounded-lg pl-8 pr-3 text-xs outline-none" />
          </div>
          <MenuSelect value={level} options={levelOptions} onChange={setLevel} ariaLabel="日志级别" variant="filter" className="h-9 w-32" />
          <MenuSelect value={category} options={categoryOptions} onChange={setCategory} ariaLabel="日志来源" variant="filter" className="h-9 w-32" />
        </div>

        {payload && (
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
            <Count label="日志" value={payload.counts.entries} />
            <Count label="消息" value={payload.counts.messages} />
            <Count label="运行" value={payload.counts.runs} />
            <Count label="任务" value={payload.counts.tasks} />
            <Count label="进程" value={payload.counts.processes} />
            <Count label="产物" value={payload.counts.artifacts} />
            <Count label="计划" value={payload.counts.plans} />
            <span className="agenthub-muted ml-auto self-center">生成于 {formatTimestamp(payload.generatedAt)}</span>
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3 font-mono text-xs md:px-6">
        {loading && !payload ? (
          <div className="agenthub-muted flex h-full items-center justify-center">正在聚合会话诊断信息…</div>
        ) : error && !payload ? (
          <div className="agenthub-status-error rounded-xl border p-4">{error}</div>
        ) : visibleEntries.length === 0 ? (
          <div className="agenthub-muted flex h-full items-center justify-center">没有符合筛选条件的日志</div>
        ) : (
          <div className="space-y-2 pb-6">
            {error && <div className="agenthub-status-warning rounded-lg border px-3 py-2">自动刷新失败：{error}</div>}
            {visibleEntries.map((entry) => {
              const style = LEVEL_STYLE[entry.level] ?? LEVEL_STYLE.debug;
              const isExpanded = expanded.has(entry.id);
              return (
                <article key={entry.id} className={`rounded-lg border border-[color:var(--ah-border)] border-l-[3px] px-3 py-2.5 ${style.row}`}>
                  <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                    <time className="agenthub-muted tabular-nums">{formatTimestamp(entry.timestamp)}</time>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${style.badge}`}>{style.label}</span>
                    <span className="rounded bg-black/5 px-1.5 py-0.5 dark:bg-white/10">{CATEGORY_LABEL[entry.category] ?? entry.category}</span>
                    <span className="font-semibold">{entry.source}</span>
                    <span className="agenthub-muted">·</span>
                    <span className="agenthub-strong font-semibold">{entry.title}</span>
                  </div>
                  <p className="mt-1.5 whitespace-pre-wrap break-words leading-5">{entry.message}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <IdChip label="RUN" value={entry.runId} onCopy={copy} copied={copied} />
                    <IdChip label="TASK" value={entry.taskId} onCopy={copy} copied={copied} />
                    <IdChip label="PROCESS" value={entry.processId} onCopy={copy} copied={copied} />
                    <IdChip label="MESSAGE" value={entry.messageId} onCopy={copy} copied={copied} />
                    <IdChip label="AGENT" value={entry.agentId} onCopy={copy} copied={copied} />
                    <button type="button" onClick={() => setExpanded((current) => toggleSet(current, entry.id))} className="agenthub-muted ml-auto inline-flex items-center gap-1 rounded px-1.5 py-1 hover:bg-black/5 dark:hover:bg-white/10">
                      {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}详情
                    </button>
                  </div>
                  {isExpanded && <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-black/[0.045] p-3 leading-5 dark:bg-black/20">{JSON.stringify(entry.details, null, 2)}</pre>}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return <span className="rounded-full border border-[color:var(--ah-border)] bg-black/[0.025] px-2 py-1 dark:bg-white/[0.04]">{label} {value}</span>;
}

function CopyButton({ copied, label, onClick }: { copied: boolean; label: string; onClick: () => void }) {
  return <button type="button" onClick={onClick} className="agenthub-icon-button inline-flex h-7 w-7 items-center justify-center rounded-md" aria-label={label} title={label}>{copied ? <Check size={12} /> : <Copy size={12} />}</button>;
}

function IdChip({ label, value, onCopy, copied }: {
  label: string;
  value?: string | null;
  onCopy: (text: string, key: string) => Promise<void>;
  copied: string | null;
}) {
  if (!value) return null;
  const key = `${label}:${value}`;
  return <button type="button" onClick={() => void onCopy(value, key)} title={`复制 ${label}: ${value}`} className="group inline-flex max-w-full items-center gap-1 rounded bg-black/5 px-1.5 py-1 text-[10px] hover:bg-black/10 dark:bg-white/10 dark:hover:bg-white/15"><b>{label}</b><span className="max-w-44 truncate">{value}</span>{copied === key ? <Check size={10} /> : <Copy size={10} className="opacity-0 group-hover:opacity-100" />}</button>;
}

function toggleSet(current: Set<string>, value: string): Set<string> {
  const next = new Set(current);
  if (next.has(value)) next.delete(value); else next.add(value);
  return next;
}

function idsText(entry: SessionDiagnosticLogEntry): string {
  return [
    entry.runId && `run=${entry.runId}`,
    entry.taskId && `task=${entry.taskId}`,
    entry.processId && `process=${entry.processId}`,
    entry.messageId && `message=${entry.messageId}`,
    entry.agentId && `agent=${entry.agentId}`,
  ].filter(Boolean).join(" ");
}

function formatTimestamp(value: string): string {
  if (!value) return "--:--:--.---";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const base = new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  }).format(date);
  return `${base}.${String(date.getMilliseconds()).padStart(3, "0")}`;
}
