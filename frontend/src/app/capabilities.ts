import type { AppSurface, ProductEdition, RuntimeCapabilities, RuntimeFeatureFlags } from "../types";

type ShellEnv = Pick<ImportMetaEnv, "MODE"> & Partial<{
  VITE_AGENTHUB_EDITION: string;
  VITE_AGENTHUB_SURFACE: string;
  VITE_AGENTHUB_API_BASE: string;
  VITE_AGENTHUB_DEV_AUTH: string;
}>;

export interface ParsedShellEnv {
  edition: ProductEdition;
  surface: AppSurface;
  apiBaseUrl: string;
  devAuth: boolean;
}

export const DEFAULT_FEATURES: RuntimeFeatureFlags = {
  localWorkspace: false,
  localCliRuntime: false,
  localPreview: false,
  localBuildExport: false,
  cloudWorkspace: false,
  teamSpaces: false,
  cloudPreview: false,
  deployment: false,
  auditLogs: false,
  notifications: false,
  mobileApprovals: false,
};

export function localDesktopCapabilities(apiBaseUrl = "http://127.0.0.1:8000"): RuntimeCapabilities {
  return {
    edition: "local",
    surface: "desktop",
    authRequired: false,
    apiBaseUrl,
    features: {
      ...DEFAULT_FEATURES,
      localWorkspace: true,
      localCliRuntime: true,
      localPreview: true,
      localBuildExport: true,
    },
    limits: { maxUploadBytes: 10 * 1024 * 1024 },
  };
}

export function saasDesktopCapabilities(apiBaseUrl = "/api"): RuntimeCapabilities {
  return {
    edition: "saas",
    surface: "desktop",
    authRequired: true,
    apiBaseUrl,
    features: {
      ...DEFAULT_FEATURES,
      cloudWorkspace: true,
      teamSpaces: true,
      cloudPreview: true,
      deployment: true,
      auditLogs: true,
      notifications: true,
    },
    limits: { maxUploadBytes: 10 * 1024 * 1024 },
  };
}

export function mobileCapabilities(apiBaseUrl = "/api"): RuntimeCapabilities {
  return {
    edition: "saas",
    surface: "mobile",
    authRequired: true,
    apiBaseUrl,
    features: {
      ...DEFAULT_FEATURES,
      cloudWorkspace: true,
      cloudPreview: true,
      notifications: true,
      mobileApprovals: true,
    },
    limits: { maxUploadBytes: 10 * 1024 * 1024 },
  };
}

export function parseShellEnv(env: ShellEnv = import.meta.env): ParsedShellEnv {
  const mode = env.MODE;
  const inferredEdition: ProductEdition = mode === "saas" || mode === "mobile" ? "saas" : "local";
  const inferredSurface: AppSurface = mode === "mobile" ? "mobile" : "desktop";
  const edition = normalizeEdition(env.VITE_AGENTHUB_EDITION) ?? inferredEdition;
  const surface = normalizeSurface(env.VITE_AGENTHUB_SURFACE) ?? inferredSurface;
  return {
    edition,
    surface,
    apiBaseUrl: env.VITE_AGENTHUB_API_BASE?.trim() || (
      edition === "local" ? "http://127.0.0.1:8000" : "/api"
    ),
    devAuth: env.VITE_AGENTHUB_DEV_AUTH === "true",
  };
}

export function fallbackCapabilities(env: ParsedShellEnv): RuntimeCapabilities {
  if (env.edition === "local" && env.surface === "desktop") {
    return localDesktopCapabilities(env.apiBaseUrl);
  }
  if (env.edition === "saas" && env.surface === "mobile") {
    return mobileCapabilities(env.apiBaseUrl);
  }
  return saasDesktopCapabilities(env.apiBaseUrl);
}

export function validateCapabilities(env: ParsedShellEnv, backend: RuntimeCapabilities): string | null {
  if (env.edition === "local" && env.surface === "mobile") {
    return "本机移动端壳暂不支持，请使用 SaaS Mobile 或 Local Desktop。";
  }
  if (backend.edition !== env.edition || backend.surface !== env.surface) {
    return `启动配置不一致：前端是 ${env.edition}/${env.surface}，后端是 ${backend.edition}/${backend.surface}。`;
  }
  return null;
}

function normalizeEdition(value: string | undefined): ProductEdition | null {
  if (value === "local" || value === "saas") return value;
  return null;
}

function normalizeSurface(value: string | undefined): AppSurface | null {
  if (value === "desktop" || value === "mobile") return value;
  return null;
}
