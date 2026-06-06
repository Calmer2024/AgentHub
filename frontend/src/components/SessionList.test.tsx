import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SessionList } from "./SessionList";
import { useChatStore } from "../stores/chatStore";
import type { AgentConfig, Project, Session } from "../types";

const project: Project = {
  id: "p1",
  name: "项目一",
  workspacePath: "D:\\AgentHub\\workspaces\\p1",
  status: "ready",
  fileCount: 0,
  totalSizeBytes: 0,
  createdAt: "",
};

const agent: AgentConfig = {
  id: "a1",
  name: "Codex",
  description: "",
  systemPrompt: "",
  agentType: "cli_wrapper",
  cliTool: "codex",
  executable: "codex",
  initArgs: [],
  envVars: {},
  status: "ready",
  isActive: true,
  createdAt: "",
  updatedAt: "",
};

const sessions: Session[] = [
  {
    id: "s-running",
    title: "后台对话",
    projectId: "p1",
    agentConfigId: "a1",
    mode: "single",
    createdAt: "",
    updatedAt: "2026-06-06T16:00:00+08:00",
  },
  {
    id: "s-idle",
    title: "空闲对话",
    projectId: "p1",
    agentConfigId: "a1",
    mode: "single",
    createdAt: "",
    updatedAt: "2026-06-06T15:00:00+08:00",
  },
];

function resetStore() {
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

describe("SessionList", () => {
  afterEach(() => {
    resetStore();
  });

  it("展示后台运行会话的输入状态", () => {
    resetStore();
    useChatStore.setState({
      runtimeBySession: {
        "s-running": {
          isStreaming: true,
          activeStreamKey: "stream-running",
          activeRunId: "run-running",
          activeStreamAbort: null,
          activeProgress: null,
        },
      },
    });

    render(
      <SessionList
        project={project}
        sessions={sessions}
        currentSessionId="s-idle"
        agents={[agent]}
        onSelectSession={vi.fn()}
        onNewSession={vi.fn()}
        onNewGroupSession={vi.fn()}
        onDeleteSession={vi.fn()}
        onRenameSession={vi.fn()}
      />,
    );

    expect(screen.getByText("后台对话")).toBeInTheDocument();
    expect(screen.getByText("对方正在输入")).toBeInTheDocument();
    expect(screen.getByText("空闲对话")).toBeInTheDocument();
  });
});
