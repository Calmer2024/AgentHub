import { describe, expect, it } from "vitest";
import {
  fallbackCapabilities,
  parseShellEnv,
  saasDesktopCapabilities,
  validateCapabilities,
} from "./capabilities";

describe("Phase 13 capabilities", () => {
  it("按 Vite mode 推断三端 shell", () => {
    expect(parseShellEnv({ MODE: "local-desktop" }).edition).toBe("local");
    expect(parseShellEnv({ MODE: "local-desktop" }).surface).toBe("desktop");
    expect(parseShellEnv({ MODE: "saas" }).edition).toBe("saas");
    expect(parseShellEnv({ MODE: "saas" }).surface).toBe("desktop");
    expect(parseShellEnv({ MODE: "mobile" }).edition).toBe("saas");
    expect(parseShellEnv({ MODE: "mobile" }).surface).toBe("mobile");
  });

  it("生成 fallback 能力矩阵并拒绝前后端壳不一致", () => {
    const env = parseShellEnv({ MODE: "local-desktop" });
    const fallback = fallbackCapabilities(env);
    expect(fallback.features.localWorkspace).toBe(true);
    expect(fallback.features.cloudWorkspace).toBe(false);
    expect(validateCapabilities(env, saasDesktopCapabilities())).toContain("启动配置不一致");
  });
});
