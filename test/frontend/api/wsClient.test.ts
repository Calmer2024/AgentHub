import { describe, expect, it } from "vitest";
import { buildWebSocketUrl } from "../../../frontend/src/api/wsClient";

describe("buildWebSocketUrl", () => {
  it("桌面端使用 API base 推导本地后端 WS 地址", () => {
    expect(buildWebSocketUrl("s1", "http://127.0.0.1:8188/api", {
      protocol: "http:",
      host: "tauri.localhost",
      origin: "http://tauri.localhost",
    })).toBe("ws://127.0.0.1:8188/ws/sessions/s1");
  });

  it("开发代理模式保持同源 WS 地址", () => {
    expect(buildWebSocketUrl("s1", "/api", {
      protocol: "http:",
      host: "127.0.0.1:5173",
      origin: "http://127.0.0.1:5173",
    })).toBe("ws://127.0.0.1:5173/ws/sessions/s1");
  });
});
