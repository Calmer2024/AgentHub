import type { Message } from "../types";
import { CheckSquare, Copy, Forward, Pin, PinOff, Quote, RefreshCw } from "lucide-react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

interface Props {
  message: Message;
  open: boolean;
  position: { x: number; y: number } | null;
  onReply: (message: Message) => void;
  onRegenerate: (message: Message) => void;
  onTogglePin: (message: Message) => void;
  onForward: (message: Message) => void;
  onMultiSelect: (message: Message) => void;
  onCopy: (content: string) => void;
  onClose: () => void;
}

export function MessageActions({
  message, open, position, onReply, onRegenerate, onTogglePin,
  onForward, onMultiSelect, onCopy, onClose,
}: Props) {
  const canRegenerate = message.role === "assistant" && !message.isCollaborating;
  if (!open || !position || typeof document === "undefined") return null;

  const run = (action: () => void) => {
    action();
    onClose();
  };

  const menu = (
    <div
      className="agenthub-menu agenthub-popover fixed z-[1200] w-44 rounded-2xl border p-1.5"
      style={{ left: position.x, top: position.y }}
      role="menu"
      onContextMenu={(event) => event.preventDefault()}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <MenuAction icon={<Quote size={14} />} label="引用回复" onClick={() => run(() => onReply(message))} />
      {canRegenerate && (
        <MenuAction icon={<RefreshCw size={14} />} label="重新生成" onClick={() => run(() => onRegenerate(message))} />
      )}
      <MenuAction
        icon={message.isPinned ? <PinOff size={14} /> : <Pin size={14} />}
        label={message.isPinned ? "取消 Pin" : "Pin 消息"}
        onClick={() => run(() => onTogglePin(message))}
      />
      <MenuAction icon={<Forward size={14} />} label="转发" onClick={() => run(() => onForward(message))} />
      <MenuAction icon={<CheckSquare size={14} />} label="多选" onClick={() => run(() => onMultiSelect(message))} />
      <MenuAction icon={<Copy size={14} />} label="复制" onClick={() => run(() => onCopy(message.content))} />
    </div>
  );

  return createPortal(menu, document.body);
}

function MenuAction({
  icon,
  label,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="agenthub-nav-idle flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition active:translate-y-px"
    >
      <span className="agenthub-muted inline-flex h-5 w-5 items-center justify-center">{icon}</span>
      <span>{label}</span>
    </button>
  );
}
