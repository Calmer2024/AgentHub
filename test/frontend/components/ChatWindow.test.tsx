import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ChatWindow } from "../../../frontend/src/components/ChatWindow";
import { useChatStore } from "../../../frontend/src/stores/chatStore";
import { useToastStore } from "../../../frontend/src/stores/toastStore";
import type { AgentConfig, Message, RunRead, Session, TaskRead } from "../../../frontend/src/types";
import {
  cancelRun,
  forwardMessages,
  interruptOrchestratorExecution,
  resumeOrchestratorExecution,
} from "../../../frontend/src/api/client";

vi.mock("../../../frontend/src/api/client", () => ({
  cancelRun: vi.fn(() => new Promise(() => {})),
  fetchArtifacts: vi.fn(() => Promise.resolve([])),
  fetchMessages: vi.fn(() => Promise.resolve([])),
  forwardMessages: vi.fn(() => Promise.resolve({ messages: [] })),
  fetchRuns: vi.fn(() => Promise.resolve([])),
  fetchSessionDiagnosticLogs: vi.fn(() => Promise.resolve({
    session: { id: "s-cancel", title: "当前对话", mode: "single", projectId: "p1", createdAt: "", updatedAt: "" },
    generatedAt: "2026-09-16T20:00:00+08:00",
    counts: { entries: 1, messages: 0, runs: 0, tasks: 0, processes: 0, artifacts: 0, plans: 0 },
    entries: [{ id: "session:s-cancel", timestamp: "2026-09-16T20:00:00+08:00", level: "info", category: "session", source: "AgentHub", title: "会话已创建", message: "当前对话", details: { sessionId: "s-cancel" } }],
  })),
  interruptOrchestratorExecution: vi.fn(() => Promise.resolve({ status: "interrupted" })),
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
    systemHealth: null,
    healthBlockingError: null,
    messagesBySession: {},
    artifactsBySession: {},
    runsBySession: {},
    runtimeBySession: {},
    streamingErrorBySession: {},
    activeStreamsByKey: {},
    collabSnapshots: {},
  });
  useToastStore.setState({ toasts: [] });
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

function Harness({
  onSend = vi.fn(),
  onToggleProjectFiles,
  projectFilesOpen,
}: {
  onSend?: (content: string, mentions: string[]) => void;
  onToggleProjectFiles?: () => void;
  projectFilesOpen?: boolean;
} = {}) {
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
      routeType={null}
      routeReason={null}
      mentionableAgents={[agent]}
      groupMembers={[]}
      onSend={onSend}
      onDismissError={vi.fn()}
      onReply={vi.fn()}
      onRegenerate={vi.fn()}
      onTogglePin={vi.fn()}
      onArtifactsChanged={vi.fn()}
      onToggleProjectFiles={onToggleProjectFiles}
      projectFilesOpen={projectFilesOpen}
      onRenameSession={vi.fn(() => Promise.resolve())}
      onAddGroupMember={vi.fn(() => Promise.resolve())}
      onRemoveGroupMember={vi.fn(() => Promise.resolve())}
    />
  );
}

describe("ChatWindow runtime cancel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
    });
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

    expect(screen.getByText(/对方正在输入/)).toBeInTheDocument();
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

  it("当前空回复占位在流式运行中不显示冗余等待态", () => {
    resetStore();
    useChatStore.setState({
      messages: [{
        id: "m-pending",
        sessionId: "s-cancel",
        role: "assistant",
        content: "",
        agentName: agent.name,
        createdAt: "2026-06-06T00:00:00.000Z",
      }],
      messagesBySession: {
        "s-cancel": [{
          id: "m-pending",
          sessionId: "s-cancel",
          role: "assistant",
          content: "",
          agentName: agent.name,
          createdAt: "2026-06-06T00:00:00.000Z",
        }],
      },
      isStreaming: true,
      activeStreamKey: "stream-pending",
      activeStreamsByKey: {
        "stream-pending": { sessionId: "s-cancel", abort: vi.fn() },
      },
      runtimeBySession: {
        "s-cancel": {
          isStreaming: true,
          activeStreamKey: "stream-pending",
          activeRunId: null,
          activeStreamAbort: vi.fn(),
          activeProgress: null,
        },
      },
    });

    render(<Harness />);

    expect(screen.queryByLabelText("正在等待 Agent 回复")).not.toBeInTheDocument();
    expect(screen.queryByText("未返回可见回复")).not.toBeInTheDocument();
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

  it("复制消息内容时写入剪贴板并提示成功", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    const message: Message = {
      id: "m-copy",
      sessionId: "s-cancel",
      role: "assistant",
      content: "需要复制的内容",
      agentName: agent.name,
      createdAt: "2026-06-11T00:00:00.000Z",
    };
    resetStore();
    useChatStore.setState({
      messages: [message],
      messagesBySession: { "s-cancel": [message] },
    });

    render(<Harness />);

    fireEvent.contextMenu(screen.getByText("需要复制的内容"));
    fireEvent.click(screen.getByRole("menuitem", { name: "复制" }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith("需要复制的内容");
    });
    const copyToasts = useToastStore.getState().toasts;
    expect(copyToasts[copyToasts.length - 1]?.title).toBe("已复制到剪贴板");
  });

  it("日志按钮切换会话诊断视图，再次点击回到对话", async () => {
    const onToggleProjectFiles = vi.fn();
    resetStore();

    render(<Harness onToggleProjectFiles={onToggleProjectFiles} />);

    const logButton = screen.getByRole("button", { name: "查看会话诊断日志" });
    expect(logButton).toHaveTextContent("");
    fireEvent.click(logButton);
    expect(await screen.findByRole("region", { name: "会话诊断日志" })).toBeInTheDocument();
    expect(screen.getByText("s-cancel")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("搜索内容、来源或任意关联 ID")).toHaveClass("agenthub-search-field");

    const levelFilter = screen.getByRole("button", { name: "日志级别" });
    expect(levelFilter).toHaveClass("agenthub-filter-trigger");
    fireEvent.click(levelFilter);
    expect(await screen.findByRole("option", { name: "输入" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "返回对话" }));
    expect(screen.queryByRole("region", { name: "会话诊断日志" })).not.toBeInTheDocument();

    const projectFilesButton = screen.getByRole("button", { name: "打开项目资源管理器" });
    const artifactsButton = screen.getByRole("button", { name: "会话文件，0 个产物" });
    expect(
      projectFilesButton.compareDocumentPosition(artifactsButton) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    fireEvent.click(projectFilesButton);
    expect(onToggleProjectFiles).toHaveBeenCalledTimes(1);
  });

  it("空白会话提供可直接落笔的任务建议，并可一键写入输入框", async () => {
    resetStore();

    render(<Harness />);

    expect(screen.getByText("和 验收 Agent 开始一个任务")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /设计实现方案/ }));
    });

    await waitFor(() => {
      expect(
        screen.getByDisplayValue("请先理解当前项目，然后给我一份实现方案，包含改动点和验收标准。"),
      ).toHaveFocus();
    });
  });

  it("转发成功后把返回消息写入目标会话缓存", async () => {
    vi.clearAllMocks();
    const sourceMessage: Message = {
      id: "m-source",
      sessionId: "s-cancel",
      role: "user",
      content: "待转发消息",
      agentName: null,
      sourceType: "user",
      sourceName: "用户",
      createdAt: "2026-06-11T00:00:00.000Z",
    };
    const forwardedMessage: Message = {
      id: "m-forwarded",
      sessionId: "s-target",
      role: "user",
      content: "转发自 用户：\n\n待转发消息",
      agentName: null,
      sourceType: "user",
      sourceName: "用户",
      metadata: { forwarded: true },
      createdAt: "2026-06-11T00:00:01.000Z",
    };
    vi.mocked(forwardMessages).mockResolvedValueOnce({ messages: [forwardedMessage] });
    resetStore();
    useChatStore.setState({
      messages: [sourceMessage],
      messagesBySession: {
        "s-cancel": [sourceMessage],
        "s-target": [],
      },
    });

    render(<Harness />);

    fireEvent.contextMenu(screen.getByText("待转发消息"));
    fireEvent.click(screen.getByRole("menuitem", { name: "转发" }));
    fireEvent.click(screen.getByRole("button", { name: /目标对话/ }));
    const sendButtons = screen.getAllByRole("button", { name: "发送" });
    fireEvent.click(sendButtons[sendButtons.length - 1]);

    await waitFor(() => {
      expect(forwardMessages).toHaveBeenCalledWith(["m-source"], ["s-target"]);
    });
    await waitFor(() => {
      expect(useChatStore.getState().messagesBySession["s-target"]).toEqual([forwardedMessage]);
    });
    const forwardToasts = useToastStore.getState().toasts;
    expect(forwardToasts[forwardToasts.length - 1]?.title).toBe("消息已转发");
  });
});
