import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, Loader2, OctagonAlert, RefreshCw } from "lucide-react";
import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import type { SystemHealthItem, SystemHealthRead } from "../types";

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

function detailItems(health: SystemHealthRead): SystemHealthItem[] {
  return health.items.filter((item) => item.severity !== "info" || item.status !== "ok");
}

function metadataLines(item: SystemHealthItem) {
  if (!item.metadata) return [];
  return Object.entries(item.metadata).map(([key, value]) => `${key}: ${value ?? "null"}`);
}

export function HealthCheckCard({ health, loading, compact, onRefresh }: Props) {
  const [expanded, setExpanded] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const [floatingStyle, setFloatingStyle] = useState<CSSProperties>({});
  const tone = health?.overall === "ok"
    ? "agenthub-status-success"
    : health?.overall === "error"
      ? "agenthub-status-error"
      : "agenthub-status-warning";
  const items = health && health.overall !== "ok" ? detailItems(health) : [];
  const canExpand = items.length > 0;

  useLayoutEffect(() => {
    if (!compact || !expanded || !canExpand) return;
    if (typeof window === "undefined") return;

    const updatePosition = () => {
      const rect = cardRef.current?.getBoundingClientRect();
      if (!rect) return;
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      const width = Math.min(360, Math.max(280, viewportWidth - 24));
      const left = Math.min(
        Math.max(12, rect.right - width),
        Math.max(12, viewportWidth - width - 12),
      );
      const top = Math.min(rect.bottom + 8, Math.max(12, viewportHeight - 120));
      setFloatingStyle({
        left,
        top,
        width,
        maxWidth: "calc(100vw - 1.5rem)",
        maxHeight: `min(70dvh, ${Math.max(220, viewportHeight - top - 16)}px)`,
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [canExpand, compact, expanded]);

  const detailPanel = expanded && canExpand ? (
    <div
      className={`space-y-2 px-3 py-2 text-current ${
        compact
          ? `fixed z-[1600] overflow-y-auto rounded-lg border shadow-xl ${tone}`
          : "border-t"
      }`}
      style={{ borderColor: "var(--ah-border)", ...(compact ? floatingStyle : {}) }}
      data-testid="health-check-details"
    >
      {items.map((item) => {
        const metadata = metadataLines(item);
        return (
          <div key={item.key} className="rounded-md border border-current/10 px-2.5 py-2">
            <div className="flex min-w-0 items-center justify-between gap-2 text-[11px] font-medium">
              <span className="truncate">{item.label}</span>
              <span className="shrink-0 uppercase text-current/65">{item.status}</span>
            </div>
            <div className="mt-1 whitespace-pre-wrap break-words text-[11px] leading-relaxed text-current/85">
              {item.detail}
            </div>
            {metadata.length > 0 && (
              <div className="mt-2 space-y-0.5 rounded bg-black/5 px-2 py-1 text-[10px] leading-4 text-current/70 dark:bg-white/10">
                {metadata.map((line) => (
                  <div key={line} className="break-words">{line}</div>
                ))}
              </div>
            )}
            {item.action && (
              <div className="mt-1 text-[10px] text-current/65">
                建议操作：{item.action.label}
              </div>
            )}
          </div>
        );
      })}
    </div>
  ) : null;

  return (
    <div ref={cardRef} className={`relative rounded-lg border ${tone}`}>
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-medium">
        {loading ? <Loader2 size={15} className="animate-spin" /> : iconFor(health?.overall)}
        <span className="min-w-[5rem] flex-1 whitespace-nowrap">{textFor(health)}</span>
        {canExpand && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full hover:bg-[color:var(--ah-accent-soft)]"
            aria-label={expanded ? "收起环境体检详情" : "展开环境体检详情"}
            title={expanded ? "收起详情" : "展开详情"}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
        )}
        <button
          type="button"
          onClick={onRefresh}
          className="inline-flex h-7 w-7 items-center justify-center rounded-full hover:bg-[color:var(--ah-accent-soft)]"
          aria-label="刷新环境体检"
          title="刷新环境体检"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      {compact && detailPanel && typeof document !== "undefined"
        ? createPortal(detailPanel, document.body)
        : detailPanel}
    </div>
  );
}
