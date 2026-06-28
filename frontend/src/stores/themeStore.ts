import { create } from "zustand";

export type ThemeMode = "dark" | "light";

interface ThemeState {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
}

const STORAGE_KEY = "agenthub.theme";
const TRANSITION_CLASS = "agenthub-theme-switching";
let transitionTimer: number | null = null;

function initialTheme(): ThemeMode {
  if (typeof window === "undefined") return "dark";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  return saved === "light" ? "light" : "dark";
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

export const useThemeStore = create<ThemeState>((set, get) => {
  const theme = initialTheme();
  applyTheme(theme, false);
  return {
    theme,
    setTheme: (nextTheme) => {
      applyTheme(nextTheme, true);
      if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, nextTheme);
      set({ theme: nextTheme });
    },
    toggleTheme: () => {
      const nextTheme = get().theme === "dark" ? "light" : "dark";
      get().setTheme(nextTheme);
    },
  };
});
