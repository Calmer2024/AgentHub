import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ChatWindow } from "./ChatWindow";
import { useChatStore } from "../stores/chatStore";
import type { AgentConfig, Message, RunRead, TaskRead } from "../types";

vi.mock("../api/client", () => ({
  approveCheckpoint: vi.fn(),
  cancelRun: vi.fn(() => new Promise(() => {})),
  fetchApprovals: vi.fn(() => Promise.resolve([])),
  fetchArtifacts: vi.fn(() => Promise.resolve([])),
  fetchMessages: vi.fn(() => Promise.resolve([])),
  fetchRuns: vi.fn(() => Promise.resolve([])),
  fetchSystemHealth: vi.fn(() => Promise.resolve(null)),
  rejectCheckpoint: vi.fn(),
  replyToInteractivePrompt: vi.fn(),
}));

const agent: AgentConfig = {
  id: "agent-1",
  name: "验收 Agent",
  description: "",
  systemPrompt: "",
  agentType: "cli_wrapper",
  cliTool: "claude_code",
  executable: "claude",
  initArgs: [],
  envVars: {},
  status: "ready",
  isActive: true,
  createdAt: "",
  updatedAt: "",
};

function resetStore() {
  useChatStore.setState({
    currentSessionId: "s-cancel",
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

function runningMessage(): Message {
  return {
    id: "m-cancel",
    sessionId: "s-cancel",
    role: "assistant",
    content: "仍在处理",
    agentName: agent.name,
    createdAt: "2026-06-06T00:00:00.000Z",
    metadata: {
      runId: "run-cancel",
      executionTrace: {
        status: "running",
        agentName: agent.name,
        cliTool: agent.cliTool,
        startedAt: "2026-06-06T00:00:00.000Z",
        completedAt: null,
        processId: "proc-1",
        exitCode: null,
        items: [{
          id: "trace-1",
          kind: "process",
          text: "正在启动",
          source: "system",
          chunkType: "process",
          processId: "proc-1",
          timestamp: "2026-06-06T00:00:00.000Z",
        }],
      },
    },
  };
}

const runningRun: RunRead = {
  id: "run-cancel",
  sessionId: "s-cancel",
  mode: "single",
  status: "running",
  currentMessageId: "m-cancel",
  startedAt: "2026-06-06T00:00:00.000Z",
  updatedAt: "2026-06-06T00:00:00.000Z",
};

const runningTask: TaskRead = {
  id: "task-cancel",
  runId: "run-cancel",
  sessionId: "s-cancel",
  name: "primary",
  role: "executor",
  status: "running",
  dependsOn: [],
};

function Harness() {
  const state = useChatStore();
  return (
    <ChatWindow
      messages={state.messages}
      artifacts={state.artifacts}
      isStreaming={state.isStreaming}
      streamingError={state.streamingError}
      currentAgent={agent}
      currentSessionId="s-cancel"
      agents={[agent]}
      mode="single"
      routeAgents={null}
      orchestratorIntent={null}
      planSummary={null}
      mentionableAgents={[agent]}
      collabTasks={[]}
      dagPhases={[]}
      chainSteps={[]}
      collabCompleted={false}
      collabSummary={null}
      onSend={vi.fn()}
      onDismissError={vi.fn()}
      onReply={vi.fn()}
      onRegenerate={vi.fn()}
      onTogglePin={vi.fn()}
      onArtifactsChanged={vi.fn()}
    />
  );
}

describe("ChatWindow runtime cancel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetStore();
  });

  it("后端取消请求未返回时，点击停止也会立即中止本地回复并解锁输入框", async () => {
    const abort = vi.fn();
    resetStore();
    useChatStore.setState({
      messages: [runningMessage()],
      messagesBySession: { "s-cancel": [runningMessage()] },
      runs: [runningRun],
      runsBySession: { "s-cancel": [runningRun] },
      tasksByRun: { "run-cancel": [runningTask] },
      isStreaming: true,
      activeStreamKey: "stream-cancel",
      activeRunId: "run-cancel",
      activeStreamAbort: abort,
      activeProgress: "running",
      activeStreamsByKey: {
        "stream-cancel": { sessionId: "s-cancel", abort },
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
    });

    render(<Harness />);

    expect(screen.getByText("对方正在输入")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("当前对话正在输出...")).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "停止本次运行" }));

    await waitFor(() => {
      expect(screen.queryByText("对方正在输入")).not.toBeInTheDocument();
    });
    expect(abort).toHaveBeenCalledTimes(1);
    expect(screen.getByPlaceholderText("输入消息，@ 提及 Agent")).toBeEnabled();
    expect(screen.getByText(/本次运行已中止成功/)).toBeInTheDocument();
    expect(screen.queryByText("正在生成")).not.toBeInTheDocument();
  });
});
