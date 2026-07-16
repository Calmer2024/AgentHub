import { Check, Laptop, Moon, Sun } from "lucide-react";
import { useThemeStore, type ThemePreference } from "../stores/themeStore";

const themeOptions: Array<{
  value: ThemePreference;
  label: string;
  description: string;
  icon: typeof Sun;
}> = [
  { value: "system", label: "跟随系统", description: "自动匹配 Windows 外观", icon: Laptop },
  { value: "dark", label: "深色", description: "适合低光环境", icon: Moon },
  { value: "light", label: "浅色", description: "适合明亮环境", icon: Sun },
];

export function AppSettingsPage() {
  const preference = useThemeStore((state) => state.preference);
  const setTheme = useThemeStore((state) => state.setTheme);

  return (
    <main className="agenthub-app-settings min-h-0 flex-1 overflow-y-auto px-8 py-7">
      <div className="mx-auto w-full max-w-3xl">
        <h1 className="agenthub-strong text-xl font-semibold">设置</h1>
        <p className="agenthub-muted mt-1 text-sm">调整此桌面应用的显示方式。</p>

        <section className="mt-8" aria-labelledby="appearance-settings-title">
          <h2 id="appearance-settings-title" className="agenthub-strong text-sm font-semibold">外观</h2>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {themeOptions.map((option) => {
              const Icon = option.icon;
              const selected = preference === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  data-selected={selected}
                  onClick={() => setTheme(option.value)}
                  className="agenthub-settings-choice agenthub-focus-ring relative min-h-24 rounded-[14px] px-4 py-3 text-left"
                  aria-pressed={selected}
                >
                  <span className="flex items-center justify-between gap-3">
                    <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
                    {selected && <Check size={16} strokeWidth={2} aria-hidden="true" />}
                  </span>
                  <span className="agenthub-strong mt-3 block text-sm font-medium">{option.label}</span>
                  <span className="agenthub-muted mt-0.5 block text-xs">{option.description}</span>
                </button>
              );
            })}
          </div>
        </section>
      </div>
    </main>
  );
}
