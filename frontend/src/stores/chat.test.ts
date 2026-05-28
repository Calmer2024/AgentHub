import { describe, it, expect } from "vitest";
import { useChatStore } from "./chatStore";
import { useSessionStore } from "./sessionStore";
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

describe("Chat Store (split)", () => {
  it("chatStore 初始状态 messages 为空数组", () => {
    expect(useChatStore.getState().messages).toEqual([]);
  });

  it("chatStore 初始 isStreaming 为 false", () => {
    expect(useChatStore.getState().isStreaming).toBe(false);
  });

  it("chatStore appendStreamingToken", () => {
    useChatStore.setState({
      messages: [{ id: "1", sessionId: "s", role: "assistant", content: "Hi", agentName: null, createdAt: "" }],
      isStreaming: true,
    });
    useChatStore.getState().appendStreamingToken(" there");
    expect(useChatStore.getState().messages[0].content).toBe("Hi there");
  });

  it("sessionStore 初始 agents 为空数组", () => {
    expect(useSessionStore.getState().agents).toEqual([]);
  });

  it("sessionStore setAgents 设置 agent 列表", () => {
    useSessionStore.getState().setAgents([mockAgent]);
    expect(useSessionStore.getState().agents).toEqual([mockAgent]);
  });

  it("sessionStore setProviders 设置 provider 列表", () => {
    useSessionStore.getState().setProviders([mockProvider]);
    expect(useSessionStore.getState().providers).toEqual([mockProvider]);
  });

  it("sessionStore 初始 sidebarTab 为 sessions", () => {
    expect(useSessionStore.getState().sidebarTab).toBe("sessions");
  });

  it("sessionStore updateSession 更新会话列表", () => {
    useSessionStore.getState().setSessions([
      { id: "s1", title: "旧标题", agentConfigId: "a1", mode: "single", createdAt: "", updatedAt: "" },
    ]);
    useSessionStore.getState().updateSession({
      id: "s1", title: "旧标题", agentConfigId: "a2", mode: "single", createdAt: "", updatedAt: "",
    });
    expect(useSessionStore.getState().sessions[0].agentConfigId).toBe("a2");
  });
});
