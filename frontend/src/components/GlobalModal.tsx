import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

interface Props {
  title: string;
  subtitle?: string;
  ariaLabel?: string;
  icon?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  onClose: () => void;
  zIndexClass?: string;
  bodyClassName?: string;
  panelClassName?: string;
  closeLabel?: string;
  closeDisabled?: boolean;
}

export function GlobalModal({
  title,
  subtitle,
  ariaLabel,
  icon,
  actions,
  footer,
  children,
  onClose,
  zIndexClass = "z-[1200]",
  bodyClassName = "p-4 md:p-5",
  panelClassName = "max-w-3xl",
  closeLabel = "关闭",
  closeDisabled = false,
}: Props) {
  void icon;
  useEffect(() => {
    if (typeof document === "undefined") return;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !closeDisabled) onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [closeDisabled, onClose]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className={`agenthub-backdrop fixed inset-0 ${zIndexClass} flex min-w-0 items-center justify-center px-3 py-4 md:px-6`}
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel ?? title}
      onClick={() => {
        if (!closeDisabled) onClose();
      }}
    >
      <section
        className={`agenthub-global-modal agenthub-modal agenthub-modal-pop flex w-full flex-col overflow-hidden rounded-2xl border ${panelClassName}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="agenthub-header flex shrink-0 items-center justify-between gap-3 border-b px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="min-w-0">
              <h2 className="agenthub-strong truncate text-base font-semibold">{title}</h2>
              {subtitle && <p className="agenthub-muted mt-0.5 truncate text-xs">{subtitle}</p>}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {actions}
            <button
              type="button"
              onClick={onClose}
              disabled={closeDisabled}
              className="agenthub-icon-button inline-flex h-9 w-9 items-center justify-center rounded-[10px] disabled:cursor-not-allowed disabled:opacity-50"
              aria-label={closeLabel}
              title={closeLabel}
            >
              <X size={16} />
            </button>
          </div>
        </header>
        <div className={`min-h-0 flex-1 overflow-y-auto ${bodyClassName}`}>
          {children}
        </div>
        {footer && (
          <footer className="agenthub-header shrink-0 border-t px-4 py-2.5">
            {footer}
          </footer>
        )}
      </section>
    </div>,
    document.body,
  );
}
