import { Minus, Square, X } from "lucide-react";
import { BrandLogo } from "./BrandLogo";

function withDesktopWindow(action: (window: import("@tauri-apps/api/window").Window) => Promise<unknown>) {
  if (!("__TAURI_INTERNALS__" in window)) return;
  void import("@tauri-apps/api/window").then(({ getCurrentWindow }) => action(getCurrentWindow()));
}

export function DesktopTitleBar() {
  return (
    <header className="agenthub-desktop-titlebar" data-tauri-drag-region>
      <div
        className="agenthub-desktop-title"
        data-tauri-drag-region
        onDoubleClick={() => withDesktopWindow((desktopWindow) => desktopWindow.toggleMaximize())}
      >
        <BrandLogo size="rail" className="agenthub-desktop-title-logo" />
        <span data-tauri-drag-region>AgentHub</span>
      </div>
      <div className="agenthub-window-controls" aria-label="窗口控制">
        <button
          type="button"
          onClick={() => withDesktopWindow((desktopWindow) => desktopWindow.minimize())}
          aria-label="最小化"
          title="最小化"
        >
          <Minus size={14} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => withDesktopWindow((desktopWindow) => desktopWindow.toggleMaximize())}
          aria-label="最大化或还原"
          title="最大化或还原"
        >
          <Square size={11} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="agenthub-window-close"
          onClick={() => withDesktopWindow((desktopWindow) => desktopWindow.close())}
          aria-label="关闭"
          title="关闭"
        >
          <X size={14} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
