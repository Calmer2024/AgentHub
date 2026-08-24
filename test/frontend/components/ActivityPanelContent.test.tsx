import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ActivityPanelContent } from "../../../frontend/src/components/ActivityPanelContent";
import type { AgentConfig, Project, Session } from "../../../frontend/src/types";

vi.mock("../../../frontend/src/api/client", () => ({
  fetchSessions: vi.fn().mockResolvedValue([]),
}));

const projects: Project[] = [
  {
    id: "alpha",
    name: "Alpha",
    workspaceMode: "local",
    status: "ready",
    fileCount: 0,
    totalSizeBytes: 0,
    createdAt: "2026-07-15T10:00:00Z",
  },
  {
    id: "beta",
    name: "Beta",
    workspaceMode: "local",
    status: "ready",
    fileCount: 0,
    totalSizeBytes: 0,
    createdAt: "2026-07-15T09:00:00Z",
  },
];

const agent: AgentConfig = {
  id: "agent-1",
  name: "前端工程师",
  description: "负责界面实现",
  systemPrompt: "",
  rules: "",
  agentType: "cli_wrapper",
  cliTool: "codex",
  executable: "codex",
  initArgs: [],
  envVars: {},
  toolset: [],
  primarySkill: "",
  auxiliarySkills: [],
  contextPolicy: "workspace",
  avatar: "",
  status: "ready",
  isActive: true,
  createdAt: "2026-07-15T10:00:00Z",
  updatedAt: "2026-07-15T10:00:00Z",
};

describe("项目列表拖拽", () => {
  beforeEach(() => window.localStorage.clear());

  it("整条项目行可拖动，且不渲染独立拖拽按钮", () => {
    render(
      <ActivityPanelContent
        panel="projects"
        project={null}
        projects={projects}
        currentProjectId={null}
        currentTeamId={null}
        sessions={[]}
        currentSessionId={null}
        sessionsLoading={false}
        projectsLoading={false}
        creatingProject={false}
        agents={[]}
        canCreateLocalProject
        canCreateCloudProject={false}
        onSelectSession={vi.fn()}
        onNewSession={vi.fn()}
        onNewGroupSession={vi.fn()}
        onDeleteSession={vi.fn()}
        onRenameSession={vi.fn()}
        onPinSession={vi.fn()}
        onArchiveSession={vi.fn()}
        onMuteSession={vi.fn()}
        onSelectProject={vi.fn()}
        onSelectProjectSession={vi.fn()}
        onCreateBlankProject={vi.fn()}
        onCreateCloudProject={vi.fn()}
        onPickExistingFolder={vi.fn()}
        onArchiveProject={vi.fn()}
        onRenameProject={vi.fn()}
        onDeleteProject={vi.fn()}
        onNewProjectSession={vi.fn()}
        onStartAgentChat={vi.fn()}
        onCreateAgent={vi.fn()}
        onEditAgent={vi.fn()}
        onDeleteAgent={vi.fn()}
      />,
    );

    const alpha = screen.getByLabelText("拖动 Alpha 调整顺序");
    const beta = screen.getByLabelText("拖动 Beta 调整顺序");
    expect(alpha).toHaveAttribute("draggable", "true");
    expect(screen.queryByTitle(/拖动排序/)).not.toBeInTheDocument();

    let draggedId = "";
    const dataTransfer = {
      effectAllowed: "none",
      dropEffect: "none",
      setData: (_type: string, value: string) => { draggedId = value; },
      getData: () => draggedId,
    };
    fireEvent.dragStart(alpha, { dataTransfer });
    fireEvent.dragEnter(beta, { dataTransfer });
    fireEvent.dragOver(beta, { dataTransfer });
    fireEvent.drop(beta, { dataTransfer });

    const labels = screen.getAllByLabelText(/^拖动 .* 调整顺序$/).map((node) => node.getAttribute("aria-label"));
    expect(labels).toEqual(["拖动 Beta 调整顺序", "拖动 Alpha 调整顺序"]);
  });

  it("项目可展开收起对话，并提供重命名和删除按钮但不提供对话置顶", async () => {
    const pinnedSession: Session = {
      id: "pinned-session",
      title: "发布准备",
      projectId: "alpha",
      agentConfigId: null,
      mode: "single",
      isPinned: true,
      createdAt: "2026-07-15T10:00:00Z",
      updatedAt: "2026-07-16T10:00:00Z",
    };
    const regularSession: Session = {
      ...pinnedSession,
      id: "regular-session",
      title: "普通对话",
      isPinned: false,
      updatedAt: "2026-07-15T11:00:00Z",
    };
    const onRenameSession = vi.fn();
    const onPinSession = vi.fn();
    const onDeleteSession = vi.fn();

    render(
      <ActivityPanelContent
        panel="projects"
        project={projects[0]}
        projects={projects}
        currentProjectId="alpha"
        currentTeamId={null}
        sessions={[pinnedSession, regularSession]}
        currentSessionId={null}
        sessionsLoading={false}
        projectsLoading={false}
        creatingProject={false}
        agents={[]}
        canCreateLocalProject
        canCreateCloudProject={false}
        onSelectSession={vi.fn()}
        onNewSession={vi.fn()}
        onNewGroupSession={vi.fn()}
        onDeleteSession={onDeleteSession}
        onRenameSession={onRenameSession}
        onPinSession={onPinSession}
        onArchiveSession={vi.fn()}
        onMuteSession={vi.fn()}
        onSelectProject={vi.fn()}
        onSelectProjectSession={vi.fn()}
        onCreateBlankProject={vi.fn()}
        onCreateCloudProject={vi.fn()}
        onPickExistingFolder={vi.fn()}
        onArchiveProject={vi.fn()}
        onRenameProject={vi.fn()}
        onDeleteProject={vi.fn()}
        onNewProjectSession={vi.fn()}
        onStartAgentChat={vi.fn()}
        onCreateAgent={vi.fn()}
        onEditAgent={vi.fn()}
        onDeleteAgent={vi.fn()}
      />,
    );

    expect(await screen.findByText("发布准备")).toBeInTheDocument();
    expect(screen.getAllByText("发布准备")).toHaveLength(1);
    const collapseProject = screen.getByLabelText("收起 Alpha 的对话");
    expect(collapseProject).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByLabelText("重命名 发布准备"));
    const input = screen.getByLabelText("重命名对话 发布准备");
    fireEvent.change(input, { target: { value: "发布版本" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onRenameSession).toHaveBeenCalledWith("pinned-session", "发布版本");

    expect(screen.queryByLabelText("取消置顶 发布准备")).not.toBeInTheDocument();
    expect(onPinSession).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("删除 发布准备"));
    fireEvent.click(screen.getByLabelText("确认 发布准备"));
    expect(onDeleteSession).toHaveBeenCalledWith("pinned-session");

    fireEvent.click(collapseProject);
    expect(screen.getByLabelText("展开 Alpha 的对话")).toHaveAttribute("aria-expanded", "false");
  });

  it("项目新建对话必须先选择 Agent", () => {
    const onNewProjectSession = vi.fn();
    render(
      <ActivityPanelContent
        panel="projects"
        project={projects[0]}
        projects={projects}
        currentProjectId="alpha"
        currentTeamId={null}
        sessions={[]}
        currentSessionId={null}
        sessionsLoading={false}
        projectsLoading={false}
        creatingProject={false}
        agents={[agent]}
        canCreateLocalProject
        canCreateCloudProject={false}
        onSelectSession={vi.fn()}
        onNewSession={vi.fn()}
        onNewGroupSession={vi.fn()}
        onDeleteSession={vi.fn()}
        onRenameSession={vi.fn()}
        onPinSession={vi.fn()}
        onArchiveSession={vi.fn()}
        onMuteSession={vi.fn()}
        onSelectProject={vi.fn()}
        onSelectProjectSession={vi.fn()}
        onCreateBlankProject={vi.fn()}
        onCreateCloudProject={vi.fn()}
        onPickExistingFolder={vi.fn()}
        onArchiveProject={vi.fn()}
        onRenameProject={vi.fn()}
        onDeleteProject={vi.fn()}
        onNewProjectSession={onNewProjectSession}
        onStartAgentChat={vi.fn()}
        onCreateAgent={vi.fn()}
        onEditAgent={vi.fn()}
        onDeleteAgent={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText("在 Alpha 新建对话"));
    expect(onNewProjectSession).not.toHaveBeenCalled();
    expect(screen.getByText("选择 Agent 后新建对话")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /前端工程师/ }));
    expect(onNewProjectSession).toHaveBeenCalledWith("alpha", "agent-1");
  });

  it("好友行只渲染一个居中的操作按钮", () => {
    const { container } = render(
      <ActivityPanelContent
        panel="agents"
        project={null}
        projects={projects}
        currentProjectId={null}
        currentTeamId={null}
        sessions={[]}
        currentSessionId={null}
        sessionsLoading={false}
        projectsLoading={false}
        creatingProject={false}
        agents={[agent]}
        canCreateLocalProject
        canCreateCloudProject={false}
        onSelectSession={vi.fn()}
        onNewSession={vi.fn()}
        onNewGroupSession={vi.fn()}
        onDeleteSession={vi.fn()}
        onRenameSession={vi.fn()}
        onPinSession={vi.fn()}
        onArchiveSession={vi.fn()}
        onMuteSession={vi.fn()}
        onSelectProject={vi.fn()}
        onSelectProjectSession={vi.fn()}
        onCreateBlankProject={vi.fn()}
        onCreateCloudProject={vi.fn()}
        onPickExistingFolder={vi.fn()}
        onArchiveProject={vi.fn()}
        onRenameProject={vi.fn()}
        onDeleteProject={vi.fn()}
        onNewProjectSession={vi.fn()}
        onStartAgentChat={vi.fn()}
        onCreateAgent={vi.fn()}
        onEditAgent={vi.fn()}
        onDeleteAgent={vi.fn()}
      />,
    );

    const row = container.querySelector(".agenthub-activity-list-row");
    expect(row?.querySelectorAll(".agenthub-row-more")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "前端工程师 操作" })).toHaveClass("agenthub-row-more");
  });
});
