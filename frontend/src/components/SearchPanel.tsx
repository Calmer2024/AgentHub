import { useEffect, useMemo, useState } from "react";
import { searchMessages } from "../api/client";
import type { Message } from "../types";

interface Props {
  sessionId: string;
  open: boolean;
  onClose: () => void;
  onJump: (sessionId: string, messageId: string) => void;
}

export function SearchPanel({ sessionId, open, onClose, onJump }: Props) {
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

  return (
    <div className={`absolute inset-y-0 right-0 z-30 w-full max-w-md border-l border-slate-200 bg-white shadow-xl transition-all duration-200 ${visible}`}>
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
          <input
            autoFocus={open}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索当前会话"
            className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
          >
            关闭
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {loading && <div className="px-3 py-4 text-sm text-slate-500">搜索中...</div>}
          {error && <div className="px-3 py-4 text-sm text-red-600">{error}</div>}
          {showEmpty && <div className="px-3 py-4 text-sm text-slate-500">未找到匹配消息</div>}
          {!query.trim() && (
            <div className="px-3 py-4 text-sm text-slate-500">输入关键词搜索历史消息</div>
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
                className="w-full rounded-lg border border-slate-200 p-3 text-left hover:border-blue-300 hover:bg-blue-50"
              >
                <div className="mb-1 flex items-center gap-2 text-xs text-slate-500">
                  <span>{message.role === "user" ? "用户" : message.agentName ?? message.sourceName ?? "AI"}</span>
                  <span>{formatTime(message.createdAt)}</span>
                </div>
                <Highlight text={message.highlight || message.content} />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Highlight({ text }: { text: string }) {
  const parts = useMemo(() => splitHighlight(text), [text]);
  return (
    <p className="max-h-16 overflow-hidden text-sm leading-5 text-slate-700">
      {parts.map((part, idx) => (
        part.marked
          ? <mark key={idx} className="rounded bg-yellow-200 px-0.5">{part.text}</mark>
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
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}
