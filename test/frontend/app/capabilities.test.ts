import { describe, expect, it } from "vitest";
import {
  fallbackCapabilities,
  parseShellEnv,
  saasDesktopCapabilities,
  validateCapabilities,
} from "../../../frontend/src/app/capabilities";

describe("Phase 13 capabilities", () => {
  it("按 Vite mode 推断三端 shell", () => {
    expect(parseShellEnv({ MODE: "local-desktop" }).edition).toBe("local");
    expect(parseShellEnv({ MODE: "local-desktop" }).surface).toBe("desktop");
    expect(parseShellEnv({ MODE: "saas" }).edition).toBe("saas");
    expect(parseShellEnv({ MODE: "saas" }).surface).toBe("desktop");
    expect(parseShellEnv({ MODE: "mobile" }).edition).toBe("saas");
    expect(parseShellEnv({ MODE: "mobile" }).surface).toBe("mobile");
  });

  it("SaaS 开发请求头 mock 必须显式开启", () => {
    expect(parseShellEnv({ MODE: "saas" }).devAuth).toBe(false);
    expect(parseShellEnv({ MODE: "saas", VITE_AGENTHUB_DEV_AUTH: "true" }).devAuth).toBe(true);
  });

  it("生成 fallback 能力矩阵并拒绝前后端壳不一致", () => {
    const env = parseShellEnv({ MODE: "local-desktop" });
    const fallback = fallbackCapabilities(env);
    expect(fallback.features.localWorkspace).toBe(true);
    expect(fallback.features.cloudWorkspace).toBe(false);
    expect(validateCapabilities(env, saasDesktopCapabilities())).toContain("启动配置不一致");
  });

  it("SaaS Web 构建必须接受 SaaS 后端能力矩阵", () => {
    const env = parseShellEnv({ MODE: "saas" });
    expect(validateCapabilities(env, saasDesktopCapabilities())).toBeNull();
  });
});
