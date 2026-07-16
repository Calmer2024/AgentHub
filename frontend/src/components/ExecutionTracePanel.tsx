import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  AlertCircle, CheckCircle2, ChevronDown, ChevronRight,
  Clock3, Code2, FileCode2, FolderOpen, Hammer, Info, Play,
  Maximize2, Search, SquareActivity, Terminal, TriangleAlert, X, XCircle,
} from "lucide-react";
import type { ExecutionTrace, ExecutionTraceItem } from "../types";
import { formatChinaTime } from "../utils/time";

interface Props {
  trace?: ExecutionTrace | null;
  className?: string;
}

const KIND_LABELS: Record<ExecutionTraceItem["kind"], string> = {
  process: "进程",
  progress: "过程",
  tool: "工具",
  command: "命令",
  file: "文件",
  artifact: "产物",
  prompt: "确认",
  error: "错误",
  info: "信息",
};

const ACTION_LABELS: Record<string, string> = {
  start: "启动",
  reuse: "复用",
  recover: "恢复",
  complete: "完成",
  run: "执行",
  read: "读取",
  write: "写入",
  edit: "编辑",
  search: "搜索",
  list: "列出",
  delete: "删除",
  retry: "重试",
  confirm: "确认",
  artifact: "产物",
  error: "错误",
  step: "步骤",
  think: "思考",
  result: "结果",
};

export function ExecutionTracePanel({ trace, className = "" }: Props) {
  const items = useMemo(() => compactTraceItems(trace?.items ?? []), [trace?.items]);
  const traceScrollRef = useRef<HTMLDivElement | null>(null);
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);
  const isRunning = trace?.status === "running";
  const isError = trace?.status === "error";
  const isCancelled = trace?.status === "cancelled";
  const isInterrupted = trace?.status === "interrupted";
  const open = manualOpen ?? false;

  useEffect(() => {
    if (trace?.status === "running") setManualOpen(null);
    if (trace?.status && trace.status !== "running" && manualOpen === null) {
      setManualOpen(false);
    }
  }, [trace?.status]);

  useEffect(() => {
    if (!open || !isRunning || items.length === 0) return;
    const container = traceScrollRef.current;
    if (!container) return;
    if (typeof container.scrollTo === "function") {
      container.scrollTo({ top: container.scrollHeight });
    } else {
      container.scrollTop = container.scrollHeight;
    }
  }, [items.length, isRunning, open]);

  useEffect(() => {
    if (!fullscreenOpen || typeof document === "undefined") return;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullscreenOpen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [fullscreenOpen]);

  const stats = useMemo(() => traceStats(items), [items]);
  const elapsed = useMemo(() => traceDuration(trace, items), [items, trace]);
  const summary = useMemo(() => {
    if (!trace) return "";
    const status = isRunning
      ? "执行中"
      : isInterrupted
        ? "已中断"
        : isCancelled
          ? "已中止"
          : isError
            ? "执行失败"
            : "已完成";
    return `${status}，${traceItemSummary(trace, items.length)}，${stats.toolCount} 次工具调用，用时 ${elapsed}`;
  }, [elapsed, isCancelled, isError, isInterrupted, isRunning, items.length, stats.toolCount, trace]);

  if (!trace || items.length === 0) return null;

  const fullscreenDialog = fullscreenOpen && typeof document !== "undefined"
    ? createPortal(
      <div
        className="agenthub-backdrop fixed inset-0 z-[1400] flex items-stretch justify-center p-2 md:p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="execution-trace-fullscreen-title"
        onClick={() => setFullscreenOpen(false)}
      >
        <div
          className="agenthub-modal agenthub-modal-pop flex h-full w-full max-w-[1280px] flex-col overflow-hidden rounded-3xl border"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="flex min-w-0 items-center gap-3 border-b px-4 py-3" style={{ borderColor: "var(--ah-border)" }}>
            <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border ${statusFrame(trace.status)}`}>
              {statusIcon(trace.status)}
            </span>
            <div className="min-w-0 flex-1">
              <h2 id="execution-trace-fullscreen-title" className="agenthub-strong truncate text-base font-semibold">执行过程</h2>
              <p className="agenthub-muted mt-0.5 truncate text-xs">{summary}</p>
            </div>
            <TraceBadges items={items} />
            <button
              type="button"
              onClick={() => setFullscreenOpen(false)}
              className="agenthub-icon-button inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
              aria-label="关闭执行过程全屏"
              title="关闭"
            >
              <X size={16} />
            </button>
          </div>
          <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-3 md:p-4">
            <TraceTimeline items={items} isRunning={isRunning} />
          </div>
        </div>
      </div>,
      document.body,
    )
    : null;

  return (
    <section className={`agenthub-execution-panel mt-2 min-w-0 max-w-full ${className}`}>
      <div className="flex w-full min-w-0 items-center gap-2 border-t px-1 pt-2" style={{ borderColor: "var(--ah-border)" }}>
        <button
          type="button"
          onClick={() => setManualOpen(!open)}
          className="agenthub-execution-summary flex min-h-9 min-w-0 flex-1 items-center gap-2 rounded-lg px-2 text-left"
          aria-expanded={open}
        >
        <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${statusFrame(trace.status)}`}>
          {statusIcon(trace.status)}
        </span>
        <span className="agenthub-faint shrink-0 text-xs">执行过程</span>
        <span className="agenthub-muted min-w-0 flex-1 truncate text-xs leading-5">{summary}</span>
        <span className="agenthub-faint shrink-0 rounded-full p-1" aria-hidden="true">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        </button>
        <button
          type="button"
          onClick={() => setFullscreenOpen(true)}
        className="agenthub-icon-button inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
          aria-label="全屏查看执行过程"
          title="全屏查看执行过程"
        >
          <Maximize2 size={14} />
        </button>
      </div>

      {open && (
        <div className="agenthub-execution-details agenthub-soft mt-2 rounded-xl px-3 py-2">
          <div ref={traceScrollRef} className="max-h-96 min-w-0 overflow-y-auto overflow-x-hidden overscroll-contain pr-1">
            <TraceTimeline items={items} isRunning={isRunning} />
          </div>
        </div>
      )}

      {fullscreenDialog}
    </section>
  );
}

function TraceTimeline({ items, isRunning }: { items: ExecutionTraceItem[]; isRunning: boolean }) {
  return (
    <ol className="min-w-0 divide-y" style={{ borderColor: "var(--ah-border)" }}>
      {items.map((item, index) => (
        <TraceRow
          key={item.id}
          item={item}
          isRunning={isRunning && index === items.length - 1}
        />
      ))}
    </ol>
  );
}

function TraceBadges({ items }: { items: ExecutionTraceItem[] }) {
  const stats = traceStats(items);
  return (
    <span className="hidden items-center gap-1.5 sm:inline-flex">
      {stats.toolCount > 0 && <Badge icon={<Hammer size={11} />} text={String(stats.toolCount)} />}
      {stats.commandCount > 0 && <Badge icon={<Terminal size={11} />} text={String(stats.commandCount)} />}
      {stats.errorCount > 0 && <Badge icon={<AlertCircle size={11} />} text={String(stats.errorCount)} tone="error" />}
    </span>
  );
}

function Badge({ icon, text, tone = "default" }: { icon: ReactNode; text: string; tone?: "default" | "error" }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-1 text-[10px] ${
      tone === "error"
        ? "agenthub-status-error"
        : "agenthub-status"
    }`}>
      {icon}
      {text}
    </span>
  );
}

function TraceRow({
  item,
  isRunning,
}: {
  item: ExecutionTraceItem;
  isRunning: boolean;
}) {
  const level = normalizeLevel(item);
  const title = itemTitle(item);
  const detail = item.detail || fallbackDetail(item);
  const showDetail = detail && detail !== title;
  const showRaw = item.raw && item.raw !== detail && item.raw !== item.text;
  const output = item.output || item.stderr || null;

  return (
    <li className="flex min-w-0 gap-2.5 py-2.5 first:pt-1 last:pb-1">
      <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${dotStyle(item, level)} ${
        isRunning ? "agenthub-status-info" : ""
      }`}>
        {kindIcon(item)}
      </span>
      <article className="min-w-0 max-w-full flex-1">
        <header className="flex min-w-0 items-start gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="agenthub-muted text-[10px] font-medium">
                {actionLabel(item)}
              </span>
              {item.status && (
                <span className={`text-[10px] ${statusBadgeStyle(item.status, level)}`}>
                  {statusLabel(item.status)}
                </span>
              )}
              {typeof item.exitCode === "number" && (
                <span className={`text-[10px] ${
                  item.exitCode === 0
                    ? "agenthub-status-success"
                    : "agenthub-status-error"
                }`}>
                  exit {item.exitCode}
                </span>
              )}
              {item.provider && <span className="agenthub-faint text-[10px]">{item.provider}</span>}
              <time className="agenthub-faint text-[10px]">{formatTime(item.timestamp)}</time>
            </div>
            <h4 className="agenthub-strong mt-1 break-words text-xs font-medium leading-5">{title}</h4>
          </div>
        </header>

        {item.target && (
          <div className="agenthub-muted mt-1.5 flex min-w-0 items-center gap-1.5 text-[11px]">
            <FolderOpen size={12} className="agenthub-faint shrink-0" aria-hidden="true" />
            <span className="truncate font-mono">{item.target}</span>
          </div>
        )}

        {item.command && (
          <pre className="agenthub-code-surface mt-2 max-h-36 w-full max-w-full overflow-auto rounded-md border px-2.5 py-2 font-mono text-[11px] leading-5">
            {item.command}
          </pre>
        )}

        {showDetail && (
          <p className="agenthub-muted mt-1.5 whitespace-pre-wrap break-words text-[11px] leading-5">{detail}</p>
        )}

        {output && (
          <div className={`agenthub-code-surface mt-2 rounded-md px-2.5 py-2 ${
            item.stderr
              ? "agenthub-status-error"
              : "agenthub-status"
          }`}>
            <div className="agenthub-muted mb-1 flex items-center gap-1.5 text-[10px] font-medium">
              <Terminal size={11} aria-hidden="true" />
              <span>{item.stderr ? "错误输出" : "输出预览"}</span>
            </div>
            <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words font-mono text-[10.5px] leading-4">
              {output}
            </pre>
          </div>
        )}

        {showRaw && (
          <details className="agenthub-status mt-2 rounded-md px-2 py-1.5 text-[11px]">
            <summary className="cursor-pointer">原始输出</summary>
            <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-4">
              {item.raw}
            </pre>
          </details>
        )}
      </article>
    </li>
  );
}

function compactTraceItems(items: ExecutionTraceItem[]) {
  const result: ExecutionTraceItem[] = [];
  for (const item of items) {
    const title = itemTitle(item);
    const previous = result[result.length - 1];
    if (
      previous
      && previous.kind === item.kind
      && item.kind !== "error"
      && item.kind !== "command"
      && itemTitle(previous) === title
    ) {
      result[result.length - 1] = { ...previous, timestamp: item.timestamp };
      continue;
    }
    result.push(item);
  }
  return result;
}

function traceStats(items: ExecutionTraceItem[]) {
  return items.reduce((acc, item) => {
    if (item.kind === "tool") acc.toolCount += 1;
    if (item.kind === "command") acc.commandCount += 1;
    if (item.kind === "error") acc.errorCount += 1;
    return acc;
  }, { toolCount: 0, commandCount: 0, errorCount: 0 });
}

function traceItemSummary(trace: ExecutionTrace, visibleCount: number) {
  const total = typeof trace.totalItemCount === "number" && Number.isFinite(trace.totalItemCount)
    ? trace.totalItemCount
    : visibleCount;
  if (trace.truncated || total > visibleCount) {
    return `最近 ${visibleCount}/共 ${total} 个步骤`;
  }
  return `${visibleCount} 个步骤`;
}

function traceDuration(trace: ExecutionTrace | null | undefined, items: ExecutionTraceItem[]) {
  const firstItem = items[0]?.timestamp;
  const lastItem = items[items.length - 1]?.timestamp;
  const start = Date.parse(trace?.startedAt || firstItem || "");
  const end = Date.parse(trace?.completedAt || lastItem || "");
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "少于 1 秒";
  const totalSeconds = Math.max(0, Math.round((end - start) / 1000));
  if (totalSeconds < 60) return `${totalSeconds} 秒`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds ? `${minutes} 分 ${seconds} 秒` : `${minutes} 分`;
}

function itemTitle(item?: ExecutionTraceItem) {
  if (!item) return "";
  return item.title || item.summary || item.text || KIND_LABELS[item.kind] || "执行步骤";
}

function fallbackDetail(item: ExecutionTraceItem) {
  if (item.command || item.target) return "";
  return item.text;
}

function actionLabel(item: ExecutionTraceItem) {
  if (item.action && ACTION_LABELS[item.action]) return ACTION_LABELS[item.action];
  return KIND_LABELS[item.kind] ?? "过程";
}

function normalizeLevel(item: ExecutionTraceItem) {
  if (item.kind === "error") return "error";
  if (item.kind === "prompt") return "warning";
  if (item.level === "success" || item.level === "warning" || item.level === "error") return item.level;
  return "info";
}

function kindIcon(item: ExecutionTraceItem) {
  const props = { size: 13, "aria-hidden": true };
  if (item.action === "think") return <SquareActivity {...props} />;
  if (item.kind === "process") return item.action === "complete" ? <CheckCircle2 {...props} /> : <Play {...props} />;
  if (item.kind === "command") return <Terminal {...props} />;
  if (item.kind === "tool") return <Hammer {...props} />;
  if (item.kind === "file") return <FileCode2 {...props} />;
  if (item.kind === "artifact") return <Code2 {...props} />;
  if (item.kind === "prompt") return <TriangleAlert {...props} />;
  if (item.kind === "error") return <AlertCircle {...props} />;
  if (item.action === "search") return <Search {...props} />;
  return <Info {...props} />;
}

function dotStyle(item: ExecutionTraceItem, level: string) {
  if (level === "error") return "border-[color:var(--ah-danger)] text-[color:var(--ah-danger)]";
  if (level === "warning") return "border-[color:var(--ah-warning)] text-[color:var(--ah-warning)]";
  if (item.kind === "process" && item.action === "complete") return "border-[color:var(--ah-success)] text-[color:var(--ah-success)]";
  return "border-[color:var(--ah-border-strong)] text-[color:var(--ah-text-strong)]";
}

function statusIcon(status: ExecutionTrace["status"]) {
  const props = { size: 14, "aria-hidden": true };
  if (status === "running") return <Clock3 {...props} className="animate-pulse" />;
  if (status === "error") return <AlertCircle {...props} />;
  if (status === "cancelled") return <XCircle {...props} />;
  if (status === "interrupted") return <TriangleAlert {...props} />;
  return <CheckCircle2 {...props} />;
}

function statusFrame(status: ExecutionTrace["status"]) {
  if (status === "running") return "agenthub-status-info";
  if (status === "error") return "agenthub-status-error";
  if (status === "cancelled" || status === "interrupted") return "agenthub-status-warning";
  return "agenthub-status-success";
}

function formatTime(value: string) {
  return formatChinaTime(value, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function statusLabel(status: string) {
  return {
    in_progress: "进行中",
    running: "进行中",
    completed: "已完成",
    success: "已完成",
    cancelled: "已中止",
    failed: "失败",
    error: "失败",
  }[status] ?? status;
}

function statusBadgeStyle(status: string, level: string) {
  if (level === "error" || status === "failed" || status === "error") {
    return "agenthub-status-error";
  }
  if (status === "completed" || status === "success") {
    return "agenthub-status-success";
  }
  if (status === "cancelled") {
    return "agenthub-status-warning";
  }
  return "agenthub-status-info";
}
