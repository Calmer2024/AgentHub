import { describe, it, expect } from "vitest";
import { useChatStore } from "./chat";
import type { AgentConfig, Provider } from "../types";

const mockAgent: AgentConfig = {
  id: "a1", name: "测试 Agent", description: "", systemPrompt: "",
  provider: "deepseek", model: "deepseek-v4-flash",
  temperature: 0.7, isActive: true, createdAt: "", updatedAt: "",
};

const mockProvider: Provider = {
  name: "deepseek", displayName: "DeepSeek V3", provider: "deepseek",
  isAvailable: true, models: ["deepseek-v4-flash"], defaultModel: "deepseek-v4-flash",
  capability: { supportsStreaming: true, supportsFileInput: false, supportsToolCall: false, maxContextTokens: 128000, tags: [] },
};

describe("Chat Store", () => {
  it("初始状态 agents 为空数组", () => {
    expect(useChatStore.getState().agents).toEqual([]);
  });

  it("setAgents 设置 agent 列表", () => {
    useChatStore.getState().setAgents([mockAgent]);
    expect(useChatStore.getState().agents).toEqual([mockAgent]);
  });

  it("初始状态 providers 为空数组", () => {
    expect(useChatStore.getState().providers).toEqual([]);
  });

  it("setProviders 设置 provider 列表", () => {
    useChatStore.getState().setProviders([mockProvider]);
    expect(useChatStore.getState().providers).toEqual([mockProvider]);
  });

  it("初始状态 sidebarTab 为 sessions", () => {
    expect(useChatStore.getState().sidebarTab).toBe("sessions");
  });

  it("updateSession 更新会话列表", () => {
    useChatStore.getState().setSessions([
      { id: "s1", title: "旧标题", agentConfigId: "a1", createdAt: "", updatedAt: "" },
    ]);
    useChatStore.getState().updateSession({
      id: "s1", title: "旧标题", agentConfigId: "a2", createdAt: "", updatedAt: "",
    });
    expect(useChatStore.getState().sessions[0].agentConfigId).toBe("a2");
  });
});
