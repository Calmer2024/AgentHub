import { create } from "zustand";

export type ThemeMode = "dark" | "light";

interface ThemeState {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
}

const STORAGE_KEY = "agenthub.theme";

function initialTheme(): ThemeMode {
  if (typeof window === "undefined") return "dark";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  return saved === "light" ? "light" : "dark";
}

function applyTheme(theme: ThemeMode) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = theme;
}

export const useThemeStore = create<ThemeState>((set, get) => {
  const theme = initialTheme();
  applyTheme(theme);
  return {
    theme,
    setTheme: (nextTheme) => {
      applyTheme(nextTheme);
      if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, nextTheme);
      set({ theme: nextTheme });
    },
    toggleTheme: () => {
      const nextTheme = get().theme === "dark" ? "light" : "dark";
      get().setTheme(nextTheme);
    },
  };
});
