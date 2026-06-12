import { ChevronDown, Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface MenuSelectOption<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
}

interface Props<T extends string> {
  value: T;
  options: Array<MenuSelectOption<T>>;
  onChange: (value: T) => void;
  ariaLabel: string;
  disabled?: boolean;
  className?: string;
}

export function MenuSelect<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  disabled = false,
  className = "",
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div ref={ref} className={`relative min-w-0 ${className}`}>
      <button
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
        className="agenthub-composer flex h-full min-h-9 w-full items-center justify-between gap-2 rounded-lg border px-3 text-left text-sm outline-none disabled:cursor-not-allowed disabled:opacity-60"
      >
        <span className="min-w-0 truncate">{selected?.label ?? ""}</span>
        <ChevronDown size={14} className="agenthub-muted shrink-0" />
      </button>
      {open && (
        <div
          role="listbox"
          className="agenthub-menu absolute left-0 right-0 top-[calc(100%+6px)] z-[80] max-h-56 overflow-y-auto rounded-xl border p-1"
        >
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={option.value === value}
              disabled={option.disabled}
              onClick={() => {
                if (option.disabled) return;
                onChange(option.value);
                setOpen(false);
              }}
              className="agenthub-nav-idle flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-sm disabled:cursor-not-allowed disabled:opacity-45"
            >
              <span className="min-w-0 truncate">{option.label}</span>
              {option.value === value && <Check size={14} className="agenthub-muted shrink-0" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
