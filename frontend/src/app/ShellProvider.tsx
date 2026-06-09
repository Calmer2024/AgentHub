import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { configureApiClient, createDevCloudAuthProvider, fetchCapabilities } from "../api/client";
import type { RuntimeCapabilities, ShellContextValue } from "../types";
import { fallbackCapabilities, parseShellEnv, validateCapabilities, type ParsedShellEnv } from "./capabilities";

interface ShellProviderState extends ShellContextValue {
  loading: boolean;
  error: string | null;
  env: ParsedShellEnv;
}

const defaultEnv = parseShellEnv();
const defaultCapabilities = fallbackCapabilities(defaultEnv);

const ShellContext = createContext<ShellContextValue>({
  capabilities: defaultCapabilities,
  edition: defaultCapabilities.edition,
  surface: defaultCapabilities.surface,
});

export function ShellProvider({
  children,
}: {
  children: ReactNode | ((state: ShellProviderState) => ReactNode);
}) {
  const env = useMemo(() => parseShellEnv(), []);
  const [capabilities, setCapabilities] = useState<RuntimeCapabilities>(() => fallbackCapabilities(env));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fallback = fallbackCapabilities(env);
    configureApiClient({
      apiBaseUrl: env.apiBaseUrl,
      cloudAuthProvider: env.edition === "saas" && env.devAuth ? createDevCloudAuthProvider() : null,
    });
    fetchCapabilities()
      .then((backendCapabilities) => {
        if (cancelled) return;
        const validationError = validateCapabilities(env, backendCapabilities);
        if (validationError) {
          setCapabilities(fallback);
          setError(validationError);
        } else {
          setCapabilities(backendCapabilities);
          setError(null);
        }
      })
      .catch((fetchError: unknown) => {
        if (cancelled) return;
        setCapabilities(fallback);
        setError(fetchError instanceof Error ? fetchError.message : "能力矩阵加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [env]);

  const value = useMemo<ShellContextValue>(() => ({
    capabilities,
    edition: capabilities.edition,
    surface: capabilities.surface,
  }), [capabilities]);

  const state: ShellProviderState = {
    ...value,
    loading,
    error,
    env,
  };

  return (
    <ShellContext.Provider value={value}>
      {typeof children === "function" ? children(state) : children}
    </ShellContext.Provider>
  );
}

export function StaticShellProvider({
  capabilities,
  children,
}: {
  capabilities: RuntimeCapabilities;
  children: ReactNode;
}) {
  useEffect(() => {
    configureApiClient({
      apiBaseUrl: capabilities.apiBaseUrl,
      cloudAuthProvider: capabilities.edition === "saas" ? createDevCloudAuthProvider() : null,
    });
  }, [capabilities]);

  const value = useMemo<ShellContextValue>(() => ({
    capabilities,
    edition: capabilities.edition,
    surface: capabilities.surface,
  }), [capabilities]);

  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>;
}

export function useCapabilities(): ShellContextValue {
  return useContext(ShellContext);
}
