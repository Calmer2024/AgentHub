import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { ProjectSidebar } from "./ProjectSidebar";
import type { AgentConfig, Project } from "../types";

const project: Project = {
  id: "p1",
  name: "大作业",
  workspacePath: "D:\\AgentHub\\workspaces\\homework",
  workspaceMode: "local",
  workspaceId: null,
  teamId: null,
  status: "ready",
  fileCount: 0,
  totalSizeBytes: 0,
  createdAt: "",
};

const makeProject = (id: string, name: string): Project => ({
  ...project,
  id,
  name,
  workspacePath: `D:\\AgentHub\\workspaces\\${id}`,
});

const cloudProject: Project = {
  ...project,
  id: "p-cloud",
  name: "云端项目",
  workspacePath: null,
  workspaceMode: "cloud",
  workspaceId: "w1",
  teamId: "t1",
};

const makeAgent = (id: string, name: string, overrides: Partial<AgentConfig> = {}): AgentConfig => ({
  id,
  name,
  description: "",
  systemPrompt: "",
  rules: "",
  agentType: "cli_wrapper",
  cliTool: "custom",
  executable: "agent",
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
  ...overrides,
});

const renderSidebar = (overrides: Partial<ComponentProps<typeof ProjectSidebar>> = {}) => render(
  <ProjectSidebar
    projects={[project]}
    currentProjectId="p1"
    agents={[]}
    activePanel="sessions"
    currentUser={{
      id: "u1",
      email: "demo@agenthub.local",
      displayName: "Demo",
      createdAt: "",
    }}
    teams={[]}
    currentTeamId={null}
    creating={false}
    onSelectProject={vi.fn()}
    onSelectTeam={vi.fn()}
    onCreateTeam={vi.fn().mockResolvedValue(undefined)}
    onCreateBlankProject={vi.fn().mockResolvedValue(undefined)}
    onCreateCloudProject={vi.fn().mockResolvedValue(undefined)}
    onPickExistingFolder={vi.fn().mockResolvedValue(undefined)}
    onArchiveProject={vi.fn()}
    onRenameProject={vi.fn().mockResolvedValue(undefined)}
    onDeleteProject={vi.fn().mockResolvedValue(undefined)}
    onOpenPanel={vi.fn()}
    onStartAgentChat={vi.fn().mockResolvedValue(undefined)}
    onCreateAgent={vi.fn()}
    onEditAgent={vi.fn()}
    onDeleteAgent={vi.fn().mockResolvedValue(undefined)}
    {...overrides}
  />,
);

describe("ProjectSidebar", () => {
  it("创建按钮弹出空白文件夹和现有文件夹动作", () => {
    const onCreateBlankProject = vi.fn().mockResolvedValue(undefined);
    const onPickExistingFolder = vi.fn().mockResolvedValue(undefined);

    renderSidebar({ onCreateBlankProject, onPickExistingFolder });

    fireEvent.click(screen.getByTitle("创建项目"));

    expect(screen.getByText("新建空白项目")).toBeInTheDocument();
    expect(screen.getByText("选择现有文件夹")).toBeInTheDocument();

    fireEvent.click(screen.getByText("新建空白项目"));
    const createDialog = screen.getByRole("dialog", { name: "新建项目" });
    expect(createDialog).toHaveClass("fixed");
    expect(createDialog).toHaveClass("items-center");
    expect(createDialog).not.toHaveClass("h-[100dvh]");
    fireEvent.change(screen.getByLabelText("项目名称"), { target: { value: "新项目" } });
    fireEvent.click(screen.getByText("创建本机项目"));

    expect(onCreateBlankProject).toHaveBeenCalledWith("新项目");
  });

  it("选择现有文件夹调用系统选择动作", () => {
    const onPickExistingFolder = vi.fn().mockResolvedValue(undefined);

    renderSidebar({ onPickExistingFolder });

    fireEvent.click(screen.getByTitle("创建项目"));
    fireEvent.click(screen.getByText("选择现有文件夹"));

    expect(onPickExistingFolder).toHaveBeenCalled();
  });

  it("云端项目入口按团队空间提交", () => {
    const onCreateCloudProject = vi.fn().mockResolvedValue(undefined);

    renderSidebar({
      teams: [{ id: "t1", name: "研发团队", role: "owner", memberCount: 1, createdAt: "" }],
      currentTeamId: "t1",
      onCreateCloudProject,
    });

    fireEvent.click(screen.getByTitle("创建项目"));
    fireEvent.click(screen.getByText("新建云端项目"));
    fireEvent.change(screen.getByLabelText("项目名称"), { target: { value: "云项目" } });
    fireEvent.click(screen.getByText("创建云端项目"));

    expect(onCreateCloudProject).toHaveBeenCalledWith("云项目", "t1");
  });

  it("智能体设置按钮直接打开设置弹窗", () => {
    const onEditAgent = vi.fn();
    const agent = makeAgent("a1", "前端工程师");

    renderSidebar({ agents: [agent], onEditAgent });

    const actionButton = screen.getByTitle("智能体操作");
    expect(actionButton).toHaveClass("opacity-0");
    expect(actionButton).toHaveClass("group-hover:opacity-100");

    fireEvent.click(actionButton);
    expect(actionButton).toHaveClass("opacity-100");
    fireEvent.click(screen.getByText("设置"));

    expect(onEditAgent).toHaveBeenCalledWith("a1");
  });

  it("删除 Agent 使用原按钮二次确认", () => {
    const onDeleteAgent = vi.fn().mockResolvedValue(undefined);
    const agent = makeAgent("a1", "前端工程师");

    renderSidebar({ agents: [agent], onDeleteAgent });

    fireEvent.click(screen.getByTitle("智能体操作"));
    fireEvent.click(screen.getByText("删除"));

    expect(onDeleteAgent).not.toHaveBeenCalled();
    expect(screen.getByText("确认")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /删除/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("确认"));
    expect(onDeleteAgent).toHaveBeenCalledWith("a1");
  });

  it("删除项目使用原按钮二次确认", () => {
    const onDeleteProject = vi.fn().mockResolvedValue(undefined);

    renderSidebar({ onDeleteProject });

    fireEvent.click(screen.getByLabelText("项目操作"));
    fireEvent.click(screen.getByText("删除目录"));

    expect(onDeleteProject).not.toHaveBeenCalled();
    expect(screen.getByText("确认")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /删除/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("确认"));
    expect(onDeleteProject).toHaveBeenCalledWith("p1", true);
  });

  it("好友列表固定高度滚动且不再需要展开按钮，项目仍可展开", () => {
    renderSidebar({
      projects: [
        makeProject("p1", "项目一"),
        makeProject("p2", "项目二"),
        makeProject("p3", "项目三"),
        makeProject("p4", "项目四"),
      ],
      agents: [
        makeAgent("a1", "Claude"),
        makeAgent("a2", "Codex 自定义"),
        makeAgent("a3", "OpenCode 自定义"),
        makeAgent("a4", "Pascal"),
      ],
    });

    expect(screen.getByText("Claude")).toBeInTheDocument();
    expect(screen.getByText("Pascal")).toBeInTheDocument();
    expect(screen.getByText("项目三")).toBeInTheDocument();
    expect(screen.queryByText("项目四")).not.toBeInTheDocument();
    expect(screen.getByLabelText("好友列表")).toHaveClass("agenthub-friends-scroll");
    expect(screen.queryByRole("button", { name: /展开全部好友/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /展开全部项目/ }));

    expect(screen.getByText("项目四")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /收起项目 \(4\)/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("原生 CLI Agent 置顶并与自定义 Agent 分区", () => {
    renderSidebar({
      agents: [
        makeAgent("custom-1", "前端工程师", { cliTool: "codex", executable: "codex" }),
        makeAgent("native-open", "OpenCode", { cliTool: "opencode", executable: "opencode" }),
        makeAgent("native-codex", "Codex", { cliTool: "codex", executable: "codex" }),
        makeAgent("native-claude", "Claude Code", { cliTool: "claude_code", executable: "claude" }),
      ],
    });

    const listText = screen.getByLabelText("好友列表").textContent ?? "";
    expect(listText.indexOf("原生 CLI")).toBeLessThan(listText.indexOf("自定义 Agent"));
    expect(listText.indexOf("Claude Code")).toBeLessThan(listText.indexOf("Codex"));
    expect(listText.indexOf("Codex")).toBeLessThan(listText.indexOf("OpenCode"));
    expect(listText.indexOf("OpenCode")).toBeLessThan(listText.indexOf("前端工程师"));
  });

  it("local 壳隐藏团队空间和云端项目入口", () => {
    renderSidebar({
      productEdition: "local",
      projects: [project, cloudProject],
    });

    expect(screen.queryByLabelText("团队空间")).not.toBeInTheDocument();
    expect(screen.queryByText("本机项目设置")).not.toBeInTheDocument();
    expect(screen.queryByText("工作区设置")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTitle("创建项目"));
    expect(screen.getByText("新建空白项目")).toBeInTheDocument();
    expect(screen.getByText("选择现有文件夹")).toBeInTheDocument();
    expect(screen.queryByText("新建云端项目")).not.toBeInTheDocument();
    expect(screen.getByText("大作业")).toBeInTheDocument();
    expect(screen.queryByText("云端项目")).not.toBeInTheDocument();
  });

  it("SaaS 壳隐藏本机目录入口，只显示云端项目", () => {
    renderSidebar({
      productEdition: "saas",
      projects: [project, cloudProject],
      teams: [{ id: "t1", name: "研发团队", role: "owner", memberCount: 1, createdAt: "" }],
      currentTeamId: "t1",
    });

    expect(screen.getByLabelText("团队空间")).toBeInTheDocument();
    expect(screen.getByText("工作区设置")).toBeInTheDocument();
    fireEvent.click(screen.getByTitle("创建项目"));
    expect(screen.getByText("新建云端项目")).toBeInTheDocument();
    expect(screen.queryByText("新建空白项目")).not.toBeInTheDocument();
    expect(screen.queryByText("选择现有文件夹")).not.toBeInTheDocument();
    expect(screen.getAllByText("云端项目").length).toBeGreaterThan(0);
    expect(screen.queryByText("大作业")).not.toBeInTheDocument();
  });

  it("SaaS 团队创建使用全局弹窗", () => {
    const onCreateTeam = vi.fn().mockResolvedValue(undefined);

    renderSidebar({
      productEdition: "saas",
      teams: [{ id: "t1", name: "研发团队", role: "owner", memberCount: 1, createdAt: "" }],
      onCreateTeam,
    });

    fireEvent.click(screen.getByLabelText("团队空间"));
    fireEvent.click(screen.getByRole("button", { name: "创建团队" }));

    const teamDialog = screen.getByRole("dialog", { name: "创建团队" });
    expect(teamDialog).toHaveClass("fixed");
    expect(teamDialog).toHaveClass("items-center");
    expect(teamDialog).not.toHaveClass("h-[100dvh]");
    fireEvent.change(screen.getByLabelText("团队名称"), { target: { value: "增长团队" } });
    fireEvent.click(screen.getByRole("button", { name: "创建团队" }));

    expect(onCreateTeam).toHaveBeenCalledWith("增长团队");
  });
});
