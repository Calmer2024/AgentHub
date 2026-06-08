import { afterEach, describe, it, expect, vi } from "vitest";
import { useChatStore } from "./chatStore";
import { useSessionStore } from "./sessionStore";
import type { AgentConfig, Artifact } from "../types";

const mockAgent: AgentConfig = {
  id: "a1", name: "测试 Agent", description: "", systemPrompt: "",
  rules: "",
  agentType: "cli_wrapper", cliTool: "claude_code", executable: "claude",
  initArgs: ["-p"], envVars: {}, status: "ready",
  toolset: [],
  primarySkill: "general_coding", auxiliarySkills: ["workspace_editing"],
  avatar: "preset:blue",
  contextPolicy: "workspace_coding",
  isActive: true, createdAt: "", updatedAt: "",
};

function resetChatStore() {
  useChatStore.setState({
    currentSessionId: null,
    messages: [],
    artifacts: [],
    isStreaming: false,
    activeStreamKey: null,
    activeRunId: null,
    activeStreamAbort: null,
    latestRunId: null,
    streamingError: null,
    replyTarget: null,
    codeReference: null,
    activeProgress: null,
    interactivePrompts: [],
    runs: [],
    tasksByRun: {},
    approvals: [],
    systemHealth: null,
    healthBlockingError: null,
    messagesBySession: {},
    artifactsBySession: {},
    runsBySession: {},
    approvalsBySession: {},
    runtimeBySession: {},
    streamingErrorBySession: {},
    activeStreamsByKey: {},
    collabSnapshots: {},
  });
}

describe("Chat Store (split)", () => {
  afterEach(() => {
    resetChatStore();
  });

  it("chatStore 初始状态 messages 为空数组", () => {
    expect(useChatStore.getState().messages).toEqual([]);
  });

  it("chatStore 初始 isStreaming 为 false", () => {
    expect(useChatStore.getState().isStreaming).toBe(false);
  });

  it("chatStore appendStreamingToken", () => {
    useChatStore.setState({
      currentSessionId: "s",
      messages: [{ id: "1", sessionId: "s", role: "assistant", content: "Hi", agentName: null, createdAt: "" }],
      messagesBySession: {
        s: [{ id: "1", sessionId: "s", role: "assistant", content: "Hi", agentName: null, createdAt: "" }],
      },
      isStreaming: true,
      runtimeBySession: {
        s: {
          isStreaming: true,
          activeStreamKey: "stream-s",
          activeRunId: null,
          activeStreamAbort: null,
          activeProgress: null,
        },
      },
    });
    useChatStore.getState().appendStreamingToken(" there");
    expect(useChatStore.getState().messages[0].content).toBe("Hi there");
  });

  it("chatStore 可把流式 token 固定写入指定消息，避免写到最后一个气泡", () => {
    useChatStore.setState({
      currentSessionId: "s",
      messages: [
        { id: "target", sessionId: "s", role: "assistant", content: "A", agentName: null, createdAt: "" },
        { id: "latest", sessionId: "s", role: "assistant", content: "B", agentName: null, createdAt: "" },
      ],
      messagesBySession: {
        s: [
          { id: "target", sessionId: "s", role: "assistant", content: "A", agentName: null, createdAt: "" },
          { id: "latest", sessionId: "s", role: "assistant", content: "B", agentName: null, createdAt: "" },
        ],
      },
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

  it("chatStore 对同一文件产物只保留最新版本链头", () => {
    const artifact = (
      id: string,
      version: number,
      createdAt: string,
      parentArtifactId: string | null = null,
    ): Artifact => ({
      id,
      sessionId: "s-current",
      messageId: `m-${id}`,
      projectId: "p1",
      type: "web_preview",
      title: "index.html",
      content: id,
      status: "ready",
      version,
      parentArtifactId,
      filePath: "index.html",
      createdAt,
    });
    useChatStore.setState({ currentSessionId: "s-current" });

    useChatStore.getState().setArtifactsForSession("s-current", [
      artifact("v1", 1, "2026-06-06T09:00:00.000+08:00"),
      artifact("v2", 2, "2026-06-06T09:01:00.000+08:00", "v1"),
      artifact("duplicate-v1", 1, "2026-06-06T09:02:00.000+08:00"),
    ]);

    expect(useChatStore.getState().artifacts.map((item) => item.id)).toEqual(["v2"]);
  });

  it("chatStore 实时 upsert 同一文件新版本会替换旧产物卡片", () => {
    const base: Artifact = {
      id: "a1",
      sessionId: "s-current",
      messageId: "m1",
      projectId: "p1",
      type: "web_preview",
      title: "index.html",
      content: "old",
      status: "ready",
      version: 1,
      filePath: "index.html",
      createdAt: "2026-06-06T09:00:00.000+08:00",
    };
    useChatStore.setState({
      currentSessionId: "s-current",
      artifacts: [base],
      artifactsBySession: { "s-current": [base] },
    });

    useChatStore.getState().upsertArtifact({
      ...base,
      id: "a2",
      messageId: "m2",
      content: "new",
      version: 2,
      parentArtifactId: "a1",
      createdAt: "2026-06-06T09:01:00.000+08:00",
    });

    expect(useChatStore.getState().artifacts).toHaveLength(1);
    expect(useChatStore.getState().artifacts[0].id).toBe("a2");
    expect(useChatStore.getState().artifacts[0].version).toBe(2);
  });

  it("chatStore 只允许当前 run 结束 streaming", () => {
    useChatStore.setState({ currentSessionId: "s-run" });
    useChatStore.getState().startStreamRun("s-run", "run-new");
    useChatStore.getState().finishStreamRun("run-old");

    expect(useChatStore.getState().isStreaming).toBe(true);
    expect(useChatStore.getState().activeStreamKey).toBe("run-new");
    expect(useChatStore.getState().latestRunId).toBe("run-new");

    useChatStore.getState().finishStreamRun("run-new");

    expect(useChatStore.getState().isStreaming).toBe(false);
    expect(useChatStore.getState().activeRunId).toBeNull();
    expect(useChatStore.getState().latestRunId).toBe("run-new");
  });

  it("chatStore 取消当前流会 abort SSE 并解除全局输入占用", () => {
    const abort = vi.fn();
    useChatStore.setState({ currentSessionId: "s-cancel" });
    useChatStore.getState().startStreamRun("s-cancel", "run-cancel", abort);
    useChatStore.setState({
      activeProgress: "running",
      runtimeBySession: {
        "s-cancel": {
          ...useChatStore.getState().getSessionRuntime("s-cancel"),
          activeProgress: "running",
        },
      },
    });

    useChatStore.getState().cancelActiveStream();

    expect(abort).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().isStreaming).toBe(false);
    expect(useChatStore.getState().activeRunId).toBeNull();
    expect(useChatStore.getState().activeStreamKey).toBeNull();
    expect(useChatStore.getState().activeProgress).toBeNull();
  });

  it("chatStore 切换会话时保留后台会话 streaming runtime", () => {
    const abort = vi.fn();
    useChatStore.setState({
      currentSessionId: "s-bg",
      messagesBySession: {
        "s-bg": [{ id: "m-bg", sessionId: "s-bg", role: "assistant", content: "", agentName: null, createdAt: "" }],
      },
      messages: [{ id: "m-bg", sessionId: "s-bg", role: "assistant", content: "", agentName: null, createdAt: "" }],
    });
    useChatStore.getState().startStreamRun("s-bg", "stream-bg", abort);

    useChatStore.getState().setCurrentSessionId("s-front");
    useChatStore.getState().setMessagesForSession("s-front", []);

    expect(useChatStore.getState().isStreaming).toBe(false);
    expect(useChatStore.getState().isSessionStreaming("s-bg")).toBe(true);

    useChatStore.getState().appendStreamingTokenToSessionMessage("s-bg", "m-bg", "后台输出");
    expect(useChatStore.getState().messages).toEqual([]);

    useChatStore.getState().setCurrentSessionId("s-bg");
    expect(useChatStore.getState().isStreaming).toBe(true);
    expect(useChatStore.getState().activeStreamAbort).toBe(abort);
    expect(useChatStore.getState().messages[0].content).toBe("后台输出");
  });

  it("chatStore 允许多个不同会话同时保留独立 streaming runtime", () => {
    const abortA = vi.fn();
    const abortB = vi.fn();
    useChatStore.setState({
      currentSessionId: "s-a",
      messagesBySession: {
        "s-a": [{ id: "m-a", sessionId: "s-a", role: "assistant", content: "", agentName: null, createdAt: "" }],
        "s-b": [{ id: "m-b", sessionId: "s-b", role: "assistant", content: "", agentName: null, createdAt: "" }],
      },
      messages: [{ id: "m-a", sessionId: "s-a", role: "assistant", content: "", agentName: null, createdAt: "" }],
    });

    useChatStore.getState().startStreamRun("s-a", "stream-a", abortA);
    useChatStore.getState().startStreamRun("s-b", "stream-b", abortB);

    expect(useChatStore.getState().isSessionStreaming("s-a")).toBe(true);
    expect(useChatStore.getState().isSessionStreaming("s-b")).toBe(true);
    expect(Object.keys(useChatStore.getState().activeStreamsByKey).sort()).toEqual(["stream-a", "stream-b"]);

    useChatStore.getState().appendStreamingTokenToSessionMessage("s-b", "m-b", "B");
    expect(useChatStore.getState().messages[0].content).toBe("");

    useChatStore.getState().setCurrentSessionId("s-b");
    expect(useChatStore.getState().messages[0].content).toBe("B");
    expect(useChatStore.getState().activeStreamAbort).toBe(abortB);
  });

  it("chatStore hydrate 时不会覆盖隐藏会话里正在输出的本地气泡", () => {
    useChatStore.setState({
      currentSessionId: "s-front",
      messages: [],
      messagesBySession: {
        "s-bg": [{
          id: "local-ai-bg",
          sessionId: "s-bg",
          role: "assistant",
          content: "半截回复",
          agentName: null,
          createdAt: "",
        }],
      },
      runtimeBySession: {
        "s-bg": {
          isStreaming: true,
          activeStreamKey: "stream-bg",
          activeRunId: "run-bg",
          activeStreamAbort: null,
          activeProgress: null,
        },
      },
      runsBySession: {
        "s-bg": [{
          id: "run-bg",
          sessionId: "s-bg",
          mode: "single",
          status: "running",
          currentMessageId: "local-ai-bg",
          startedAt: "2026-06-06T00:00:00.000",
          updatedAt: "2026-06-06T00:00:00.000",
        }],
      },
    });

    useChatStore.getState().setMessagesForSession("s-bg", []);

    expect(useChatStore.getState().messagesBySession["s-bg"][0].content).toBe("半截回复");
    expect(useChatStore.getState().messages).toEqual([]);
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
      activeStreamsByKey: {
        "stream-cancel": { sessionId: "s-cancel", abort },
      },
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
      messagesBySession: {
        "s-cancel": [{
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
      },
      runs: [{
        id: "run-cancel",
        sessionId: "s-cancel",
        mode: "single",
        status: "running",
        currentMessageId: "m-cancel",
        startedAt: "2026-06-06T00:00:00.000Z",
        updatedAt: "2026-06-06T00:00:00.000Z",
      }],
      runsBySession: {
        "s-cancel": [{
          id: "run-cancel",
          sessionId: "s-cancel",
          mode: "single",
          status: "running",
          currentMessageId: "m-cancel",
          startedAt: "2026-06-06T00:00:00.000Z",
          updatedAt: "2026-06-06T00:00:00.000Z",
        }],
      },
      runtimeBySession: {
        "s-cancel": {
          isStreaming: true,
          activeStreamKey: "stream-cancel",
          activeRunId: "run-cancel",
          activeStreamAbort: abort,
          activeProgress: "running",
        },
      },
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
      draftPlan: null,
    });
    expect(useChatStore.getState().getCollab("s-dag").dagPhases[0].phase).toBe(0);
    expect(useChatStore.getState().getCollab("s-dag").planSummary).toContain("架构师");
  });

  it("服务端结构化调度计划水合后替换本地 planner 占位气泡", () => {
    useChatStore.setState({
      currentSessionId: "s-plan",
      messages: [
        {
          id: "local-agent-orchestrator-0-draft",
          sessionId: "s-plan",
          role: "assistant",
          content: "{ raw json }",
          agentName: "Orchestrator 调度器",
          sourceType: "agent",
          sourceId: "agent-orchestrator",
          sourceName: "Orchestrator 调度器",
          agentRole: "planner",
          phase: 0,
          taskName: "draft plan",
          isCollaborating: true,
          createdAt: "",
          metadata: {
            executionTrace: {
              status: "running",
              agentName: "Orchestrator 调度器",
              cliTool: "codex",
              workspacePath: null,
              startedAt: "",
              completedAt: null,
              processId: "proc-1",
              exitCode: null,
              items: [],
            },
          },
        },
      ],
      messagesBySession: {
        "s-plan": [
          {
            id: "local-agent-orchestrator-0-draft",
            sessionId: "s-plan",
            role: "assistant",
            content: "{ raw json }",
            agentName: "Orchestrator 调度器",
            sourceType: "agent",
            sourceId: "agent-orchestrator",
            sourceName: "Orchestrator 调度器",
            agentRole: "planner",
            phase: 0,
            taskName: "draft plan",
            isCollaborating: true,
            createdAt: "",
          },
        ],
      },
      runtimeBySession: {
        "s-plan": {
          isStreaming: true,
          activeStreamKey: "stream-s-plan",
          activeRunId: null,
          activeStreamAbort: null,
          activeProgress: null,
        },
      },
    });

    useChatStore.getState().setMessagesForSession("s-plan", [
      {
        id: "msg-plan-server",
        sessionId: "s-plan",
        role: "assistant",
        content: "{ normalized json }",
        agentName: "Orchestrator 调度器",
        sourceType: "agent",
        sourceId: "agent-orchestrator",
        sourceName: "Orchestrator 调度器",
        createdAt: "",
        metadata: {
          orchestratorPlan: {
            ok: true,
            normalizedPlan: {
              plan_id: "plan_001",
              status: "draft",
              execution_policy: { mode: "plan_only", requires_approval_before_execution: true },
              tasks: [],
              execution_strategy: { parallelizable_groups: [], critical_path: [] },
            },
            validation: { ok: true, errors: [], warnings: [] },
            visualization: { mermaid: "graph TD" },
          },
        },
      },
    ]);

    const messages = useChatStore.getState().messages;
    expect(messages).toHaveLength(1);
    expect(messages[0].id).toBe("msg-plan-server");
    expect(messages[0].metadata?.orchestratorPlan?.ok).toBe(true);
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
