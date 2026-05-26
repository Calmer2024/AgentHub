import { describe, it, expect } from "vitest";
import { useChatStore } from "./chat";
import type { Agent } from "../types";

const mockAgent: Agent = {
  name: "claude",
  displayName: "Claude 4 Opus",
  provider: "anthropic",
  isAvailable: true,
  capability: {
    supportsStreaming: true,
    supportsFileInput: false,
    supportsToolCall: false,
    maxContextTokens: 200000,
    tags: ["code"],
  },
};

describe("Chat Store - Agent 管理", () => {
  it("初始状态 agents 为空数组", () => {
    const { agents } = useChatStore.getState();
    expect(agents).toEqual([]);
  });

  it("setAgents 设置 agent 列表", () => {
    useChatStore.getState().setAgents([mockAgent]);
    expect(useChatStore.getState().agents).toEqual([mockAgent]);
  });

  it("初始状态 settingsOpen 为 false", () => {
    const { settingsOpen } = useChatStore.getState();
    expect(settingsOpen).toBe(false);
  });

  it("setSettingsOpen 切换设置面板", () => {
    useChatStore.getState().setSettingsOpen(true);
    expect(useChatStore.getState().settingsOpen).toBe(true);
  });

  it("updateSession 更新会话列表", () => {
    useChatStore.getState().setSessions([
      { id: "s1", title: "旧标题", agentName: "claude", createdAt: "", updatedAt: "" },
    ]);
    useChatStore.getState().updateSession({
      id: "s1", title: "旧标题", agentName: "deepseek", createdAt: "", updatedAt: "",
    });
    const sessions = useChatStore.getState().sessions;
    expect(sessions[0].agentName).toBe("deepseek");
  });
});
