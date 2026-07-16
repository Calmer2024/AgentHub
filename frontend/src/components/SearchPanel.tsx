import { useEffect, useMemo, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { searchMessages } from "../api/client";
import type { CurrentUser, Message } from "../types";
import { AgentAvatar } from "./AgentAvatar";
import { formatChinaDateTime } from "../utils/time";

interface Props {
  sessionId: string;
  open: boolean;
  currentUser?: CurrentUser | null;
  onClose: () => void;
  onJump: (sessionId: string, messageId: string) => void;
}

export function SearchPanel({ sessionId, open, currentUser, onClose, onJump }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const id = window.setTimeout(async () => {
      const q = query.trim();
      if (!q) {
        setResults([]);
        setError(null);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        setResults(await searchMessages(sessionId, q));
      } catch {
        setError("搜索失败，请稍后重试");
      } finally {
        setLoading(false);
      }
    }, 180);
    return () => window.clearTimeout(id);
  }, [open, query, sessionId]);

  const visible = open ? "translate-x-0 opacity-100" : "translate-x-full opacity-0 pointer-events-none";
  const showEmpty = query.trim() && !loading && !error && results.length === 0;
  const currentUserName = currentUser?.displayName || currentUser?.username || currentUser?.email || "你";

  return (
    <div className={`agenthub-modal absolute inset-y-0 right-0 z-30 w-full max-w-md border-l transition-all duration-200 ${visible}`}>
      <div className="flex h-full flex-col">
        <div className="agenthub-header border-b px-4 py-3">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="agenthub-strong text-sm font-semibold">搜索消息</h2>
              <p className="agenthub-muted mt-0.5 text-xs">当前会话</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="agenthub-icon-button inline-flex h-9 w-9 items-center justify-center rounded-full"
              aria-label="关闭搜索"
              title="关闭搜索"
            >
              <X size={16} />
            </button>
          </div>
          <div className="agenthub-composer agenthub-focus-ring flex min-w-0 flex-1 items-center gap-2 rounded-full border px-3 py-2">
            <Search size={15} className="agenthub-muted shrink-0" />
            <input
              autoFocus={open}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索当前会话"
              className="agenthub-textarea min-w-0 flex-1 bg-transparent text-sm outline-none"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {loading && (
            <div className="agenthub-muted flex items-center gap-2 rounded-2xl px-3 py-4 text-sm">
              <Loader2 size={15} className="animate-spin" />
              搜索中
            </div>
          )}
          {error && <div className="px-3 py-4 text-sm text-[color:var(--ah-danger)]">{error}</div>}
          {showEmpty && <div className="agenthub-muted px-3 py-4 text-sm">未找到匹配消息</div>}
          {!query.trim() && (
            <div className="agenthub-muted px-3 py-4 text-sm">输入关键词搜索历史消息</div>
          )}
          <div className="space-y-2">
            {results.map((message) => (
              <button
                key={message.id}
                type="button"
                onClick={() => {
                  onJump(message.sessionId, message.id);
                  onClose();
                }}
                className="agenthub-soft flex w-full gap-3 rounded-2xl p-3 text-left transition"
              >
                <AgentAvatar
                  kind={message.role === "user" ? "user" : "agent"}
                  name={messageLabel(message, currentUserName)}
                  size="sm"
                />
                <span className="min-w-0 flex-1">
                  <span className="agenthub-muted mb-1 flex items-center gap-2 text-xs">
                    <span className="truncate">{messageLabel(message, currentUserName)}</span>
                    <span className="shrink-0">{formatTime(message.createdAt)}</span>
                  </span>
                  <Highlight text={message.highlight || message.content} />
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function messageLabel(message: Message, currentUserName: string) {
  return message.role === "user"
    ? message.sourceName || currentUserName
    : message.agentName ?? message.sourceName ?? "AI";
}

function Highlight({ text }: { text: string }) {
  const parts = useMemo(() => splitHighlight(text), [text]);
  return (
    <p className="max-h-16 overflow-hidden text-sm leading-5">
      {parts.map((part, idx) => (
        part.marked
          ? <mark key={idx} className="rounded bg-[color:var(--ah-highlight-bg)] px-0.5 text-[color:var(--ah-highlight-text)]">{part.text}</mark>
          : <span key={idx}>{part.text}</span>
      ))}
    </p>
  );
}

function splitHighlight(text: string): Array<{ text: string; marked: boolean }> {
  const result: Array<{ text: string; marked: boolean }> = [];
  let rest = text;
  while (rest.includes("<mark>")) {
    const start = rest.indexOf("<mark>");
    const end = rest.indexOf("</mark>", start);
    if (start > 0) result.push({ text: rest.slice(0, start), marked: false });
    if (end < 0) {
      result.push({ text: rest.slice(start), marked: false });
      return result;
    }
    result.push({ text: rest.slice(start + 6, end), marked: true });
    rest = rest.slice(end + 7);
  }
  if (rest) result.push({ text: rest, marked: false });
  return result;
}

function formatTime(value: string): string {
  return formatChinaDateTime(value, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
