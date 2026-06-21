import { describe, expect, it, vi, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { WorkspaceSettingsPage } from "../../../frontend/src/components/WorkspaceSettingsPage";
import type { CloudWorkspace, Project } from "../../../frontend/src/types";

const apiMocks = vi.hoisted(() => ({
  addTeamMember: vi.fn(),
  createSecret: vi.fn(),
  createWorkspaceSnapshot: vi.fn(),
  fetchAuditLogs: vi.fn(),
  fetchQuotaSummary: vi.fn(),
  fetchTeamMembers: vi.fn().mockResolvedValue([]),
  fetchWorkspace: vi.fn(),
  importWorkspaceGithub: vi.fn(),
  importWorkspaceZip: vi.fn(),
  removeTeamMember: vi.fn(),
  restoreWorkspaceSnapshot: vi.fn(),
  updateTeamMemberRole: vi.fn(),
}));

vi.mock("../../../frontend/src/api/client", () => apiMocks);

const cloudProject: Project = {
  id: "p-cloud",
  name: "云端项目",
  workspacePath: null,
  workspaceMode: "cloud",
  workspaceId: "w1",
  teamId: "t1",
  status: "ready",
  fileCount: 0,
  totalSizeBytes: 0,
  createdAt: "",
};

const localProject: Project = {
  id: "p-local",
  name: "本机项目",
  workspacePath: "D:/workspace/local",
  workspaceMode: "local",
  workspaceId: null,
  teamId: null,
  status: "ready",
  fileCount: 2,
  totalSizeBytes: 12,
  createdAt: "",
};

const workspace: CloudWorkspace = {
  id: "w1",
  projectId: "p-cloud",
  provider: "cloud",
  status: "ready",
  storageUri: "cloud://agenthub/workspaces/w1",
  snapshots: [{
    id: "snap1",
    workspaceId: "w1",
    label: "导入后",
    storageUri: "cloud://agenthub/workspaces/w1/snapshots/snap1",
    createdAt: "2026-06-08T10:00:00+08:00",
  }],
  imports: [{
    id: "imp1",
    workspaceId: "w1",
    source: "zip",
    status: "completed",
    detail: "已导入 2 个文件的元数据",
    metadata: {},
    createdAt: "2026-06-08T09:00:00+08:00",
  }],
  restores: [],
  createdAt: "2026-06-08T08:00:00+08:00",
  updatedAt: "2026-06-08T08:00:00+08:00",
};

function renderPage(project: Project | null = cloudProject, onRefreshProjects = vi.fn().mockResolvedValue(undefined)) {
  return render(
    <WorkspaceSettingsPage
      project={project}
      currentUser={{ id: "u1", email: "demo@agenthub.local", displayName: "Demo", createdAt: "" }}
      teams={[{ id: "t1", name: "研发团队", role: "owner", memberCount: 1, createdAt: "" }]}
      onRefreshProjects={onRefreshProjects}
    />,
  );
}

function chooseMenuOption(label: string, option: string) {
  fireEvent.click(screen.getByLabelText(label));
  fireEvent.click(screen.getByRole("option", { name: option }));
}

describe("WorkspaceSettingsPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("云端工作区加载导入、快照和审计日志", async () => {
    apiMocks.fetchWorkspace.mockResolvedValue(workspace);
    apiMocks.fetchQuotaSummary.mockResolvedValue({
      subjectType: "user",
      subjectId: "u1",
      concurrentRunsLimit: 2,
      concurrentRunsUsed: 1,
      runtimeSecondsLimit: 30,
      memoryMbLimit: 1024,
      diskMbLimit: 512,
      network: "disabled_by_default",
    });
    apiMocks.fetchAuditLogs.mockResolvedValue([
      { id: "log1", action: "workspace.created", resourceType: "workspace", resourceId: "w1", metadata: {}, createdAt: "" },
    ]);

    renderPage();

    expect(screen.getByLabelText("正在加载工作区")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("cloud://agenthub/workspaces/w1")).toBeInTheDocument());
    expect(screen.getByText("1/2")).toBeInTheDocument();
    expect(screen.queryByText("CLI 凭据")).not.toBeInTheDocument();
    expect(screen.getByText("zip · completed")).toBeInTheDocument();
    expect(screen.getByText("导入后")).toBeInTheDocument();
    expect(screen.getByText("workspace.created")).toBeInTheDocument();
  });

  it("创建和恢复快照后刷新工作区", async () => {
    const onRefreshProjects = vi.fn().mockResolvedValue(undefined);
    apiMocks.fetchWorkspace.mockResolvedValue(workspace);
    apiMocks.fetchQuotaSummary.mockResolvedValue({
      subjectType: "user",
      subjectId: "u1",
      concurrentRunsLimit: 2,
      concurrentRunsUsed: 0,
      runtimeSecondsLimit: 30,
      memoryMbLimit: 1024,
      diskMbLimit: 512,
      network: "disabled_by_default",
    });
    apiMocks.fetchAuditLogs.mockResolvedValue([]);
    apiMocks.createWorkspaceSnapshot.mockResolvedValue(workspace.snapshots[0]);
    apiMocks.restoreWorkspaceSnapshot.mockResolvedValue({ restoreId: "restore1" });

    renderPage(cloudProject, onRefreshProjects);
    await waitFor(() => expect(screen.getByText("导入后")).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText("创建快照"));
    await waitFor(() => expect(apiMocks.createWorkspaceSnapshot).toHaveBeenCalledWith("w1", "手动快照"));
    expect(onRefreshProjects).toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("恢复快照"));
    await waitFor(() => expect(apiMocks.restoreWorkspaceSnapshot).toHaveBeenCalledWith("w1", "snap1", "replace"));
  });

  it("保存云端 Secret 后清空输入并刷新", async () => {
    apiMocks.fetchWorkspace.mockResolvedValue(workspace);
    apiMocks.fetchQuotaSummary.mockResolvedValue({
      subjectType: "user",
      subjectId: "u1",
      concurrentRunsLimit: 2,
      concurrentRunsUsed: 0,
      runtimeSecondsLimit: 30,
      memoryMbLimit: 1024,
      diskMbLimit: 512,
      network: "disabled_by_default",
    });
    apiMocks.fetchAuditLogs.mockResolvedValue([]);
    apiMocks.createSecret.mockResolvedValue({
      id: "sec1",
      name: "PHASE10_TOKEN",
      scope: "user",
      ownerId: "u1",
      createdAt: "",
    });

    renderPage();
    await waitFor(() => expect(screen.getByText("cloud://agenthub/workspaces/w1")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Secret 名称"), { target: { value: "PHASE10_TOKEN" } });
    fireEvent.change(screen.getByLabelText("Secret 值"), { target: { value: "secret" } });
    fireEvent.click(screen.getByLabelText("保存 Secret"));

    await waitFor(() => expect(apiMocks.createSecret).toHaveBeenCalledWith({
      name: "PHASE10_TOKEN",
      value: "secret",
      scope: "user",
    }));
  });

  it("保存项目共享 Secret 时带上项目归属", async () => {
    apiMocks.fetchWorkspace.mockResolvedValue(workspace);
    apiMocks.fetchQuotaSummary.mockResolvedValue({
      subjectType: "team",
      subjectId: "t1",
      concurrentRunsLimit: 2,
      concurrentRunsUsed: 0,
      runtimeSecondsLimit: 30,
      memoryMbLimit: 1024,
      diskMbLimit: 512,
      network: "disabled_by_default",
    });
    apiMocks.fetchAuditLogs.mockResolvedValue([]);
    apiMocks.createSecret.mockResolvedValue({
      id: "sec-project",
      name: "PROJECT_TOKEN",
      scope: "project",
      ownerId: "p-cloud",
      createdAt: "",
    });

    renderPage();
    await waitFor(() => expect(screen.getByText("cloud://agenthub/workspaces/w1")).toBeInTheDocument());

    chooseMenuOption("Secret 作用域", "项目共享");
    fireEvent.change(screen.getByLabelText("Secret 名称"), { target: { value: "PROJECT_TOKEN" } });
    fireEvent.change(screen.getByLabelText("Secret 值"), { target: { value: "secret" } });
    fireEvent.click(screen.getByLabelText("保存 Secret"));

    await waitFor(() => expect(apiMocks.createSecret).toHaveBeenCalledWith({
      name: "PROJECT_TOKEN",
      value: "secret",
      scope: "project",
      ownerId: "p-cloud",
    }));
  });

  it("列出、添加、改角色并移除团队成员", async () => {
    apiMocks.fetchWorkspace.mockResolvedValue(workspace);
    apiMocks.fetchQuotaSummary.mockResolvedValue({
      subjectType: "team",
      subjectId: "t1",
      concurrentRunsLimit: 2,
      concurrentRunsUsed: 0,
      runtimeSecondsLimit: 30,
      memoryMbLimit: 1024,
      diskMbLimit: 512,
      network: "disabled_by_default",
    });
    apiMocks.fetchAuditLogs.mockResolvedValue([]);
    apiMocks.fetchTeamMembers.mockResolvedValue([
      {
        id: "tm-owner",
        teamId: "t1",
        userId: "u1",
        email: "owner@example.com",
        displayName: "Owner",
        role: "owner",
        createdAt: "",
      },
      {
        id: "tm-viewer",
        teamId: "t1",
        userId: "u2",
        email: "viewer@example.com",
        displayName: "Viewer",
        role: "viewer",
        createdAt: "",
      },
    ]);
    apiMocks.addTeamMember.mockResolvedValue({
      id: "tm-new",
      teamId: "t1",
      userId: "u3",
      email: "new@example.com",
      displayName: "new@example.com",
      role: "member",
      createdAt: "",
    });
    apiMocks.updateTeamMemberRole.mockResolvedValue({
      id: "tm-viewer",
      teamId: "t1",
      userId: "u2",
      email: "viewer@example.com",
      displayName: "Viewer",
      role: "member",
      createdAt: "",
    });
    apiMocks.removeTeamMember.mockResolvedValue(undefined);

    renderPage();
    await waitFor(() => expect(screen.getByText("viewer@example.com")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("成员邮箱"), { target: { value: "new@example.com" } });
    fireEvent.click(screen.getByLabelText("添加成员"));
    await waitFor(() => expect(apiMocks.addTeamMember).toHaveBeenCalledWith("t1", "new@example.com", "member"));

    await waitFor(() => expect(screen.getByLabelText("成员角色 viewer@example.com")).not.toBeDisabled());
    chooseMenuOption("成员角色 viewer@example.com", "member");
    await waitFor(() => expect(apiMocks.updateTeamMemberRole).toHaveBeenCalledWith("t1", "tm-viewer", "member"));

    await waitFor(() => expect(screen.getByLabelText("移除成员 viewer@example.com")).not.toBeDisabled());
    fireEvent.click(screen.getByLabelText("移除成员 viewer@example.com"));
    await waitFor(() => expect(apiMocks.removeTeamMember).toHaveBeenCalledWith("t1", "tm-viewer"));
  });

  it("本机项目不再提供本机项目设置页", () => {
    renderPage(localProject);

    expect(screen.getByText("选择云端项目后查看工作区")).toBeInTheDocument();
    expect(screen.queryByText("本机项目设置")).not.toBeInTheDocument();
    expect(screen.queryByText("本机工作区")).not.toBeInTheDocument();
    expect(screen.queryByText("D:/workspace/local")).not.toBeInTheDocument();
    expect(apiMocks.fetchWorkspace).not.toHaveBeenCalled();
  });
});
