import { LocalDesktopShell } from "../shells/local/LocalDesktopShell";
import { SaasWebShell } from "../shells/saas/SaasWebShell";
import { MobileShell } from "../shells/mobile/MobileShell";
import { ShellProvider } from "./ShellProvider";
import { AuthGate } from "../shells/saas/AuthGate";

export function AppRoot() {
  return (
    <ShellProvider>
      {({ loading, error, capabilities }) => {
        if (loading) return <ShellStatus title="正在加载能力矩阵" />;
        if (error) return <ShellStatus title="启动配置错误" description={error} tone="error" />;
        if (capabilities.edition === "local" && capabilities.surface === "mobile") {
          return <ShellStatus title="不支持本机移动端壳" description="请启动 Local Desktop 或 SaaS Mobile。" tone="error" />;
        }
        if (capabilities.edition === "saas" && capabilities.surface === "mobile") {
          return (
            <AuthGate surface="mobile">
              <MobileShell />
            </AuthGate>
          );
        }
        if (capabilities.edition === "saas") {
          return <SaasWebShell />;
        }
        return <LocalDesktopShell />;
      }}
    </ShellProvider>
  );
}

function ShellStatus({
  title,
  description,
  tone = "info",
}: {
  title: string;
  description?: string;
  tone?: "info" | "error";
}) {
  return (
    <main className="agenthub-shell flex h-[100dvh] items-center justify-center px-6 text-center">
      <div className={`rounded-lg border px-5 py-4 ${tone === "error" ? "agenthub-status-error" : "agenthub-status-info"}`}>
        <h1 className="text-base font-semibold">{title}</h1>
        {description && <p className="mt-2 max-w-xl text-sm leading-6">{description}</p>}
      </div>
    </main>
  );
}
