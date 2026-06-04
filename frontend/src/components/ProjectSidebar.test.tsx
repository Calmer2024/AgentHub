import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ProjectSidebar } from "./ProjectSidebar";
import type { Project } from "../types";

const project: Project = {
  id: "p1",
  name: "大作业",
  workspacePath: "D:\\AgentHub\\workspaces\\homework",
  status: "ready",
  fileCount: 0,
  totalSizeBytes: 0,
  createdAt: "",
};

describe("ProjectSidebar", () => {
  it("创建按钮弹出空白文件夹和现有文件夹动作", () => {
    const onCreateBlankProject = vi.fn().mockResolvedValue(undefined);
    const onPickExistingFolder = vi.fn().mockResolvedValue(undefined);

    render(
      <ProjectSidebar
        projects={[project]}
        currentProjectId="p1"
        agents={[]}
        activePanel="sessions"
        creating={false}
        onSelectProject={vi.fn()}
        onCreateBlankProject={onCreateBlankProject}
        onPickExistingFolder={onPickExistingFolder}
        onArchiveProject={vi.fn()}
        onOpenPanel={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTitle("创建项目"));

    expect(screen.getByText("新建空白文件夹")).toBeInTheDocument();
    expect(screen.getByText("选择现有文件夹")).toBeInTheDocument();

    fireEvent.click(screen.getByText("新建空白文件夹"));
    expect(onCreateBlankProject).toHaveBeenCalled();
  });

  it("选择现有文件夹调用系统选择动作", () => {
    const onPickExistingFolder = vi.fn().mockResolvedValue(undefined);

    render(
      <ProjectSidebar
        projects={[project]}
        currentProjectId="p1"
        agents={[]}
        activePanel="sessions"
        creating={false}
        onSelectProject={vi.fn()}
        onCreateBlankProject={vi.fn().mockResolvedValue(undefined)}
        onPickExistingFolder={onPickExistingFolder}
        onArchiveProject={vi.fn()}
        onOpenPanel={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTitle("创建项目"));
    fireEvent.click(screen.getByText("选择现有文件夹"));

    expect(onPickExistingFolder).toHaveBeenCalled();
  });
});
