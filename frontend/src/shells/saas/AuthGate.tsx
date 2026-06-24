import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Loader2, LogIn, ShieldAlert, UserPlus } from "lucide-react";
import {
  fetchAuthProviders,
  fetchCurrentUser,
  getStoredAuthSession,
  loginWithEmail,
  registerWithPassword,
} from "../../api/client";
import type { AuthProvider, CurrentUser } from "../../types";

type AuthField = "identifier" | "username" | "email" | "password";
type AuthFieldErrors = Partial<Record<AuthField, string>>;

export function AuthGate({ children, surface }: { children: ReactNode; surface: "desktop" | "mobile" }) {
  const [user, setUser] = useState<CurrentUser | null>(() => getStoredAuthSession()?.user ?? null);
  const [providers, setProviders] = useState<AuthProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [identifier, setIdentifier] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<AuthFieldErrors>({});

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
      const message = err instanceof Error ? err.message : "请先登录后继续";
      setError(isExpectedSignedOutState(message) ? null : message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadIdentity();
  }, [loadIdentity]);

  const submit = async () => {
    const nextErrors = validateAuthFields({ mode, identifier, username, email, password });
    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const session = mode === "login"
        ? await loginWithEmail({
          identifier: identifier.trim(),
          password,
        })
        : await registerWithPassword({
          username: username.trim(),
          email: email.trim(),
          password,
          displayName: displayName.trim() || undefined,
        });
      setUser(session.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : mode === "login" ? "登录失败" : "注册失败");
    } finally {
      setSubmitting(false);
    }
  };

  const clearFieldError = (field: AuthField) => {
    setFieldErrors((current) => {
      if (!current[field]) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
  };

  if (loading && user) {
    return <AuthStatus title="正在恢复登录态" description="正在连接你的云端空间" />;
  }
  if (user) return <>{children}</>;
  if (loading) {
    return <AuthStatus title="正在检查登录态" description="稍后将进入登录或注册入口" />;
  }

  const providerText = providers.length > 0
    ? providers.filter((item) => item.enabled).map((item) => item.label).join(" / ")
    : "用户名密码";

  return (
    <main className="agenthub-shell flex h-[100dvh] w-screen items-center justify-center px-4">
      <section className="agenthub-auth-card agenthub-card w-full max-w-md border px-6 py-6">
        <div className="flex items-center gap-3">
          <span className="agenthub-soft agenthub-muted flex h-10 w-10 items-center justify-center rounded-full border">
            {mode === "login" ? <LogIn size={18} /> : <UserPlus size={18} />}
          </span>
          <div className="min-w-0">
            <p className="agenthub-faint text-xs">{surface === "mobile" ? "AgentHub Mobile" : "AgentHub SaaS"}</p>
            <h1 className="agenthub-strong truncate text-base font-semibold">
              {mode === "login" ? "登录云端工作区" : "注册云端账号"}
            </h1>
          </div>
        </div>
        <p className="agenthub-muted mt-3 text-sm leading-6">
          {mode === "login" ? "使用账号进入当前云端空间。" : "创建账号后即可进入云端工作区。"}
        </p>

        <div className="agenthub-theme-segment mt-5 grid grid-cols-2 rounded-full p-1">
          <button
            type="button"
            data-active={mode === "login"}
            onClick={() => {
              setMode("login");
              setError(null);
              setFieldErrors({});
            }}
            className="agenthub-theme-choice inline-flex h-9 items-center justify-center gap-1.5 rounded-full text-sm font-medium transition"
          >
            <LogIn size={14} />
            登录
          </button>
          <button
            type="button"
            data-active={mode === "register"}
            onClick={() => {
              setMode("register");
              setError(null);
              setFieldErrors({});
            }}
            className="agenthub-theme-choice inline-flex h-9 items-center justify-center gap-1.5 rounded-full text-sm font-medium transition"
          >
            <UserPlus size={14} />
            注册
          </button>
        </div>

        <div className="mt-5 space-y-3">
          {mode === "login" ? (
          <label className="block space-y-1.5" htmlFor="agenthub-auth-identifier">
            <span className="agenthub-muted text-xs">用户名或邮箱</span>
            <input
              id="agenthub-auth-identifier"
              value={identifier}
              onChange={(event) => {
                setIdentifier(event.target.value);
                clearFieldError("identifier");
              }}
              aria-invalid={Boolean(fieldErrors.identifier)}
              className={authInputClass(Boolean(fieldErrors.identifier))}
              autoComplete="username"
              placeholder="输入用户名或邮箱"
            />
            <FieldError message={fieldErrors.identifier} />
          </label>
          ) : (
          <>
          <label className="block space-y-1.5" htmlFor="agenthub-auth-username">
            <span className="agenthub-muted text-xs">用户名</span>
            <input
              id="agenthub-auth-username"
              value={username}
              onChange={(event) => {
                setUsername(event.target.value);
                clearFieldError("username");
              }}
              aria-invalid={Boolean(fieldErrors.username)}
              className={authInputClass(Boolean(fieldErrors.username))}
              autoComplete="username"
              placeholder="设置登录用户名"
            />
            <FieldError message={fieldErrors.username} />
          </label>
          <label className="block space-y-1.5" htmlFor="agenthub-auth-email">
            <span className="agenthub-muted text-xs">邮箱</span>
            <input
              id="agenthub-auth-email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                clearFieldError("email");
              }}
              aria-invalid={Boolean(fieldErrors.email)}
              className={authInputClass(Boolean(fieldErrors.email))}
              autoComplete="email"
              placeholder="输入邮箱"
            />
            <FieldError message={fieldErrors.email} />
          </label>
          <label className="block space-y-1.5" htmlFor="agenthub-auth-name">
            <span className="agenthub-muted text-xs">显示名称</span>
            <input
              id="agenthub-auth-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className={authInputClass(false)}
              autoComplete="name"
              placeholder="可选，用于团队内显示"
            />
          </label>
          </>
          )}
          <label className="block space-y-1.5" htmlFor="agenthub-auth-password">
            <span className="agenthub-muted text-xs">密码</span>
            <input
              id="agenthub-auth-password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
                clearFieldError("password");
              }}
              aria-invalid={Boolean(fieldErrors.password)}
              className={authInputClass(Boolean(fieldErrors.password))}
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder={mode === "login" ? "输入密码" : "至少 8 位"}
            />
            <FieldError message={fieldErrors.password} />
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
          disabled={submitting}
          className="agenthub-primary-button mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-2xl text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? <Loader2 size={16} className="animate-spin" /> : mode === "login" ? <LogIn size={16} /> : <UserPlus size={16} />}
          {mode === "login" ? "登录" : "注册"}
        </button>
        <p className="agenthub-faint mt-3 text-xs">当前启用：{providerText}</p>
      </section>
    </main>
  );
}

function AuthStatus({ title, description }: { title: string; description?: string }) {
  return (
    <main className="agenthub-shell flex h-[100dvh] items-center justify-center px-6">
      <div className="agenthub-auth-status agenthub-card inline-flex items-center gap-3 border px-4 py-3">
        <Loader2 size={16} className="animate-spin" />
        <div className="min-w-0">
          <div className="text-sm font-medium">{title}</div>
          {description && <div className="agenthub-muted mt-0.5 text-xs">{description}</div>}
        </div>
      </div>
    </main>
  );
}

function authInputClass(hasError: boolean) {
  return `agenthub-composer h-11 w-full rounded-lg border px-3 text-sm outline-none ${
    hasError ? "border-[color:var(--ah-danger)]" : ""
  }`;
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <span className="block text-xs text-[color:var(--ah-danger)]">{message}</span>;
}

function validateAuthFields(input: {
  mode: "login" | "register";
  identifier: string;
  username: string;
  email: string;
  password: string;
}): AuthFieldErrors {
  const errors: AuthFieldErrors = {};
  if (input.mode === "login") {
    if (!input.identifier.trim()) errors.identifier = "请输入用户名或邮箱";
    if (!input.password) errors.password = "请输入密码";
    return errors;
  }

  const username = input.username.trim();
  const email = input.email.trim();
  if (!username) errors.username = "请输入用户名";
  else if (username.length < 3 || username.length > 32) errors.username = "用户名需要 3-32 个字符";
  else if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(username)) {
    errors.username = "用户名只能包含字母、数字、下划线或连字符，且必须以字母或数字开头";
  }
  if (!email) errors.email = "请输入邮箱";
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = "请输入有效邮箱";
  if (!input.password) errors.password = "请输入密码";
  else if (input.password.length < 8) errors.password = "密码至少 8 位";
  return errors;
}

function isExpectedSignedOutState(message: string) {
  const normalized = message.trim().toLowerCase();
  return normalized === "请先登录后继续"
    || normalized.includes("unauthorized")
    || normalized.includes("401");
}
