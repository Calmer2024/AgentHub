import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

type Placement = "bottom-start" | "bottom-end" | "top-start" | "top-end";

interface FloatingMenuProps {
  open: boolean;
  anchorRef?: RefObject<HTMLElement | null>;
  anchorElement?: HTMLElement | null;
  children: ReactNode;
  menuRef?: RefObject<HTMLDivElement | null>;
  width?: number;
  placement?: Placement;
  className?: string;
  ariaLabel?: string;
  role?: "menu" | "presentation";
}

interface FloatingPosition {
  left: number;
  top: number;
  width?: number;
}

export function FloatingMenu({
  open,
  anchorRef,
  anchorElement,
  children,
  menuRef,
  width,
  placement = "bottom-end",
  className = "",
  ariaLabel,
  role = "menu",
}: FloatingMenuProps) {
  const [position, setPosition] = useState<FloatingPosition | null>(null);
  const internalMenuRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    if (!open) {
      setPosition(null);
      return;
    }
    if (typeof window === "undefined") return;
    let frame = 0;

    const update = () => {
      const anchor = anchorElement ?? anchorRef?.current;
      const rect = anchor?.getBoundingClientRect();
      if (!rect) {
        setPosition(null);
        return;
      }
      const measuredWidth = internalMenuRef.current?.offsetWidth;
      const menuWidth = width ?? Math.max(88, Math.min(220, measuredWidth || rect.width));
      const menuHeight = internalMenuRef.current?.offsetHeight ?? 0;
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      const gap = 8;
      const maxLeft = Math.max(gap, viewportWidth - menuWidth - gap);
      const alignEnd = placement.endsWith("end");
      const preferTop = placement.startsWith("top");
      const left = Math.min(
        Math.max(gap, alignEnd ? rect.right - menuWidth : rect.left),
        maxLeft,
      );
      const below = rect.bottom + gap;
      const above = rect.top - gap - menuHeight;
      const maxTop = Math.max(gap, viewportHeight - (menuHeight || 0) - gap);
      const top = preferTop
        ? Math.max(gap, menuHeight ? above : rect.top - gap)
        : Math.min(below, maxTop);
      setPosition({ left, top, width: width ? menuWidth : undefined });
    };

    update();
    frame = window.requestAnimationFrame(update);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [anchorElement, anchorRef, open, placement, width]);

  if (!open || typeof document === "undefined" || !position) return null;

  return createPortal(
    <div
      ref={(node) => {
        internalMenuRef.current = node;
        if (menuRef) {
          (menuRef as { current: HTMLDivElement | null }).current = node;
        }
      }}
      role={role}
      aria-label={ariaLabel}
      className={`agenthub-menu agenthub-popover fixed z-[1500] rounded-2xl border p-1.5 ${className}`}
      style={{
        left: position.left,
        top: position.top,
        width: position.width,
        minWidth: width ? undefined : 88,
        maxWidth: width ? undefined : 220,
        maxHeight: "calc(100dvh - 16px)",
        overflowY: "auto",
      }}
    >
      {children}
    </div>,
    document.body,
  );
}
