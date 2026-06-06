import { describe, it, expect, vi } from "vitest";
import { useChatStore } from "./chatStore";
import { useSessionStore } from "./sessionStore";
import type { AgentConfig, Artifact } from "../types";

const mockAgent: AgentConfig = {
  id: "a1", name: "测试 Agent", description: "", systemPrompt: "",
  agentType: "cli_wrapper", cliTool: "claude_code", executable: "claude",
  initArgs: ["-p"], envVars: {}, status: "ready",
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

  it("chatStore 取消当前流会 abort SSE 并解除全局输入占用", () => {
    const abort = vi.fn();
    useChatStore.getState().startStreamRun("run-cancel");
    useChatStore.getState().setActiveStreamAbort(abort);
    useChatStore.setState({ activeProgress: "running" });

    useChatStore.getState().cancelActiveStream();

    expect(abort).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().isStreaming).toBe(false);
    expect(useChatStore.getState().activeRunId).toBeNull();
    expect(useChatStore.getState().activeStreamKey).toBeNull();
    expect(useChatStore.getState().activeProgress).toBeNull();
  });

  it("chatStore 本地中止 run 时同步回退消息、任务和执行轨迹", () => {
    const abort = vi.fn();
    useChatStore.setState({
      currentSessionId: "s-cancel",
      activeStreamKey: "stream-cancel",
      activeRunId: "run-cancel",
      activeStreamAbort: abort,
      isStreaming: true,
      activeProgress: "running",
      messages: [{
        id: "m-cancel",
        sessionId: "s-cancel",
        role: "assistant",
        content: "working",
        agentName: "测试 Agent",
        createdAt: "",
        metadata: {
          runId: "run-cancel",
          executionTrace: {
            status: "running",
            agentName: "测试 Agent",
            cliTool: "claude_code",
            startedAt: "2026-06-06T00:00:00.000Z",
            completedAt: null,
            processId: "proc-1",
            exitCode: null,
            items: [{
              id: "trace-1",
              kind: "process",
              text: "正在执行",
              source: "system",
              chunkType: "process",
              processId: "proc-1",
              timestamp: "2026-06-06T00:00:00.000Z",
            }],
          },
        },
      }],
      runs: [{
        id: "run-cancel",
        sessionId: "s-cancel",
        mode: "single",
        status: "running",
        currentMessageId: "m-cancel",
        startedAt: "2026-06-06T00:00:00.000Z",
        updatedAt: "2026-06-06T00:00:00.000Z",
      }],
      tasksByRun: {
        "run-cancel": [{
          id: "task-cancel",
          runId: "run-cancel",
          sessionId: "s-cancel",
          name: "primary",
          role: "executor",
          status: "running",
          dependsOn: [],
        }],
      },
    });

    useChatStore.getState().cancelRunLocally("run-cancel", "manual stop");

    const state = useChatStore.getState();
    expect(abort).toHaveBeenCalledTimes(1);
    expect(state.isStreaming).toBe(false);
    expect(state.activeRunId).toBeNull();
    expect(state.activeStreamKey).toBeNull();
    expect(state.runs[0].status).toBe("cancelled");
    expect(state.tasksByRun["run-cancel"][0].status).toBe("cancelled");
    expect(state.messages[0].metadata?.runStatus).toBe("cancelled");
    expect(state.messages[0].metadata?.executionTrace?.status).toBe("cancelled");
    expect(state.messages.some((message) => message.content.includes("本次运行已中止成功"))).toBe(true);
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
