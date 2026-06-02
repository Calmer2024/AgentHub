import type { Message } from "../types";

interface Props {
  message: Message;
  onReply: (message: Message) => void;
  onRegenerate: (message: Message) => void;
  onTogglePin: (message: Message) => void;
  onCopy: (content: string) => void;
}

export function MessageActions({
  message, onReply, onRegenerate, onTogglePin, onCopy,
}: Props) {
  const canRegenerate = message.role === "assistant" && !message.isCollaborating;

  return (
    <div className="absolute -top-3 right-2 hidden items-center gap-1 rounded-md border border-slate-200 bg-white px-1 py-1 shadow-sm group-hover:flex">
      <button
        type="button"
        onClick={() => onReply(message)}
        className="px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded"
        title="引用回复"
      >
        引用
      </button>
      {canRegenerate && (
        <button
          type="button"
          onClick={() => onRegenerate(message)}
          className="px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded"
          title="重新生成"
        >
          重生成
        </button>
      )}
      <button
        type="button"
        onClick={() => onTogglePin(message)}
        className="px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded"
        title={message.isPinned ? "取消 Pin" : "Pin 消息"}
      >
        {message.isPinned ? "取消Pin" : "Pin"}
      </button>
      <button
        type="button"
        onClick={() => onCopy(message.content)}
        className="px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded"
        title="复制"
      >
        复制
      </button>
    </div>
  );
}
