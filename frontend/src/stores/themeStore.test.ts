import { afterEach, describe, expect, it, vi } from "vitest";

describe("useThemeStore", () => {
  afterEach(async () => {
    vi.useRealTimers();
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.classList.remove("agenthub-theme-switching");
    vi.resetModules();
  });

  it("切换主题时同步更新根节点并使用统一过渡窗口", async () => {
    vi.useFakeTimers();
    const { useThemeStore } = await import("./themeStore");

    useThemeStore.getState().setTheme("light");

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement).toHaveClass("agenthub-theme-switching");
    expect(window.localStorage.getItem("agenthub.theme")).toBe("light");

    vi.advanceTimersByTime(180);

    expect(document.documentElement).not.toHaveClass("agenthub-theme-switching");
  });
});
