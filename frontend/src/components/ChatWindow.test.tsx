import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ChatWindow } from "./ChatWindow";
import { useChatStore } from "../stores/chatStore";
import type { AgentConfig, Message, RunRead, Session, TaskRead } from "../types";
import { cancelRun, interruptOrchestratorExecution, resumeOrchestratorExecution } from "../api/client";

vi.mock("../api/client", () => ({
  approveCheckpoint: vi.fn(),
  cancelRun: vi.fn(() => new Promise(() => {})),
  fetchApprovals: vi.fn(() => Promise.resolve([])),
  fetchArtifacts: vi.fn(() => Promise.resolve([])),
  fetchMessages: vi.fn(() => Promise.resolve([])),
  forwardMessages: vi.fn(() => Promise.resolve({ messages: [] })),
  fetchRuns: vi.fn(() => Promise.resolve([])),
  fetchSystemHealth: vi.fn(() => Promise.resolve(null)),
  interruptOrchestratorExecution: vi.fn(() => Promise.resolve({ status: "interrupted" })),
  rejectCheckpoint: vi.fn(),
  replyToInteractivePrompt: vi.fn(),
  resumeOrchestratorExecution: vi.fn(() => Promise.resolve({ status: "running" })),
}));

const agent: AgentConfig = {
  id: "agent-1",
  name: "验收 Agent",
  description: "",
  systemPrompt: "",
  rules: "",
  agentType: "cli_wrapper",
  cliTool: "claude_code",
  executable: "claude",
  initArgs: [],
  envVars: {},
  toolset: [],
  primarySkill: "general_coding",
  auxiliarySkills: [],
  contextPolicy: "workspace_coding",
  avatar: "preset:blue",
  status: "ready",
  isActive: true,
  createdAt: "",
  updatedAt: "",
};

const sessions: Session[] = [
  {
    id: "s-cancel",
    title: "当前对话",
    projectId: "p1",
    agentConfigId: agent.id,
    mode: "single",
    createdAt: "",
    updatedAt: "",
  },
  {
    id: "s-target",
    title: "目标对话",
    projectId: "p1",
    agentConfigId: agent.id,
    mode: "single",
    createdAt: "",
    updatedAt: "",
  },
];

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

function Harness({ onSend = vi.fn() }: { onSend?: (content: string, mentions: string[]) => void } = {}) {
  const state = useChatStore();
  return (
    <ChatWindow
      messages={state.messages}
      artifacts={state.artifacts}
      isStreaming={state.isStreaming}
      streamingError={state.streamingError}
      currentAgent={agent}
      currentSessionId="s-cancel"
      sessions={sessions}
      agents={[agent]}
      mode="single"
      routeAgents={null}
      orchestratorIntent={null}
      planSummary={null}
      mentionableAgents={[agent]}
      groupMembers={[]}
      collabTasks={[]}
      dagPhases={[]}
      chainSteps={[]}
      collabCompleted={false}
      collabSummary={null}
      draftPlan={null}
      onSend={onSend}
      onDismissError={vi.fn()}
      onReply={vi.fn()}
      onRegenerate={vi.fn()}
      onTogglePin={vi.fn()}
      onArtifactsChanged={vi.fn()}
      onRenameSession={vi.fn(() => Promise.resolve())}
      onAddGroupMember={vi.fn(() => Promise.resolve())}
      onRemoveGroupMember={vi.fn(() => Promise.resolve())}
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
    expect(screen.getByPlaceholderText("输入消息，@ 提及智能体")).toBeEnabled();
    expect(screen.getByText(/本次运行已中止成功/)).toBeInTheDocument();
    expect(screen.queryByText("正在生成")).not.toBeInTheDocument();
  });

  it("Orchestrator 运行的停止按钮会中断执行而不是取消执行", async () => {
    vi.clearAllMocks();
    const run: RunRead = {
      ...runningRun,
      mode: "orchestrated",
    };
    const message = {
      ...runningMessage(),
      metadata: {
        ...runningMessage().metadata,
        orchestratorExecution: {
          executionId: "exec-interrupt",
          sessionId: "s-cancel",
          planId: "plan-demo",
          runId: run.id,
          status: "running",
          createdAt: "",
          updatedAt: "",
          startedAt: "",
          completedAt: null,
          validation: { ok: true, errors: [], warnings: [] },
          tasks: [],
          events: [],
        },
      },
    } satisfies Message;
    resetStore();
    useChatStore.setState({
      messages: [message],
      messagesBySession: { "s-cancel": [message] },
      runs: [run],
      runsBySession: { "s-cancel": [run] },
      tasksByRun: { "run-cancel": [runningTask] },
    });

    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "停止本次运行" }));

    await waitFor(() => {
      expect(interruptOrchestratorExecution).toHaveBeenCalledWith(
        "exec-interrupt",
        "用户在界面中停止运行",
      );
    });
    expect(cancelRun).not.toHaveBeenCalled();
  });

  it("存在中断执行时，发送任意消息都会先提示恢复", async () => {
    vi.clearAllMocks();
    const onSend = vi.fn();
    const interruptedMessage: Message = {
      id: "m-execution",
      sessionId: "s-cancel",
      role: "assistant",
      content: "执行面板",
      agentName: "Orchestrator 调度器",
      createdAt: "2026-06-09T00:00:00.000Z",
      metadata: {
        orchestratorExecution: {
          executionId: "exec-interrupted",
          sessionId: "s-cancel",
          planId: "plan-demo",
          runId: "run-demo",
          status: "interrupted",
          createdAt: "",
          updatedAt: "",
          startedAt: "",
          completedAt: null,
          validation: { ok: true, errors: [], warnings: [] },
          tasks: [{
            taskId: "T4",
            title: "实现后端服务",
            goal: "",
            status: "interrupted",
            startedAt: "",
            completedAt: null,
            updatedAt: "",
            summary: null,
            runnerType: "cli",
            visibleMessageId: null,
            assignedAgentId: "agent-1",
            assignedAgentName: "后端工程师",
            dependsOn: [],
            requiredSkills: [],
            needsApproval: false,
            isBlocking: false,
            expectedOutputs: [],
            acceptanceCriteria: [],
          }],
          events: [],
        },
      },
    };
    resetStore();
    useChatStore.setState({
      messages: [interruptedMessage],
      messagesBySession: { "s-cancel": [interruptedMessage] },
    });

    render(<Harness onSend={onSend} />);

    const input = screen.getByPlaceholderText("输入消息，@ 提及智能体");
    fireEvent.change(input, { target: { value: "随便发一句新消息" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(screen.getByText("存在可恢复的计划执行")).toBeInTheDocument();
    expect(onSend).not.toHaveBeenCalled();

    const resumeButtons = screen.getAllByRole("button", { name: "继续执行" });
    fireEvent.click(resumeButtons[resumeButtons.length - 1]);
    await waitFor(() => {
      expect(resumeOrchestratorExecution).toHaveBeenCalledWith("exec-interrupted");
    });
  });
});
