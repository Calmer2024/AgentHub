import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useWorkspaceRuntime } from "./useWorkspaceRuntime";
import { useChatStore } from "../stores/chatStore";
import { useSessionStore } from "../stores/sessionStore";
import type { Message, Project, Session } from "../types";

const apiMocks = vi.hoisted(() => ({
  archiveProject: vi.fn(),
  createGroupSession: vi.fn(),
  createProject: vi.fn(),
  createSession: vi.fn(),
  deleteProject: vi.fn(),
  deleteSession: vi.fn(),
  fetchAgents: vi.fn(),
  fetchApprovals: vi.fn(),
  fetchArtifacts: vi.fn(),
  fetchMessages: vi.fn(),
  fetchProjects: vi.fn(),
  fetchRuns: vi.fn(),
  fetchSessionMembers: vi.fn(),
  fetchSessions: vi.fn(),
  fetchSystemHealth: vi.fn(),
  pickProjectFolder: vi.fn(),
  renameSession: vi.fn(),
  updateProject: vi.fn(),
}));

vi.mock("../api/client", () => apiMocks);

vi.mock("../api/wsClient", () => ({
  WSClient: class {
    on(_event: string, _handler: (event: Record<string, unknown>) => void) {}
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
}

const projects: Project[] = [
  {
    id: "p-a",
    name: "项目 A",
    workspacePath: "D:/workspace/a",
    status: "ready",
    fileCount: 0,
    totalSizeBytes: 0,
    createdAt: "2026-06-06T00:00:00.000Z",
  },
  {
    id: "p-b",
    name: "项目 B",
    workspacePath: "D:/workspace/b",
    status: "ready",
    fileCount: 0,
    totalSizeBytes: 0,
    createdAt: "2026-06-06T00:00:00.000Z",
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
});
