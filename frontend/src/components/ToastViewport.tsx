import { useEffect } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle, type LucideIcon } from "lucide-react";
import { useToastStore, type ToastItem, type ToastKind } from "../stores/toastStore";

const TOAST_ICON: Record<ToastKind, LucideIcon> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
};

export function ToastViewport() {
  const toasts = useToastStore((state) => state.toasts);

  return (
    <div className="agenthub-toast-viewport fixed right-4 top-4 z-[1600] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
      {toasts.map((toast) => (
        <ToastCard key={toast.id} toast={toast} />
      ))}
    </div>
  );
}

function ToastCard({ toast }: { toast: ToastItem }) {
  const removeToast = useToastStore((state) => state.removeToast);
  const Icon = TOAST_ICON[toast.kind];

  useEffect(() => {
    if (toast.durationMs <= 0) return undefined;
    const timer = window.setTimeout(() => removeToast(toast.id), toast.durationMs);
    return () => window.clearTimeout(timer);
  }, [removeToast, toast.durationMs, toast.id]);

  return (
    <div className={`agenthub-toast agenthub-toast-${toast.kind} flex items-start gap-3 rounded-2xl border px-3 py-3 shadow-lg`}>
      <span className="agenthub-toast-icon mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full">
        <Icon size={15} aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="agenthub-strong block text-sm font-semibold">{toast.title}</span>
        {toast.description && (
          <span className="agenthub-muted mt-0.5 block text-xs leading-5">{toast.description}</span>
        )}
      </span>
      <button
        type="button"
        onClick={() => removeToast(toast.id)}
        className="agenthub-toast-close inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
        aria-label="关闭提示"
        title="关闭"
      >
        <X size={14} />
      </button>
    </div>
  );
}
