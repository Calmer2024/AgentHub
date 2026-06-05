import type { Message, ReplyReference } from "../types";
import { Quote, X } from "lucide-react";

interface Props {
  message: Message | ReplyReference | null;
  compact?: boolean;
  onClear?: () => void;
  onJump?: (messageId: string) => void;
}

export function ReplyPreview({ message, compact = false, onClear, onJump }: Props) {
  const missing = !message;
  const label = missing
    ? "原消息已删除"
    : message.role === "user"
      ? "用户"
      : message.agentName ?? message.sourceName ?? "AI";
  const content = missing ? "原消息已删除" : message.content;
  const messageId = message?.id;

  return (
    <div
      className={`border-l-2 border-sky-400 bg-white/[0.06] text-[#d8d8df] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] ${
        compact ? "px-3 py-2 text-xs rounded-xl mb-2" : "px-4 py-3 text-sm rounded-2xl"
      }`}
    >
      <div className="flex items-center gap-2">
        <Quote size={compact ? 13 : 15} className="shrink-0 text-sky-300" />
        <button
          type="button"
          onClick={() => messageId && onJump?.(messageId)}
          disabled={!message || !onJump}
          className="font-medium text-sky-200 disabled:text-slate-500 disabled:cursor-default"
        >
          {label}
        </button>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="ml-auto inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-400 hover:bg-white/10 hover:text-white"
            aria-label="取消引用"
            title="取消引用"
          >
            <X size={14} />
          </button>
        )}
      </div>
      <div className="mt-1 max-h-10 overflow-hidden break-words text-[#9aa5b1]">
        {content || "..."}
      </div>
    </div>
  );
}
