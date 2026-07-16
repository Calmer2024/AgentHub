import { afterEach, describe, expect, it, vi } from "vitest";

describe("useThemeStore", () => {
  afterEach(async () => {
    vi.useRealTimers();
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.classList.remove("agenthub-theme-switching");
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it("切换主题时同步更新根节点并使用统一过渡窗口", async () => {
    vi.useFakeTimers();
    const { useThemeStore } = await import("../../../frontend/src/stores/themeStore");

    useThemeStore.getState().setTheme("light");

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement).toHaveClass("agenthub-theme-switching");
    expect(window.localStorage.getItem("agenthub.theme")).toBe("light");

    vi.advanceTimersByTime(180);

    expect(document.documentElement).not.toHaveClass("agenthub-theme-switching");
  });

  it("默认跟随系统主题，并在系统配色变化时同步页面", async () => {
    let dark = false;
    let listener: ((event: MediaQueryListEvent) => void) | undefined;
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      get matches() { return dark; },
      media: "(prefers-color-scheme: dark)",
      onchange: null,
      addEventListener: (_type: string, callback: (event: MediaQueryListEvent) => void) => { listener = callback; },
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));

    const { useThemeStore } = await import("../../../frontend/src/stores/themeStore");
    expect(useThemeStore.getState().preference).toBe("system");
    expect(useThemeStore.getState().theme).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");

    dark = true;
    listener?.({ matches: true } as MediaQueryListEvent);

    expect(useThemeStore.getState().theme).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("固定主题时忽略系统配色变化", async () => {
    let listener: ((event: MediaQueryListEvent) => void) | undefined;
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: false,
      media: "(prefers-color-scheme: dark)",
      onchange: null,
      addEventListener: (_type: string, callback: (event: MediaQueryListEvent) => void) => { listener = callback; },
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));
    const { useThemeStore } = await import("../../../frontend/src/stores/themeStore");
    useThemeStore.getState().setTheme("light");
    listener?.({ matches: true } as MediaQueryListEvent);
    expect(useThemeStore.getState().theme).toBe("light");
  });

});
