import type { Message } from "../types";
import { Copy, Pin, PinOff, Quote, RefreshCw } from "lucide-react";

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
    <div className={`agenthub-menu absolute -top-3 hidden items-center gap-1 rounded-full border px-1 py-1 group-hover:flex ${
      message.role === "user" ? "left-2" : "right-2"
    }`}>
      <button
        type="button"
        onClick={() => onReply(message)}
        className="rounded-full p-1.5 agenthub-muted transition hover:bg-[color:var(--ah-accent-soft)] hover:text-[color:var(--ah-text-strong)] active:translate-y-px"
        aria-label="引用回复"
        title="引用回复"
      >
        <Quote size={14} />
      </button>
      {canRegenerate && (
        <button
          type="button"
          onClick={() => onRegenerate(message)}
          className="rounded-full p-1.5 agenthub-muted transition hover:bg-[color:var(--ah-accent-soft)] hover:text-[color:var(--ah-text-strong)] active:translate-y-px"
          aria-label="重新生成"
          title="重新生成"
        >
          <RefreshCw size={14} />
        </button>
      )}
      <button
        type="button"
        onClick={() => onTogglePin(message)}
        className="rounded-full p-1.5 agenthub-muted transition hover:bg-[color:var(--ah-accent-soft)] hover:text-[color:var(--ah-text-strong)] active:translate-y-px"
        aria-label={message.isPinned ? "取消 Pin" : "Pin 消息"}
        title={message.isPinned ? "取消 Pin" : "Pin 消息"}
      >
        {message.isPinned ? <PinOff size={14} /> : <Pin size={14} />}
      </button>
      <button
        type="button"
        onClick={() => onCopy(message.content)}
        className="rounded-full p-1.5 agenthub-muted transition hover:bg-[color:var(--ah-accent-soft)] hover:text-[color:var(--ah-text-strong)] active:translate-y-px"
        aria-label="复制"
        title="复制"
      >
        <Copy size={14} />
      </button>
    </div>
  );
}
