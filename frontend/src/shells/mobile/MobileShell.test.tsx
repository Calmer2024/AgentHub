import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MobileShell } from "./MobileShell";
import {
  archiveSession,
  createChatStream,
  decideMobileApproval,
  fetchApprovals,
  fetchArtifacts,
  fetchCurrentUser,
  fetchMessages,
  fetchNotifications,
  fetchProjects,
  fetchSessionMembers,
  fetchSessions,
  markNotificationRead,
  markSessionRead,
  muteSession,
  pinSession,
  renderArtifact,
} from "../../api/client";
import type { ApprovalCheckpoint, Artifact, CurrentUser, Message, Notification, Project, Session } from "../../types";

const apiMocks = vi.hoisted(() => ({
  archiveSession: vi.fn(),
  createChatStream: vi.fn(),
  decideMobileApproval: vi.fn(),
  fetchApprovals: vi.fn(),
  fetchArtifacts: vi.fn(),
  fetchCurrentUser: vi.fn(),
  fetchMessages: vi.fn(),
  fetchNotifications: vi.fn(),
  fetchProjects: vi.fn(),
  fetchSessionMembers: vi.fn(),
  fetchSessions: vi.fn(),
  markNotificationRead: vi.fn(),
  markSessionRead: vi.fn(),
  muteSession: vi.fn(),
  pinSession: vi.fn(),
  renderArtifact: vi.fn(),
}));

vi.mock("../../api/client", () => apiMocks);

const user: CurrentUser = {
  id: "u1",
  email: "mobile@example.com",
  username: "mobile_user",
  displayName: "Mobile User",
  avatarUrl: null,
  status: "active",
  teams: [],
  defaultSpace: { kind: "personal", id: "u1", name: "个人空间" },
  createdAt: "2026-06-10T09:00:00+08:00",
};

const projects: Project[] = [
  {
    id: "p1",
    name: "研发空间",
    workspaceMode: "cloud",
    workspaceId: "w1",
    workspacePath: null,
    status: "ready",
    fileCount: 4,
    totalSizeBytes: 128,
    createdAt: "2026-06-10T09:00:00+08:00",
  },
  {
    id: "p2",
    name: "官网项目",
    workspaceMode: "cloud",
    workspaceId: "w2",
    workspacePath: null,
    status: "ready",
    fileCount: 8,
    totalSizeBytes: 256,
    createdAt: "2026-06-10T09:10:00+08:00",
  },
];

const sessions: Record<string, Session[]> = {
  p1: [
    {
      id: "s1",
      title: "后端联调",
      projectId: "p1",
      agentConfigId: "agent-claude",
      mode: "single",
      isPinned: true,
      archivedAt: null,
      unreadCount: 2,
      lastReadAt: null,
      isMuted: false,
      createdAt: "2026-06-10T09:20:00+08:00",
      updatedAt: "2026-06-10T09:25:00+08:00",
    },
  ],
  p2: [
    {
      id: "s2",
      title: "产品群聊",
      projectId: "p2",
      agentConfigId: null,
      mode: "group",
      isPinned: false,
      archivedAt: null,
      unreadCount: 0,
      lastReadAt: null,
      isMuted: false,
      createdAt: "2026-06-10T09:30:00+08:00",
      updatedAt: "2026-06-10T09:35:00+08:00",
    },
  ],
};

const messages: Record<string, Message[]> = {
  s1: [
    {
      id: "m1",
      sessionId: "s1",
      role: "user",
      content: "请检查登录 API",
      agentName: null,
      createdAt: "2026-06-10T09:25:00+08:00",
    },
  ],
  s2: [
    {
      id: "m2",
      sessionId: "s2",
      role: "assistant",
      content: "群聊已同步",
      agentName: "Orchestrator 调度器",
      createdAt: "2026-06-10T09:35:00+08:00",
    },
  ],
};

const artifact: Artifact = {
  id: "a1",
  sessionId: "s1",
  messageId: "m1",
  projectId: "p1",
  type: "web_preview",
  title: "登录页预览",
  content: "<main>preview</main>",
  status: "ready",
  version: 1,
  parentArtifactId: null,
  filePath: "dist/index.html",
  previewId: null,
  source: "workspace",
  createdAt: "2026-06-10T09:40:00+08:00",
};

const approval: ApprovalCheckpoint = {
  id: "ap1",
  runId: "run1",
  taskId: "task1",
  sessionId: "s1",
  messageId: "m1",
  artifactId: "a1",
  artifactVersion: 1,
  title: "部署前确认",
  summary: "准备发布登录页预览",
  status: "pending_review",
  reason: null,
  createdAt: "2026-06-10T09:42:00+08:00",
};

const notifications: Notification[] = [
  {
    id: "n1",
    type: "approval",
    resourceType: "approval",
    resourceId: "ap1",
    title: "有新的移动审批",
    body: "后端联调需要确认",
    readAt: null,
    createdAt: "2026-06-10T09:43:00+08:00",
  },
];

describe("MobileShell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCurrentUser).mockResolvedValue(user);
    vi.mocked(fetchProjects).mockResolvedValue(projects);
    vi.mocked(fetchSessions).mockImplementation((projectId) => Promise.resolve(sessions[projectId ?? ""] ?? []));
    vi.mocked(fetchNotifications).mockResolvedValue(notifications);
    vi.mocked(fetchMessages).mockImplementation((sessionId) => Promise.resolve(messages[sessionId] ?? []));
    vi.mocked(fetchArtifacts).mockImplementation((sessionId) => Promise.resolve(sessionId === "s1" ? [artifact] : []));
    vi.mocked(fetchApprovals).mockImplementation((sessionId) => Promise.resolve(sessionId === "s1" ? [approval] : []));
    vi.mocked(fetchSessionMembers).mockResolvedValue([
      { agentConfigId: "agent-orchestrator", agentName: "Orchestrator 调度器", joinedAt: "2026-06-10T09:00:00+08:00" },
    ]);
    vi.mocked(markSessionRead).mockImplementation((sessionId) => {
      const session = Object.values(sessions).flat().find((item) => item.id === sessionId);
      return Promise.resolve({ ...(session ?? sessions.p1[0]), unreadCount: 0 });
    });
    vi.mocked(renderArtifact).mockResolvedValue({
      artifactId: "a1",
      format: "html",
      renderId: "render-1",
      content: "<main>移动端预览</main>",
      fileName: "index.html",
    });
    vi.mocked(decideMobileApproval).mockResolvedValue({ ...approval, status: "approved" });
    vi.mocked(pinSession).mockResolvedValue({ ...sessions.p1[0], isPinned: false });
    vi.mocked(muteSession).mockResolvedValue({ ...sessions.p1[0], isMuted: true });
    vi.mocked(archiveSession).mockResolvedValue({ ...sessions.p1[0], archivedAt: "2026-06-10T10:00:00+08:00" });
    vi.mocked(markNotificationRead).mockResolvedValue(undefined);
    vi.mocked(createChatStream).mockImplementation((_sessionId, _content, _mentions, callbacks) => {
      callbacks.onToken("移动端回复");
      return vi.fn();
    });
  });

  it("登录后按账号加载所有项目，并可切换项目查看对话", async () => {
    render(<MobileShell />);

    expect((await screen.findAllByRole("button", { name: /研发空间/ })).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /官网项目/ }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("后端联调").length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole("button", { name: /官网项目/ })[0]);

    expect((await screen.findAllByText("产品群聊")).length).toBeGreaterThan(0);
    expect(fetchSessions).toHaveBeenCalledWith("p1", true);
    expect(fetchSessions).toHaveBeenCalledWith("p2", true);
  });

  it("进入会话后具备移动 IM 发送能力并显示流式回复", async () => {
    render(<MobileShell />);

    fireEvent.click(await screen.findByRole("button", { name: /后端联调/ }));
    expect(await screen.findByText("请检查登录 API")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("输入移动端消息"), { target: { value: "继续检查" } });
    fireEvent.click(screen.getByLabelText("发送消息"));

    expect(await screen.findByText("继续检查")).toBeInTheDocument();
    expect(screen.getByText("移动端回复")).toBeInTheDocument();
    expect(createChatStream).toHaveBeenCalledWith("s1", "继续检查", [], expect.any(Object));
  });

  it("可在移动端打开会话 Artifact 预览", async () => {
    render(<MobileShell />);

    fireEvent.click(await screen.findByRole("button", { name: /后端联调/ }));
    fireEvent.click(await screen.findByRole("button", { name: /登录页预览/ }));

    await waitFor(() => expect(renderArtifact).toHaveBeenCalledWith("a1", "html"));
    expect(await screen.findByTitle("移动端 Artifact 预览")).toBeInTheDocument();
  });

  it("可从会话进入移动审批并提交同意决策", async () => {
    render(<MobileShell />);

    fireEvent.click(await screen.findByRole("button", { name: /后端联调/ }));
    fireEvent.click(await screen.findByRole("button", { name: /1 个待审批/ }));
    expect(await screen.findByText("部署前确认")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "同意" }));

    await waitFor(() => expect(decideMobileApproval).toHaveBeenCalledWith("ap1", {
      decision: "approve",
      comment: "移动端同意",
    }));
  });
});
