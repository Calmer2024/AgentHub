import type { Message, ReplyReference } from "../types";

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
      className={`border-l-2 border-blue-400 bg-blue-50/80 text-slate-700 ${
        compact ? "px-3 py-2 text-xs rounded-md mb-2" : "px-4 py-3 text-sm rounded-lg"
      }`}
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => messageId && onJump?.(messageId)}
          disabled={!message || !onJump}
          className="font-medium text-blue-700 disabled:text-slate-500 disabled:cursor-default"
        >
          回复 {label}
        </button>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="ml-auto text-slate-400 hover:text-slate-700"
            aria-label="取消引用"
            title="取消引用"
          >
            x
          </button>
        )}
      </div>
      <div className="mt-1 max-h-10 overflow-hidden break-words text-slate-600">
        {content || "..."}
      </div>
    </div>
  );
}
