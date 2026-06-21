import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useWorkspaceRuntime } from "../../../frontend/src/hooks/useWorkspaceRuntime";
import { useChatStore } from "../../../frontend/src/stores/chatStore";
import { useSessionStore } from "../../../frontend/src/stores/sessionStore";
import type { Message, Project, Session } from "../../../frontend/src/types";

const apiMocks = vi.hoisted(() => ({
  addGroupMember: vi.fn(),
  archiveProject: vi.fn(),
  archiveSession: vi.fn(),
  createTeam: vi.fn(),
  createGroupSession: vi.fn(),
  createProject: vi.fn(),
  createSession: vi.fn(),
  deleteProject: vi.fn(),
  deleteSession: vi.fn(),
  fetchAgents: vi.fn(),
  fetchCurrentUser: vi.fn(),
  fetchApprovals: vi.fn(),
  fetchArtifacts: vi.fn(),
  fetchMessages: vi.fn(),
  fetchProjects: vi.fn(),
  fetchTeams: vi.fn(),
  fetchRuns: vi.fn(),
  fetchSessionMembers: vi.fn(),
  fetchSessions: vi.fn(),
  fetchSystemHealth: vi.fn(),
  markSessionRead: vi.fn(),
  muteSession: vi.fn(),
  pickProjectFolder: vi.fn(),
  pinSession: vi.fn(),
  renameSession: vi.fn(),
  removeGroupMember: vi.fn(),
  updateProject: vi.fn(),
}));

vi.mock("../../../frontend/src/api/client", () => apiMocks);

const wsHandlers = vi.hoisted(() => ({
  current: {} as Record<string, (event: Record<string, unknown>) => void>,
}));

vi.mock("../../../frontend/src/api/wsClient", () => ({
  WSClient: class {
    on(event: string, handler: (event: Record<string, unknown>) => void) {
      wsHandlers.current[event] = handler;
    }
    connect(_sessionId: string) {}
    disconnect() {}
  },
}));

function resetStores() {
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
  useSessionStore.setState({
    projects: [],
    currentProjectId: null,
    sessions: [],
    agents: [],
    sidebarTab: "sessions",
  });
  wsHandlers.current = {};
}

const projects: Project[] = [
  {
    id: "p-a",
    name: "项目 A",
    workspacePath: "D:/workspace/a",
    workspaceMode: "local",
    workspaceId: null,
    teamId: null,
    status: "ready",
    fileCount: 0,
    totalSizeBytes: 0,
    createdAt: "2026-06-06T00:00:00.000Z",
  },
  {
    id: "p-b",
    name: "项目 B",
    workspacePath: "D:/workspace/b",
    workspaceMode: "local",
    workspaceId: null,
    teamId: null,
    status: "ready",
    fileCount: 0,
    totalSizeBytes: 0,
    createdAt: "2026-06-06T00:00:00.000Z",
  },
];

const mixedProjects: Project[] = [
  projects[0],
  {
    ...projects[1],
    id: "p-cloud",
    name: "云端项目",
    workspacePath: null,
    workspaceMode: "cloud",
    workspaceId: "w1",
    teamId: "t1",
  },
];

const saasProjects: Project[] = [
  {
    ...projects[0],
    id: "p-personal-cloud",
    name: "个人云端项目",
    workspacePath: null,
    workspaceMode: "cloud",
    workspaceId: "w-personal",
    teamId: null,
  },
  {
    ...projects[1],
    id: "p-team-cloud",
    name: "团队云端项目",
    workspacePath: null,
    workspaceMode: "cloud",
    workspaceId: "w-team",
    teamId: "t1",
  },
];

const sessionA: Session = {
  id: "s-a",
  title: "缓存会话",
  projectId: "p-a",
  agentConfigId: null,
  mode: "single",
  createdAt: "2026-06-06T00:00:00.000Z",
  updatedAt: "2026-06-06T00:00:00.000Z",
};

const hydratedMessage: Message = {
  id: "m-a",
  sessionId: "s-a",
  role: "assistant",
  content: "已加载",
  agentName: null,
  createdAt: "2026-06-06T00:00:00.000Z",
};

describe("useWorkspaceRuntime hydration", () => {
  afterEach(() => {
    vi.clearAllMocks();
    resetStores();
  });

  it("切回已有缓存会话时仍会完成 hydrate，避免顶部脉冲加载条卡住", async () => {
    resetStores();
    apiMocks.fetchProjects.mockResolvedValue(projects);
    apiMocks.fetchAgents.mockResolvedValue([]);
    apiMocks.fetchCurrentUser.mockResolvedValue({
      id: "u1",
      email: "demo@agenthub.local",
      displayName: "Demo",
      createdAt: "",
    });
    apiMocks.fetchTeams.mockResolvedValue([]);
    apiMocks.fetchSessions.mockImplementation((projectId?: string | null) => (
      Promise.resolve(projectId === "p-a" ? [sessionA] : [])
    ));
    apiMocks.fetchMessages.mockResolvedValue([hydratedMessage]);
    apiMocks.fetchArtifacts.mockResolvedValue([]);
    apiMocks.fetchRuns.mockResolvedValue([]);
    apiMocks.fetchApprovals.mockResolvedValue([]);
    apiMocks.fetchSystemHealth.mockResolvedValue(null);
    apiMocks.markSessionRead.mockResolvedValue(sessionA);

    const { result } = renderHook(() => useWorkspaceRuntime());

    await waitFor(() => expect(result.current.currentProjectId).toBe("p-a"));
    await waitFor(() => expect(result.current.sessions.map((session) => session.id)).toEqual(["s-a"]));
    await waitFor(() => expect(result.current.sessionHydrating).toBe(false));

    await act(async () => {
      result.current.handleSelectProject("p-b");
    });
    await waitFor(() => expect(result.current.currentProjectId).toBe("p-b"));
    await waitFor(() => expect(result.current.sessions).toEqual([]));

    const callsAfterInitialLoad = apiMocks.fetchMessages.mock.calls.length;
    await act(async () => {
      result.current.handleSelectProject("p-a");
    });

    await waitFor(() => expect(apiMocks.fetchMessages.mock.calls.length).toBeGreaterThan(callsAfterInitialLoad));
    await waitFor(() => expect(result.current.sessionHydrating).toBe(false));
    expect(useChatStore.getState().messagesBySession["s-a"]).toEqual([hydratedMessage]);
  });

  it("收到会话标题更新事件后同步列表和项目缓存", async () => {
    resetStores();
    apiMocks.fetchProjects.mockResolvedValue(projects);
    apiMocks.fetchAgents.mockResolvedValue([]);
    apiMocks.fetchCurrentUser.mockResolvedValue({
      id: "u1",
      email: "demo@agenthub.local",
      displayName: "Demo",
      createdAt: "",
    });
    apiMocks.fetchTeams.mockResolvedValue([]);
    apiMocks.fetchSessions.mockResolvedValue([sessionA]);
    apiMocks.fetchMessages.mockResolvedValue([hydratedMessage]);
    apiMocks.fetchArtifacts.mockResolvedValue([]);
    apiMocks.fetchRuns.mockResolvedValue([]);
    apiMocks.fetchApprovals.mockResolvedValue([]);
    apiMocks.fetchSystemHealth.mockResolvedValue(null);
    apiMocks.markSessionRead.mockResolvedValue(sessionA);

    const { result } = renderHook(() => useWorkspaceRuntime());

    await waitFor(() => expect(result.current.currentProjectId).toBe("p-a"));
    await waitFor(() => expect(useChatStore.getState().currentSessionId).toBe("s-a"));
    await waitFor(() => expect(wsHandlers.current["session.title_updated"]).toBeTypeOf("function"));

    const updated = {
      ...sessionA,
      title: "自动总结标题",
      updatedAt: "2026-06-06T00:01:00.000Z",
    };
    act(() => {
      wsHandlers.current["session.title_updated"]({ session: updated });
    });

    await waitFor(() => expect(result.current.sessions[0].title).toBe("自动总结标题"));

    await act(async () => {
      result.current.handleSelectProject("p-b");
    });
    await waitFor(() => expect(result.current.currentProjectId).toBe("p-b"));

    await act(async () => {
      result.current.handleSelectProject("p-a");
    });

    await waitFor(() => expect(result.current.sessions[0].title).toBe("自动总结标题"));
  });

  it("发送流兜底刷新会话后也同步列表和项目缓存", async () => {
    resetStores();
    apiMocks.fetchProjects.mockResolvedValue(projects);
    apiMocks.fetchAgents.mockResolvedValue([]);
    apiMocks.fetchCurrentUser.mockResolvedValue({
      id: "u1",
      email: "demo@agenthub.local",
      displayName: "Demo",
      createdAt: "",
    });
    apiMocks.fetchTeams.mockResolvedValue([]);
    apiMocks.fetchSessions.mockImplementation((projectId?: string | null) => (
      Promise.resolve(projectId === "p-a" ? [sessionA] : [])
    ));
    apiMocks.fetchMessages.mockResolvedValue([hydratedMessage]);
    apiMocks.fetchArtifacts.mockResolvedValue([]);
    apiMocks.fetchRuns.mockResolvedValue([]);
    apiMocks.fetchApprovals.mockResolvedValue([]);
    apiMocks.fetchSystemHealth.mockResolvedValue(null);

    const { result } = renderHook(() => useWorkspaceRuntime());

    await waitFor(() => expect(result.current.currentProjectId).toBe("p-a"));
    const updated = {
      ...sessionA,
      title: "兜底刷新标题",
      updatedAt: "2026-06-06T00:02:00.000Z",
    };
    act(() => {
      window.dispatchEvent(new CustomEvent("agenthub:session-updated", {
        detail: { session: updated },
      }));
    });

    await waitFor(() => expect(result.current.sessions[0].title).toBe("兜底刷新标题"));

    await act(async () => {
      result.current.handleSelectProject("p-b");
    });
    await act(async () => {
      result.current.handleSelectProject("p-a");
    });

    await waitFor(() => expect(result.current.sessions[0].title).toBe("兜底刷新标题"));
  });

  it("SaaS 首次进入默认选择个人空间项目", async () => {
    resetStores();
    apiMocks.fetchProjects.mockResolvedValue(saasProjects);
    apiMocks.fetchAgents.mockResolvedValue([]);
    apiMocks.fetchCurrentUser.mockResolvedValue({
      id: "u1",
      email: "demo@agenthub.local",
      displayName: "Demo",
      createdAt: "",
    });
    apiMocks.fetchTeams.mockResolvedValue([
      { id: "t1", name: "研发团队", role: "owner", memberCount: 2, createdAt: "" },
    ]);
    apiMocks.fetchSessions.mockResolvedValue([]);
    apiMocks.fetchSystemHealth.mockResolvedValue(null);

    const { result } = renderHook(() => useWorkspaceRuntime({
      projectMode: "cloud",
      loadCloudIdentity: true,
    }));

    await waitFor(() => expect(result.current.currentTeamId).toBeNull());
    await waitFor(() => expect(result.current.currentProjectId).toBe("p-personal-cloud"));
    expect(result.current.currentProject?.teamId).toBeNull();

    act(() => {
      result.current.setCurrentTeamId("t1");
    });

    await waitFor(() => expect(result.current.currentTeamId).toBe("t1"));
    await waitFor(() => expect(result.current.currentProjectId).toBe("p-team-cloud"));
  });

  it("local runtime 只加载本机项目且不请求云端身份", async () => {
    resetStores();
    apiMocks.fetchProjects.mockResolvedValue(mixedProjects);
    apiMocks.fetchAgents.mockResolvedValue([]);
    apiMocks.fetchSessions.mockResolvedValue([]);
    apiMocks.fetchSystemHealth.mockResolvedValue(null);

    const { result } = renderHook(() => useWorkspaceRuntime({
      projectMode: "local",
      loadCloudIdentity: false,
    }));

    await waitFor(() => expect(result.current.projects.map((item) => item.workspaceMode)).toEqual(["local"]));
    expect(apiMocks.fetchCurrentUser).not.toHaveBeenCalled();
    expect(apiMocks.fetchTeams).not.toHaveBeenCalled();
  });
});
