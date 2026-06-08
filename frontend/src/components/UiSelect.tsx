import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Check, ChevronDown } from "lucide-react";

export interface UiSelectOption {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
}

interface Props {
  value: string;
  options: UiSelectOption[];
  onValueChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
}

export function UiSelect({
  value,
  options,
  onValueChange,
  placeholder = "请选择",
  disabled = false,
  ariaLabel,
  className = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();
  const enabledOptions = useMemo(() => options.filter((option) => !option.disabled), [options]);
  const selected = options.find((option) => option.value === value) ?? null;

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const index = options.findIndex((option) => option.value === value && !option.disabled);
    setActiveIndex(index >= 0 ? index : nextEnabledIndex(options, 0, 1));
  }, [open, options, value]);

  const choose = (option: UiSelectOption) => {
    if (option.disabled) return;
    onValueChange(option.value);
    setOpen(false);
  };

  const moveActive = (direction: 1 | -1) => {
    if (enabledOptions.length === 0) return;
    setActiveIndex((current) => nextEnabledIndex(options, current, direction));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) setOpen(true);
      else moveActive(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) setOpen(true);
      else moveActive(-1);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const option = options[activeIndex];
      if (option) choose(option);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div ref={rootRef} className={`agenthub-select-wrap ${className}`}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-label={ariaLabel}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={onKeyDown}
        className="agenthub-select-trigger agenthub-focus-ring flex w-full items-center gap-2 rounded-2xl border px-3 py-2 text-left text-sm disabled:cursor-not-allowed disabled:opacity-55"
      >
        <span className="min-w-0 flex-1">
          <span className={`agenthub-select-value block truncate ${selected ? "" : "agenthub-faint"}`}>
            {selected?.label ?? placeholder}
          </span>
          {selected?.description && (
            <span className="agenthub-muted mt-0.5 block truncate text-xs">{selected.description}</span>
          )}
        </span>
        <ChevronDown
          size={15}
          className={`agenthub-select-chevron shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div
          id={listboxId}
          role="listbox"
          aria-label={ariaLabel}
          className="agenthub-select-menu agenthub-menu agenthub-popover absolute left-0 top-[calc(100%+6px)] z-[90] max-h-64 w-full overflow-y-auto rounded-2xl border p-1.5"
        >
          {options.length === 0 ? (
            <div className="agenthub-muted px-3 py-2 text-sm">暂无选项</div>
          ) : options.map((option, index) => {
            const selectedOption = option.value === value;
            const activeOption = index === activeIndex;
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={selectedOption}
                disabled={option.disabled}
                onMouseEnter={() => {
                  if (!option.disabled) setActiveIndex(index);
                }}
                onClick={() => choose(option)}
                className={`agenthub-select-option flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm disabled:cursor-not-allowed disabled:opacity-45 ${
                  activeOption ? "agenthub-select-option-active" : ""
                } ${
                  selectedOption ? "agenthub-select-option-selected" : ""
                }`}
              >
                <span className="min-w-0 flex-1">
                  <span className="agenthub-select-option-label block truncate">{option.label}</span>
                  {option.description && (
                    <span className="agenthub-muted mt-0.5 block truncate text-xs">{option.description}</span>
                  )}
                </span>
                {selectedOption && (
                  <span className="agenthub-select-check inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full">
                    <Check size={12} aria-hidden="true" />
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function nextEnabledIndex(options: UiSelectOption[], currentIndex: number, direction: 1 | -1) {
  if (options.length === 0) return 0;
  for (let step = 1; step <= options.length; step += 1) {
    const next = (currentIndex + (step * direction) + options.length) % options.length;
    if (!options[next]?.disabled) return next;
  }
  return currentIndex;
}
