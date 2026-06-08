import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
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
  rules: "",
  agentType: "cli_wrapper",
  cliTool: "codex",
  executable: "codex",
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

function renderSessionList(
  input: {
    sessions?: Session[];
    onPinSession?: (id: string, isPinned: boolean) => void;
    onArchiveSession?: (id: string, archived?: boolean) => void;
    onMuteSession?: (id: string, isMuted: boolean) => void;
  } = {},
) {
  return render(
    <SessionList
      project={project}
      sessions={input.sessions ?? sessions}
      currentSessionId="s-idle"
      agents={[agent]}
      onSelectSession={vi.fn()}
      onNewSession={vi.fn()}
      onNewGroupSession={vi.fn()}
      onDeleteSession={vi.fn()}
      onRenameSession={vi.fn()}
      onPinSession={input.onPinSession ?? vi.fn()}
      onArchiveSession={input.onArchiveSession ?? vi.fn()}
      onMuteSession={input.onMuteSession ?? vi.fn()}
    />,
  );
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

    renderSessionList();

    expect(screen.getByText("后台对话")).toBeInTheDocument();
    expect(screen.getByText("对方正在输入")).toBeInTheDocument();
    expect(screen.getByText("空闲对话")).toBeInTheDocument();
  });

  it("支持按标题搜索会话", () => {
    resetStore();
    renderSessionList();

    fireEvent.change(screen.getByPlaceholderText("搜索对话"), {
      target: { value: "空闲" },
    });

    expect(screen.queryByText("后台对话")).not.toBeInTheDocument();
    expect(screen.getByText("空闲对话")).toBeInTheDocument();
  });

  it("置顶会话显示在列表第一位并有独立置顶区块", () => {
    resetStore();
    renderSessionList({
      sessions: [
        { ...sessions[0], title: "最新普通", updatedAt: "2026-06-06T17:00:00+08:00" },
        { ...sessions[1], title: "较早置顶", isPinned: true, updatedAt: "2026-06-06T15:00:00+08:00" },
      ],
    });

    const titles = screen.getAllByText(/最新普通|较早置顶/).map((node) => node.textContent);
    expect(titles).toEqual(["较早置顶", "最新普通"]);
    expect(screen.getAllByText("置顶")).toHaveLength(2);
    expect(screen.getByText("最近对话")).toBeInTheDocument();
    expect(screen.getByLabelText("已置顶")).toBeInTheDocument();
  });

  it("会话菜单提供置顶和归档操作", () => {
    resetStore();
    const onPinSession = vi.fn();
    const onArchiveSession = vi.fn();
    renderSessionList({ onPinSession, onArchiveSession });

    fireEvent.click(screen.getAllByLabelText("会话操作")[0]);
    fireEvent.click(screen.getByText("置顶"));
    expect(onPinSession).toHaveBeenCalledWith("s-running", true);

    fireEvent.click(screen.getAllByLabelText("会话操作")[0]);
    fireEvent.click(screen.getByText("归档"));
    expect(onArchiveSession).toHaveBeenCalledWith("s-running", true);
  });

  it("展示未读数并支持免打扰切换", () => {
    resetStore();
    const onMuteSession = vi.fn();
    renderSessionList({
      onMuteSession,
      sessions: [
        { ...sessions[0], unreadCount: 7, isMuted: true },
        sessions[1],
      ],
    });

    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByLabelText("免打扰")).toBeInTheDocument();

    fireEvent.click(screen.getAllByLabelText("会话操作")[0]);
    fireEvent.click(screen.getByText("关闭免打扰"));
    expect(onMuteSession).toHaveBeenCalledWith("s-running", false);
  });

  it("归档会话集中到顶部归档文件夹并支持取消归档", () => {
    resetStore();
    const onArchiveSession = vi.fn();
    renderSessionList({
      onArchiveSession,
      sessions: [
        ...sessions,
        {
          id: "s-archived",
          title: "已收起对话",
          projectId: "p1",
          agentConfigId: "a1",
          mode: "single",
          archivedAt: "2026-06-06T17:30:00+08:00",
          createdAt: "",
          updatedAt: "2026-06-06T17:30:00+08:00",
        },
      ],
    });

    expect(screen.getByText("归档对话")).toBeInTheDocument();
    expect(screen.getByText("1 个对话已收起")).toBeInTheDocument();
    expect(screen.queryByText("已收起对话")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("归档对话"));
    expect(screen.getByText("已收起对话")).toBeInTheDocument();
    expect(screen.getByText("1 个已归档对话")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("会话操作"));
    fireEvent.click(screen.getByText("取消归档"));
    expect(onArchiveSession).toHaveBeenCalledWith("s-archived", false);
  });
});
