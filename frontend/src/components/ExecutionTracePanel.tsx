import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertCircle, CheckCircle2, ChevronDown, ChevronRight,
  Clock3, Code2, FileCode2, FolderOpen, Hammer, Info, Play,
  Search, SquareActivity, Terminal, TriangleAlert, XCircle,
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

const LEVEL_STYLE: Record<string, string> = {
  info: "border-sky-300/20 bg-sky-300/10 text-sky-100",
  success: "border-emerald-300/25 bg-emerald-300/10 text-emerald-100",
  warning: "border-amber-300/30 bg-amber-300/10 text-amber-100",
  error: "border-rose-300/35 bg-rose-300/10 text-rose-100",
};

export function ExecutionTracePanel({ trace, className = "" }: Props) {
  const items = useMemo(() => compactTraceItems(trace?.items ?? []), [trace?.items]);
  const traceScrollRef = useRef<HTMLDivElement | null>(null);
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);
  const isRunning = trace?.status === "running";
  const isError = trace?.status === "error";
  const isCancelled = trace?.status === "cancelled";
  const open = manualOpen ?? isRunning;
  const latest = items[items.length - 1];
  const current = isRunning ? activeTraceItem(items) ?? latest : latest;

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

  const stats = useMemo(() => traceStats(items), [items]);
  const summary = useMemo(() => {
    if (!trace) return "";
    if (isRunning) return itemTitle(current) || "正在执行";
    if (isCancelled) return "本次运行已中止";
    if (isError) return itemTitle(latest) || "执行遇到错误";
    return `${items.length} 步，${stats.toolCount} 次工具调用，${stats.commandCount} 条命令`;
  }, [current, isCancelled, isError, isRunning, items.length, latest, stats.commandCount, stats.toolCount, trace]);

  if (!trace || items.length === 0) return null;

  return (
    <section className={`mt-3 overflow-hidden rounded-[14px] border border-white/10 bg-[#151619] text-zinc-100 shadow-[0_12px_32px_rgba(0,0,0,0.18)] ${className}`}>
      <button
        type="button"
        onClick={() => setManualOpen(!open)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition hover:bg-white/[0.04]"
      >
        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${statusFrame(trace.status)}`}>
          {statusIcon(trace.status)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2 text-xs font-semibold text-zinc-100">
            <span>执行过程</span>
            {trace.agentName && <span className="font-normal text-zinc-500">{trace.agentName}</span>}
            {isRunning && (
              <span className="inline-flex items-center gap-1 rounded-md border border-sky-300/25 bg-sky-300/10 px-1.5 py-0.5 text-[10px] text-sky-100">
                <SquareActivity size={10} className="animate-pulse" aria-hidden="true" />
                运行中
              </span>
            )}
          </span>
          <span className="mt-0.5 block truncate text-[11px] leading-5 text-zinc-400">{summary}</span>
        </span>
        <TraceBadges items={items} />
        <span className="rounded-md border border-white/10 p-1 text-zinc-300" aria-hidden="true">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>

      {open && (
        <div className="border-t border-white/10 px-3 py-3">
          <div ref={traceScrollRef} className="max-h-96 overflow-y-auto overscroll-contain pr-1">
            <ol className="relative space-y-2 before:absolute before:left-[14px] before:top-2 before:h-[calc(100%-1rem)] before:w-px before:bg-white/10">
              {items.map((item, index) => (
                <TraceRow
                  key={item.id}
                  item={item}
                  isLast={index === items.length - 1}
                  isRunning={isRunning && index === items.length - 1}
                />
              ))}
            </ol>
          </div>
        </div>
      )}
    </section>
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
        ? "border-rose-300/25 bg-rose-300/10 text-rose-100"
        : "border-white/10 bg-white/[0.04] text-zinc-300"
    }`}>
      {icon}
      {text}
    </span>
  );
}

function TraceRow({
  item,
  isLast,
  isRunning,
}: {
  item: ExecutionTraceItem;
  isLast: boolean;
  isRunning: boolean;
}) {
  const level = normalizeLevel(item);
  const title = itemTitle(item);
  const detail = item.detail || fallbackDetail(item);
  const showDetail = detail && detail !== title;
  const showRaw = item.raw && item.raw !== detail && item.raw !== item.text;
  const output = item.output || item.stderr || null;

  return (
    <li className="relative pl-8">
      <span className={`absolute left-0 top-1 flex h-7 w-7 items-center justify-center rounded-full border bg-[#151619] ${dotStyle(item, level)} ${
        isRunning ? "shadow-[0_0_0_4px_rgba(56,189,248,0.08)]" : ""
      }`}>
        {kindIcon(item)}
      </span>
      <article className={`rounded-[10px] border px-3 py-2.5 ${LEVEL_STYLE[level] ?? LEVEL_STYLE.info} ${isLast ? "shadow-[0_0_0_1px_rgba(255,255,255,0.02)]" : ""}`}>
        <header className="flex min-w-0 items-start gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="rounded-md border border-white/10 bg-black/10 px-1.5 py-0.5 text-[10px] font-medium text-zinc-300">
                {actionLabel(item)}
              </span>
              {item.status && (
                <span className={`rounded-md border px-1.5 py-0.5 text-[10px] ${statusBadgeStyle(item.status, level)}`}>
                  {statusLabel(item.status)}
                </span>
              )}
              {typeof item.exitCode === "number" && (
                <span className={`rounded-md border px-1.5 py-0.5 text-[10px] ${
                  item.exitCode === 0
                    ? "border-emerald-300/20 bg-emerald-300/10 text-emerald-100"
                    : "border-rose-300/25 bg-rose-300/10 text-rose-100"
                }`}>
                  exit {item.exitCode}
                </span>
              )}
              {item.provider && <span className="text-[10px] text-zinc-500">{item.provider}</span>}
              <time className="text-[10px] text-zinc-500">{formatTime(item.timestamp)}</time>
            </div>
            <h4 className="mt-1 break-words text-[12px] font-semibold leading-5 text-zinc-100">{title}</h4>
          </div>
        </header>

        {item.target && (
          <div className="mt-2 flex min-w-0 items-center gap-1.5 rounded-md border border-white/10 bg-black/10 px-2 py-1 text-[11px] text-zinc-300">
            <FolderOpen size={12} className="shrink-0 text-zinc-500" aria-hidden="true" />
            <span className="truncate font-mono">{item.target}</span>
          </div>
        )}

        {item.command && (
          <pre className="mt-2 overflow-x-auto rounded-md border border-white/10 bg-[#0d0f12] px-2.5 py-2 font-mono text-[11px] leading-5 text-zinc-200">
            {item.command}
          </pre>
        )}

        {showDetail && (
          <p className="mt-2 whitespace-pre-wrap break-words text-[11px] leading-5 text-zinc-300">{detail}</p>
        )}

        {output && (
          <div className={`mt-2 rounded-md border px-2.5 py-2 ${
            item.stderr
              ? "border-rose-300/20 bg-rose-950/20"
              : "border-emerald-300/15 bg-emerald-950/10"
          }`}>
            <div className="mb-1 flex items-center gap-1.5 text-[10px] font-medium text-zinc-400">
              <Terminal size={11} aria-hidden="true" />
              <span>{item.stderr ? "错误输出" : "输出预览"}</span>
            </div>
            <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words font-mono text-[10.5px] leading-4 text-zinc-200">
              {output}
            </pre>
          </div>
        )}

        {showRaw && (
          <details className="mt-2 rounded-md border border-white/10 bg-black/10 px-2 py-1.5 text-[11px] text-zinc-400">
            <summary className="cursor-pointer text-zinc-300">原始输出</summary>
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

function activeTraceItem(items: ExecutionTraceItem[]) {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.kind === "process" && item.action === "complete") continue;
    return item;
  }
  return null;
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
  if (level === "error") return "border-rose-300/40 text-rose-100";
  if (level === "warning") return "border-amber-300/40 text-amber-100";
  if (item.kind === "process" && item.action === "complete") return "border-emerald-300/35 text-emerald-100";
  return "border-sky-300/25 text-sky-100";
}

function statusIcon(status: ExecutionTrace["status"]) {
  const props = { size: 14, "aria-hidden": true };
  if (status === "running") return <Clock3 {...props} className="animate-pulse" />;
  if (status === "error") return <AlertCircle {...props} />;
  if (status === "cancelled") return <XCircle {...props} />;
  return <CheckCircle2 {...props} />;
}

function statusFrame(status: ExecutionTrace["status"]) {
  if (status === "running") return "border-sky-300/30 bg-sky-300/10 text-sky-100";
  if (status === "error") return "border-rose-300/35 bg-rose-300/10 text-rose-100";
  if (status === "cancelled") return "border-amber-300/35 bg-amber-300/10 text-amber-100";
  return "border-emerald-300/30 bg-emerald-300/10 text-emerald-100";
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
    return "border-rose-300/25 bg-rose-300/10 text-rose-100";
  }
  if (status === "completed" || status === "success") {
    return "border-emerald-300/20 bg-emerald-300/10 text-emerald-100";
  }
  if (status === "cancelled") {
    return "border-amber-300/25 bg-amber-300/10 text-amber-100";
  }
  return "border-sky-300/20 bg-sky-300/10 text-sky-100";
}
