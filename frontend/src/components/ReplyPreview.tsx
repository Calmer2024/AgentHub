import type { Message, ReplyReference } from "../types";
import { Quote, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  message: Message | ReplyReference | null;
  compact?: boolean;
  currentUserName?: string;
  onClear?: () => void;
  onJump?: (messageId: string) => void;
}

export function ReplyPreview({ message, compact = false, currentUserName = "你", onClear, onJump }: Props) {
  const missing = !message;
  const label = missing
    ? "原消息已删除"
    : message.role === "user"
      ? message.sourceName || currentUserName
      : message.agentName ?? message.sourceName ?? "AI";
  const content = missing ? "原消息已删除" : message.content;
  const messageId = message?.id;

  return (
    <div
      className={`agenthub-reference-card border-l-2 ${
        compact ? "px-3 py-2 text-xs rounded-xl mb-2" : "px-4 py-3 text-sm rounded-2xl"
      }`}
      style={{ borderLeftColor: "var(--ah-accent)" }}
    >
      <div className="flex items-center gap-2">
        <Quote size={compact ? 13 : 15} className="agenthub-accent shrink-0" />
        <button
          type="button"
          onClick={() => messageId && onJump?.(messageId)}
          disabled={!message || !onJump}
          className="agenthub-accent font-medium disabled:cursor-default disabled:opacity-50"
        >
          {label}
        </button>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="agenthub-icon-button ml-auto inline-flex h-7 w-7 items-center justify-center rounded-full"
            aria-label="取消引用"
            title="取消引用"
          >
            <X size={14} />
          </button>
        )}
      </div>
      <div className="agenthub-reply-markdown mt-1 max-h-16 overflow-hidden break-words">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content || "..."}
        </ReactMarkdown>
      </div>
    </div>
  );
}
