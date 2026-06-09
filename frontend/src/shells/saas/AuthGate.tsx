import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Loader2, LogIn, ShieldAlert } from "lucide-react";
import {
  fetchAuthProviders,
  fetchCurrentUser,
  getStoredAuthSession,
  loginWithEmail,
} from "../../api/client";
import type { AuthProvider, CurrentUser } from "../../types";

export function AuthGate({ children, surface }: { children: ReactNode; surface: "desktop" | "mobile" }) {
  const [user, setUser] = useState<CurrentUser | null>(() => getStoredAuthSession()?.user ?? null);
  const [providers, setProviders] = useState<AuthProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [email, setEmail] = useState("demo@agenthub.local");
  const [displayName, setDisplayName] = useState("AgentHub Demo");
  const [error, setError] = useState<string | null>(null);

  const loadIdentity = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [currentUser, authProviders] = await Promise.all([
        fetchCurrentUser(),
        fetchAuthProviders().catch(() => []),
      ]);
      setUser(currentUser);
      setProviders(authProviders);
    } catch (err) {
      setUser(null);
      setProviders(await fetchAuthProviders().catch(() => []));
      setError(err instanceof Error ? err.message : "请先登录后继续");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadIdentity();
  }, [loadIdentity]);

  const submit = async () => {
    const cleanEmail = email.trim();
    if (!cleanEmail) return;
    setSubmitting(true);
    setError(null);
    try {
      const session = await loginWithEmail({
        email: cleanEmail,
        displayName: displayName.trim() || undefined,
      });
      setUser(session.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading && user) {
    return <AuthStatus title="正在恢复登录态" />;
  }
  if (user) return <>{children}</>;
  if (loading) {
    return <AuthStatus title="正在检查登录态" />;
  }

  const providerText = providers.length > 0
    ? providers.filter((item) => item.enabled).map((item) => item.label).join(" / ")
    : "邮箱登录";

  return (
    <main className="agenthub-shell flex h-[100dvh] w-screen items-center justify-center px-4">
      <section className="agenthub-card w-full max-w-sm rounded-lg border px-5 py-5">
        <div className="flex items-center gap-3">
          <span className="agenthub-soft agenthub-muted flex h-10 w-10 items-center justify-center rounded-full border">
            <LogIn size={18} />
          </span>
          <div className="min-w-0">
            <p className="agenthub-faint text-xs">{surface === "mobile" ? "AgentHub Mobile" : "AgentHub SaaS"}</p>
            <h1 className="agenthub-strong truncate text-base font-semibold">登录云端工作区</h1>
          </div>
        </div>

        <div className="mt-5 space-y-3">
          <label className="block space-y-1.5" htmlFor="agenthub-auth-email">
            <span className="agenthub-muted text-xs">邮箱</span>
            <input
              id="agenthub-auth-email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="agenthub-composer h-11 w-full rounded-lg border px-3 text-sm outline-none"
              autoComplete="email"
            />
          </label>
          <label className="block space-y-1.5" htmlFor="agenthub-auth-name">
            <span className="agenthub-muted text-xs">显示名称</span>
            <input
              id="agenthub-auth-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className="agenthub-composer h-11 w-full rounded-lg border px-3 text-sm outline-none"
              autoComplete="name"
            />
          </label>
        </div>

        {error && (
          <div className="agenthub-status-error mt-4 flex items-start gap-2 rounded-lg border px-3 py-2 text-sm">
            <ShieldAlert size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <button
          type="button"
          onClick={() => void submit()}
          disabled={submitting || !email.trim()}
          className="agenthub-primary-button mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />}
          登录
        </button>
        <p className="agenthub-faint mt-3 text-xs">当前启用：{providerText}</p>
      </section>
    </main>
  );
}

function AuthStatus({ title }: { title: string }) {
  return (
    <main className="agenthub-shell flex h-[100dvh] items-center justify-center px-6">
      <div className="agenthub-card inline-flex items-center gap-3 rounded-lg border px-4 py-3">
        <Loader2 size={16} className="animate-spin" />
        <span className="text-sm">{title}</span>
      </div>
    </main>
  );
}
