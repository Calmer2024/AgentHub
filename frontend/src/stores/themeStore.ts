import { create } from "zustand";

export type ThemeMode = "dark" | "light";
export type ThemePreference = "system" | ThemeMode;

interface ThemeState {
  theme: ThemeMode;
  preference: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  toggleTheme: () => void;
}

const STORAGE_KEY = "agenthub.theme";
const TRANSITION_CLASS = "agenthub-theme-switching";
let transitionTimer: number | null = null;

function systemTheme(): ThemeMode {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function initialPreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  return saved === "dark" || saved === "light" || saved === "system" ? saved : "system";
}

function resolveTheme(preference: ThemePreference): ThemeMode {
  return preference === "system" ? systemTheme() : preference;
}

function applyTheme(theme: ThemeMode, animated = true) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (transitionTimer !== null) window.clearTimeout(transitionTimer);
  if (!animated) {
    root.classList.remove(TRANSITION_CLASS);
    root.dataset.theme = theme;
    transitionTimer = null;
    return;
  }
  root.classList.add(TRANSITION_CLASS);
  root.getBoundingClientRect();
  root.dataset.theme = theme;
  transitionTimer = window.setTimeout(() => {
    root.classList.remove(TRANSITION_CLASS);
    transitionTimer = null;
  }, 140);
}

function syncNativeWindowTheme(preference: ThemePreference) {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return;
  void import("@tauri-apps/api/window")
    .then(({ getCurrentWindow }) => getCurrentWindow().setTheme(preference === "system" ? null : preference))
    .catch(() => {
      // 浏览器预览和旧版壳层不应因原生标题栏同步失败而阻断页面。
    });
}

export const useThemeStore = create<ThemeState>((set, get) => {
  const preference = initialPreference();
  const theme = resolveTheme(preference);
  applyTheme(theme, false);
  syncNativeWindowTheme(preference);
  return {
    theme,
    preference,
    setTheme: (nextPreference) => {
      const nextTheme = resolveTheme(nextPreference);
      applyTheme(nextTheme, true);
      syncNativeWindowTheme(nextPreference);
      if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, nextPreference);
      set({ preference: nextPreference, theme: nextTheme });
    },
    toggleTheme: () => {
      const nextPreference: Record<ThemePreference, ThemePreference> = {
        system: "dark",
        dark: "light",
        light: "system",
      };
      get().setTheme(nextPreference[get().preference]);
    },
  };
});

if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    const state = useThemeStore.getState();
    if (state.preference !== "system") return;
    const theme = systemTheme();
    applyTheme(theme, true);
    useThemeStore.setState({ theme });
  });
}
