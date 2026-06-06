import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { ProjectSidebar } from "./ProjectSidebar";
import type { AgentConfig, Project } from "../types";

const project: Project = {
  id: "p1",
  name: "大作业",
  workspacePath: "D:\\AgentHub\\workspaces\\homework",
  status: "ready",
  fileCount: 0,
  totalSizeBytes: 0,
  createdAt: "",
};

const renderSidebar = (overrides: Partial<ComponentProps<typeof ProjectSidebar>> = {}) => render(
  <ProjectSidebar
    projects={[project]}
    currentProjectId="p1"
    agents={[]}
    activePanel="sessions"
    creating={false}
    onSelectProject={vi.fn()}
    onCreateBlankProject={vi.fn().mockResolvedValue(undefined)}
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
    expect(screen.getByRole("dialog", { name: "新建项目" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("项目名称"), { target: { value: "新项目" } });
    fireEvent.click(screen.getByText("创建"));

    expect(onCreateBlankProject).toHaveBeenCalledWith("新项目");
  });

  it("选择现有文件夹调用系统选择动作", () => {
    const onPickExistingFolder = vi.fn().mockResolvedValue(undefined);

    renderSidebar({ onPickExistingFolder });

    fireEvent.click(screen.getByTitle("创建项目"));
    fireEvent.click(screen.getByText("选择现有文件夹"));

    expect(onPickExistingFolder).toHaveBeenCalled();
  });

  it("智能体设置按钮直接打开设置弹窗", () => {
    const onEditAgent = vi.fn();
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

    renderSidebar({ agents: [agent], onEditAgent });

    fireEvent.click(screen.getByTitle("智能体操作"));
    fireEvent.click(screen.getByText("设置"));

    expect(onEditAgent).toHaveBeenCalledWith("a1");
  });
});
