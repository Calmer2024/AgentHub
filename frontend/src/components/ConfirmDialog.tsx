import { AlertTriangle, Loader2, X } from "lucide-react";

interface Props {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  danger?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy = false,
  danger = true,
  onCancel,
  onConfirm,
}: Props) {
  if (!open) return null;

  return (
    <div className="agenthub-backdrop fixed inset-0 z-[1500] flex items-center justify-center px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="agenthub-confirm-title"
        className="agenthub-modal agenthub-modal-pop w-full max-w-sm rounded-3xl border p-4"
      >
        <div className="flex items-start gap-3">
          <span className={`${danger ? "agenthub-status-error" : "agenthub-status-warning"} flex h-10 w-10 shrink-0 items-center justify-center rounded-full border`}>
            <AlertTriangle size={18} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="agenthub-confirm-title" className="agenthub-strong text-base font-semibold">{title}</h2>
            <p className="agenthub-muted mt-1 whitespace-pre-wrap text-xs leading-5">{description}</p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-full disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="关闭确认"
            title="关闭"
          >
            <X size={14} />
          </button>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="agenthub-icon-button h-10 rounded-full px-4 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`${danger ? "agenthub-danger-button" : "agenthub-primary-button"} inline-flex h-10 items-center gap-2 rounded-full px-5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {busy && <Loader2 size={15} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
