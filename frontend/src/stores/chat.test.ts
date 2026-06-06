import { describe, it, expect } from "vitest";
import { useChatStore } from "./chatStore";
import { useSessionStore } from "./sessionStore";
import type { AgentConfig, Artifact } from "../types";

const mockAgent: AgentConfig = {
  id: "a1", name: "测试 Agent", description: "", systemPrompt: "",
  agentType: "cli_wrapper", cliTool: "claude_code", executable: "claude",
  initArgs: ["-p"], envVars: {}, status: "ready",
  primarySkill: "general_coding", auxiliarySkills: ["workspace_editing"],
  contextPolicy: "workspace_coding",
  isActive: true, createdAt: "", updatedAt: "",
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

  it("chatStore 可把流式 token 固定写入指定消息，避免写到最后一个气泡", () => {
    useChatStore.setState({
      messages: [
        { id: "target", sessionId: "s", role: "assistant", content: "A", agentName: null, createdAt: "" },
        { id: "latest", sessionId: "s", role: "assistant", content: "B", agentName: null, createdAt: "" },
      ],
      isStreaming: true,
    });

    useChatStore.getState().appendStreamingTokenToMessage("target", "+");

    expect(useChatStore.getState().messages.map((m) => m.content)).toEqual(["A+", "B"]);
  });

  it("chatStore 忽略非当前会话的异步消息覆盖", () => {
    useChatStore.setState({
      currentSessionId: "s-current",
      messages: [
        { id: "current", sessionId: "s-current", role: "assistant", content: "当前", agentName: null, createdAt: "" },
      ],
    });

    useChatStore.getState().setMessagesForSession("s-old", [
      { id: "old", sessionId: "s-old", role: "assistant", content: "旧会话", agentName: null, createdAt: "" },
    ]);

    expect(useChatStore.getState().messages.map((m) => m.id)).toEqual(["current"]);

    useChatStore.getState().setMessagesForSession("s-current", [
      { id: "next", sessionId: "s-current", role: "assistant", content: "新", agentName: null, createdAt: "" },
    ]);

    expect(useChatStore.getState().messages.map((m) => m.id)).toEqual(["next"]);
  });

  it("chatStore 刷新服务端消息时保留异步执行中的 Agent 气泡", () => {
    useChatStore.setState({
      currentSessionId: "s-current",
      messages: [
        { id: "server-1", sessionId: "s-current", role: "assistant", content: "已确认执行", agentName: "调度器", createdAt: "" },
        {
          id: "msg_agent_running",
          sessionId: "s-current",
          role: "assistant",
          content: "正在分析",
          agentName: "架构师",
          sourceType: "agent",
          agentRole: "executor",
          phase: 0,
          taskName: "系统架构设计",
          isCollaborating: true,
          metadata: {
            executionTrace: {
              status: "running",
              agentName: "架构师",
              startedAt: "",
              completedAt: null,
              processId: "cli_1",
              exitCode: null,
              items: [],
            },
          },
          createdAt: "",
        },
      ],
    });

    useChatStore.getState().setMessagesForSession("s-current", [
      { id: "server-1", sessionId: "s-current", role: "assistant", content: "已确认执行", agentName: "调度器", createdAt: "" },
    ]);

    expect(useChatStore.getState().messages.map((m) => m.id)).toEqual(["server-1", "msg_agent_running"]);
  });

  it("chatStore 忽略非当前会话的异步产物覆盖", () => {
    const artifact = (id: string, sessionId: string): Artifact => ({
      id,
      sessionId,
      messageId: "m",
      type: "code_diff",
      title: id,
      content: "",
      status: "ready",
      version: 1,
      createdAt: "",
    });
    useChatStore.setState({
      currentSessionId: "s-current",
      artifacts: [artifact("current", "s-current")],
    });

    useChatStore.getState().setArtifactsForSession("s-old", [artifact("old", "s-old")]);

    expect(useChatStore.getState().artifacts.map((item) => item.id)).toEqual(["current"]);
  });

  it("chatStore 只允许当前 run 结束 streaming", () => {
    useChatStore.getState().startStreamRun("run-new");
    useChatStore.getState().finishStreamRun("run-old");

    expect(useChatStore.getState().isStreaming).toBe(true);
    expect(useChatStore.getState().activeRunId).toBe("run-new");
    expect(useChatStore.getState().latestRunId).toBe("run-new");

    useChatStore.getState().finishStreamRun("run-new");

    expect(useChatStore.getState().isStreaming).toBe(false);
    expect(useChatStore.getState().activeRunId).toBeNull();
    expect(useChatStore.getState().latestRunId).toBe("run-new");
  });

  it("chatStore 保存 DAG 协作快照", () => {
    useChatStore.getState().saveCollab("s-dag", {
      routeAgents: [{ id: "a1", name: "架构师" }],
      collabTasks: [{ name: "planning", role: "planner", agent: "架构师", status: "running", phase: 0 }],
      dagPhases: [{
        phase: 0,
        mode: "serial",
        status: "running",
        tasks: [{ name: "planning", role: "planner", agent: "架构师", status: "running", phase: 0 }],
      }],
      chainSteps: [],
      orchestratorIntent: "code_gen",
      planSummary: "已安排: 先由@架构师规划。",
      collabCompleted: false,
      collabSummary: null,
      draftPlan: null,
    });
    expect(useChatStore.getState().getCollab("s-dag").dagPhases[0].phase).toBe(0);
    expect(useChatStore.getState().getCollab("s-dag").planSummary).toContain("架构师");
  });

  it("sessionStore 初始 agents 为空数组", () => {
    expect(useSessionStore.getState().agents).toEqual([]);
  });

  it("sessionStore setAgents 设置 agent 列表", () => {
    useSessionStore.getState().setAgents([mockAgent]);
    expect(useSessionStore.getState().agents).toEqual([mockAgent]);
  });

  it("sessionStore 初始 sidebarTab 为 sessions", () => {
    expect(useSessionStore.getState().sidebarTab).toBe("sessions");
  });

  it("sessionStore updateSession 更新会话列表", () => {
    useSessionStore.getState().setSessions([
      { id: "s1", title: "旧标题", projectId: "p1", agentConfigId: "a1", mode: "single", createdAt: "", updatedAt: "" },
    ]);
    useSessionStore.getState().updateSession({
      id: "s1", title: "旧标题", projectId: "p1", agentConfigId: "a2", mode: "single", createdAt: "", updatedAt: "",
    });
    expect(useSessionStore.getState().sessions[0].agentConfigId).toBe("a2");
  });
});
