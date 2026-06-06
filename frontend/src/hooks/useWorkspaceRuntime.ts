import { useCallback, useEffect, useRef, useState } from "react";
import {
  archiveProject,
  createGroupSession,
  createProject,
  createSession,
  deleteProject,
  deleteSession,
  fetchAgents,
  fetchApprovals,
  fetchArtifacts,
  fetchMessages,
  fetchProjects,
  fetchRunTasks,
  fetchRuns,
  fetchSessionMembers,
  fetchSessions,
  fetchSystemHealth,
  pickProjectFolder,
  renameSession,
  updateProject,
} from "../api/client";
import { WSClient } from "../api/wsClient";
import { useChatStore } from "../stores/chatStore";
import { useSessionStore } from "../stores/sessionStore";
import type {
  AgentConfig, ApprovalCheckpoint, Artifact, ExecutionTraceItem, ProjectCreateInput, RunRead, TaskRead,
} from "../types";
import { chinaNowIso, formatChinaDateTime } from "../utils/time";

export function useWorkspaceRuntime() {
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const setCurrentSessionId = useChatStore((state) => state.setCurrentSessionId);
  const setMessages = useChatStore((state) => state.setMessages);
  const setMessagesForSession = useChatStore((state) => state.setMessagesForSession);
  const setArtifacts = useChatStore((state) => state.setArtifacts);
  const setArtifactsForSession = useChatStore((state) => state.setArtifactsForSession);
  const setApprovalsForSession = useChatStore((state) => state.setApprovalsForSession);
  const setRunsForSession = useChatStore((state) => state.setRunsForSession);
  const setTasksForRun = useChatStore((state) => state.setTasksForRun);
  const upsertRun = useChatStore((state) => state.upsertRun);
  const upsertTask = useChatStore((state) => state.upsertTask);
  const upsertApproval = useChatStore((state) => state.upsertApproval);
  const upsertArtifact = useChatStore((state) => state.upsertArtifact);
  const clearRuntimeState = useChatStore((state) => state.clearRuntimeState);
  const setSystemHealth = useChatStore((state) => state.setSystemHealth);
  const setStreamingError = useChatStore((state) => state.setStreamingError);
  const appendAgentStreamingToken = useChatStore((state) => state.appendAgentStreamingToken);
  const appendExecutionTraceItem = useChatStore((state) => state.appendExecutionTraceItem);
  const ensureAgentMessage = useChatStore((state) => state.ensureAgentMessage);
  const finalizeExecutionTrace = useChatStore((state) => state.finalizeExecutionTrace);
  const clearCollab = useChatStore((state) => state.clearCollab);
  const resetSessionView = useChatStore((state) => state.resetSessionView);
  const clearSessionCache = useChatStore((state) => state.clearSessionCache);
  const projects = useSessionStore((state) => state.projects);
  const currentProjectId = useSessionStore((state) => state.currentProjectId);
  const sessions = useSessionStore((state) => state.sessions);
  const agents = useSessionStore((state) => state.agents);
  const sidebarTab = useSessionStore((state) => state.sidebarTab);
  const setProjects = useSessionStore((state) => state.setProjects);
  const setCurrentProjectId = useSessionStore((state) => state.setCurrentProjectId);
  const setSessions = useSessionStore((state) => state.setSessions);
  const setAgents = useSessionStore((state) => state.setAgents);
  const setSidebarTab = useSessionStore((state) => state.setSidebarTab);
  const updateSession = useSessionStore((state) => state.updateSession);

  const wsRef = useRef<WSClient | null>(null);
  const sessionsByProjectRef = useRef<Record<string, ReturnType<typeof useSessionStore.getState>["sessions"]>>({});
  const projectRequestRef = useRef(0);
  const sessionRequestRef = useRef<Record<string, number>>({});
  const memberRequestRef = useRef(0);
  const [sessionMembers, setSessionMembers] = useState<AgentConfig[]>([]);
  const [creatingProject, setCreatingProject] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionHydrating, setSessionHydrating] = useState(false);

  useEffect(() => {
    if (!currentSessionId) return;
    const ws = new WSClient();
    wsRef.current = ws;

    ws.on("token", () => {
      // The active sender already receives chat tokens through SSE.
      // Keeping WS tokens out avoids duplicated text in the current tab.
    });
    ws.on("message.completed", (data) => {
      const eventSessionId = typeof data.sessionId === "string" ? data.sessionId : currentSessionId;
      if (eventSessionId !== currentSessionId) return;
      if (useChatStore.getState().isSessionStreaming(eventSessionId)) return;
      fetchMessages(eventSessionId).then((messages) => setMessagesForSession(eventSessionId, messages));
      fetchArtifacts(eventSessionId)
        .then((artifacts) => setArtifactsForSession(eventSessionId, artifacts))
        .catch(() => {});
    });
    ws.on("run.status_changed", (data) => {
      const run = normalizeRunEvent(data.run);
      if (!run) return;
      upsertRun(run);
      void fetchRunTasks(run.id)
        .then((tasks) => setTasksForRun(run.id, tasks))
        .catch(() => {});
    });
    ws.on("task.status_changed", (data) => {
      const task = normalizeTaskEvent(data.task);
      if (task) upsertTask(task);
    });
    ws.on("approval.created", (data) => {
      const approval = normalizeApprovalEvent(data.approval);
      if (approval) upsertApproval(approval);
    });
    ws.on("approval.status_changed", (data) => {
      const approval = normalizeApprovalEvent(data.approval);
      if (approval) upsertApproval(approval);
    });
    ws.on("artifact.created", (data) => {
      const artifact = normalizeArtifactEvent(data.artifact ?? data);
      if (artifact) upsertArtifact(artifact);
    });
    ws.on("agent.start", (data) => {
      const eventSessionId = typeof data.sessionId === "string" ? data.sessionId : currentSessionId;
      const messageId = typeof data.messageId === "string" ? data.messageId : "";
      const agentName = typeof data.agentName === "string" ? data.agentName : "Agent";
      if (!messageId || eventSessionId !== currentSessionId) return;
      ensureAgentMessage({
        id: messageId,
        sessionId: eventSessionId,
        agentName,
        agentId: typeof data.agentId === "string" ? data.agentId : null,
        role: typeof data.role === "string" ? data.role : "executor",
        phase: typeof data.phase === "number" ? data.phase : null,
        task: typeof data.task === "string" ? data.task : null,
      });
    });
    ws.on("agent.output", (data) => {
      const eventSessionId = typeof data.sessionId === "string" ? data.sessionId : currentSessionId;
      const messageId = typeof data.messageId === "string" ? data.messageId : "";
      const agentName = typeof data.agentName === "string" ? data.agentName : "Agent";
      const token = typeof data.token === "string" ? data.token : "";
      if (!messageId || !token || eventSessionId !== currentSessionId) return;
      appendAgentStreamingToken(messageId, agentName, token);
    });
    ws.on("agent.trace.delta", (data) => {
      const eventSessionId = typeof data.sessionId === "string" ? data.sessionId : currentSessionId;
      const messageId = typeof data.messageId === "string" ? data.messageId : "";
      if (!messageId || eventSessionId !== currentSessionId) return;
      const item = data.item;
      if (!item || typeof item !== "object") return;
      appendExecutionTraceItem(messageId, item as ExecutionTraceItem, {
        agentName: typeof data.agentName === "string" ? data.agentName : undefined,
        cliTool: typeof data.cliTool === "string" ? data.cliTool : undefined,
        processId: typeof data.processId === "string" ? data.processId : undefined,
      });
    });
    ws.on("agent.process.completed", (data) => {
      const eventSessionId = typeof data.sessionId === "string" ? data.sessionId : currentSessionId;
      const messageId = typeof data.messageId === "string" ? data.messageId : "";
      if (!messageId || eventSessionId !== currentSessionId) return;
      finalizeExecutionTrace(
        messageId,
        data.exitCode === 0 || data.exitCode == null ? "completed" : "error",
        typeof data.exitCode === "number" ? data.exitCode : null,
      );
    });
    ws.on("agent.changed", (data) => {
      if (typeof data.agentConfigId !== "string") return;
      const sess = sessions.find((s) => s.id === currentSessionId);
      if (sess) updateSession({ ...sess, agentConfigId: data.agentConfigId });
    });

    ws.connect(currentSessionId);
    return () => { ws.disconnect(); };
  }, [
    currentSessionId,
    sessions,
    setArtifactsForSession,
    setMessagesForSession,
    appendAgentStreamingToken,
    appendExecutionTraceItem,
    ensureAgentMessage,
    finalizeExecutionTrace,
    setTasksForRun,
    upsertApproval,
    upsertArtifact,
    upsertRun,
    upsertTask,
    updateSession,
  ]);

  useEffect(() => {
    fetchSystemHealth({ projectId: currentProjectId, sessionId: currentSessionId })
      .then(setSystemHealth)
      .catch(() => setSystemHealth(null));
  }, [currentProjectId, currentSessionId, setSystemHealth]);

  const hydrateSession = useCallback(async (id: string) => {
    const requestId = (sessionRequestRef.current[id] ?? 0) + 1;
    sessionRequestRef.current[id] = requestId;
    setSessionHydrating(true);
    const [messages, artifacts, runs, approvals] = await Promise.allSettled([
      fetchMessages(id),
      fetchArtifacts(id),
      fetchRuns(id),
      fetchApprovals(id),
    ]);
    if (sessionRequestRef.current[id] !== requestId) return;
    if (messages.status === "fulfilled") setMessagesForSession(id, messages.value);
    if (artifacts.status === "fulfilled") setArtifactsForSession(id, artifacts.value);
    if (runs.status === "fulfilled") {
      setRunsForSession(id, runs.value);
      void Promise.allSettled(runs.value.map(async (run) => {
        setTasksForRun(run.id, await fetchRunTasks(run.id));
      }));
    }
    if (approvals.status === "fulfilled") setApprovalsForSession(id, approvals.value);
    if (messages.status === "rejected") setMessagesForSession(id, []);
    if (artifacts.status === "rejected") setArtifactsForSession(id, []);
    if (runs.status === "rejected") setRunsForSession(id, []);
    if (approvals.status === "rejected") setApprovalsForSession(id, []);
    if (useChatStore.getState().currentSessionId === id) setSessionHydrating(false);
  }, [
    setApprovalsForSession,
    setArtifactsForSession,
    setMessagesForSession,
    setRunsForSession,
    setTasksForRun,
  ]);

  const loadSessionsForProject = useCallback(async (projectId: string | null) => {
    const requestId = ++projectRequestRef.current;
    if (!projectId) {
      setSessions([]);
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
      resetSessionView(null);
      setSessionsLoading(false);
      setSessionHydrating(false);
      return;
    }
    const cached = sessionsByProjectRef.current[projectId];
    if (cached) {
      setSessions(cached);
      const activeSessionId = useChatStore.getState().currentSessionId;
      if (!cached.some((session) => session.id === activeSessionId)) {
        const first = cached[0] ?? null;
        setCurrentSessionId(first?.id ?? null);
        if (first) void hydrateSession(first.id);
        else resetSessionView(null);
      }
    } else {
      setSessions([]);
      setSessionsLoading(true);
    }
    try {
      const loaded = await fetchSessions(projectId);
      if (requestId !== projectRequestRef.current || useSessionStore.getState().currentProjectId !== projectId) {
        return;
      }
      sessionsByProjectRef.current[projectId] = loaded;
      setSessions(loaded);
      const activeSessionId = useChatStore.getState().currentSessionId;
      const currentStillVisible = loaded.some((session) => session.id === activeSessionId);
      if (!currentStillVisible) {
        const first = loaded[0] ?? null;
        setCurrentSessionId(first?.id ?? null);
        if (first) {
          void hydrateSession(first.id);
        } else {
          setMessages([]);
          setArtifacts([]);
          resetSessionView(null);
          setSessionHydrating(false);
        }
      }
    } catch {
      if (requestId !== projectRequestRef.current) return;
      setSessions([]);
    } finally {
      if (requestId === projectRequestRef.current) setSessionsLoading(false);
    }
  }, [
    setArtifacts,
    hydrateSession,
    resetSessionView,
    setCurrentSessionId,
    setMessages,
    setSessions,
  ]);

  const loadData = useCallback(async () => {
    try {
      const [loadedProjects, loadedAgents] = await Promise.allSettled([
        fetchProjects(),
        fetchAgents(),
      ]);
      if (loadedProjects.status === "fulfilled") {
        setProjects(loadedProjects.value);
        const activeProjectId = useSessionStore.getState().currentProjectId;
        const nextProjectId = activeProjectId ?? loadedProjects.value[0]?.id ?? null;
        if (nextProjectId !== activeProjectId) setCurrentProjectId(nextProjectId);
        else if (activeProjectId) void loadSessionsForProject(activeProjectId);
      }
      if (loadedAgents.status === "fulfilled") setAgents(loadedAgents.value);
    } catch { /* ignore bootstrap failures */ }
  }, [
    loadSessionsForProject,
    setAgents,
    setCurrentProjectId,
    setProjects,
  ]);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => { loadSessionsForProject(currentProjectId); }, [currentProjectId, loadSessionsForProject]);

  const handleSelectSession = async (id: string) => {
    if (id === useChatStore.getState().currentSessionId) return;
    const memberRequestId = ++memberRequestRef.current;
    setCurrentSessionId(id);
    setStreamingError(null, id);
    void hydrateSession(id);

    const sess = sessions.find((s) => s.id === id);
    if (sess?.mode !== "group") {
      setSessionMembers([]);
      return;
    }
    try {
      const members = await fetchSessionMembers(id);
      if (memberRequestId !== memberRequestRef.current || useChatStore.getState().currentSessionId !== id) return;
      setSessionMembers(members.map((m) => ({
        id: m.agentConfigId,
        name: m.agentName,
      } as AgentConfig)));
    } catch {
      if (memberRequestId !== memberRequestRef.current) return;
      setSessionMembers([]);
    }
  };

  const handleSelectProject = (id: string) => {
    if (id === currentProjectId) return;
    memberRequestRef.current += 1;
    const cached = sessionsByProjectRef.current[id] ?? [];
    setCurrentProjectId(id);
    setSessions(cached);
    const first = cached[0] ?? null;
    setCurrentSessionId(first?.id ?? null);
    if (first) resetSessionView(first.id);
    else {
      setMessages([]);
      setArtifacts([]);
      resetSessionView(null);
    }
    setSessionMembers([]);
    setSessionsLoading(!cached.length);
    setSessionHydrating(Boolean(first));
    setStreamingError(null);
  };

  const handleCreateProject = async (data: ProjectCreateInput) => {
    setCreatingProject(true);
    try {
      const project = await createProject(data);
      setProjects([project, ...projects]);
      sessionsByProjectRef.current[project.id] = [];
      setCurrentProjectId(project.id);
      setSessions([]);
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
      resetSessionView(null);
      setSidebarTab("sessions");
    } finally {
      setCreatingProject(false);
    }
  };

  const handleCreateBlankProject = async (inputName?: string) => {
    const name = inputName?.trim() || `项目 ${formatChinaDateTime(chinaNowIso(), {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })}`;
    await handleCreateProject({ name });
  };

  const handlePickExistingFolder = async () => {
    setCreatingProject(true);
    try {
      const folder = await pickProjectFolder();
      await handleCreateProject({
        name: folder.folderName || "新项目",
        workspacePath: folder.workspacePath,
        folderToken: folder.folderToken,
      });
    } finally {
      setCreatingProject(false);
    }
  };

  const handleArchiveProject = async (id: string) => {
    await archiveProject(id);
    const remaining = projects.filter((project) => project.id !== id);
    delete sessionsByProjectRef.current[id];
    setProjects(remaining);
    if (currentProjectId === id) {
      const nextId = remaining[0]?.id ?? null;
      setCurrentProjectId(nextId);
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
      resetSessionView(null);
    }
  };

  const handleRenameProject = async (id: string, name: string) => {
    const renamed = await updateProject(id, { name });
    setProjects(projects.map((project) => project.id === id ? renamed : project));
  };

  const handleDeleteProject = async (id: string, deleteFiles: boolean) => {
    await deleteProject(id, deleteFiles);
    const remaining = projects.filter((project) => project.id !== id);
    delete sessionsByProjectRef.current[id];
    setProjects(remaining);
    if (currentProjectId === id) {
      const nextId = remaining[0]?.id ?? null;
      setCurrentProjectId(nextId);
      setSessions([]);
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
      resetSessionView(null);
      setStreamingError(null);
    }
  };

  const handleNewSession = async (agentId?: string) => {
    if (!currentProjectId) return;
    const agent = agents.find((item) => item.id === agentId);
    const s = await createSession(agent?.name, agentId, currentProjectId);
    const nextSessions = [s, ...sessions];
    sessionsByProjectRef.current[currentProjectId] = nextSessions;
    setSessions(nextSessions);
    setCurrentSessionId(s.id);
    resetSessionView(s.id);
    setMessagesForSession(s.id, []);
    setArtifactsForSession(s.id, []);
    setRunsForSession(s.id, []);
    setApprovalsForSession(s.id, []);
    setStreamingError(null, s.id);
  };

  const handleCreateGroup = async (title: string, selectedIds: string[]) => {
    if (!currentProjectId) return;
    const s = await createGroupSession(title || "群聊", selectedIds, currentProjectId);
    const nextSessions = [s, ...sessions];
    sessionsByProjectRef.current[currentProjectId] = nextSessions;
    setSessions(nextSessions);
    setCurrentSessionId(s.id);
    resetSessionView(s.id);
    setMessagesForSession(s.id, []);
    setArtifactsForSession(s.id, []);
    setRunsForSession(s.id, []);
    setApprovalsForSession(s.id, []);
    setStreamingError(null, s.id);
    clearCollab(s.id);
  };

  const handleDeleteSession = async (id: string) => {
    await deleteSession(id);
    const nextSessions = sessions.filter((s) => s.id !== id);
    if (currentProjectId) sessionsByProjectRef.current[currentProjectId] = nextSessions;
    setSessions(nextSessions);
    if (currentSessionId === id) {
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
      clearRuntimeState(id);
    }
    clearSessionCache(id);
    clearCollab(id);
  };

  const handleRenameSession = async (id: string, title: string) => {
    const renamed = await renameSession(id, title);
    updateSession(renamed);
    if (renamed.projectId) {
      const cached = sessionsByProjectRef.current[renamed.projectId] ?? sessions;
      sessionsByProjectRef.current[renamed.projectId] = cached.map((session) => (
        session.id === renamed.id ? renamed : session
      ));
    }
  };

  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const currentProject = projects.find((p) => p.id === currentProjectId) ?? null;
  const currentAgent = agents.find((a) => a.id === currentSession?.agentConfigId) ?? null;
  const currentMode = currentSession?.mode ?? "single";

  return {
    projects,
    currentProjectId,
    currentProject,
    sessions,
    agents,
    sidebarTab,
    creatingProject,
    sessionsLoading,
    sessionHydrating,
    sessionMembers,
    currentAgent,
    currentMode,
    setSidebarTab,
    loadData,
    handleSelectProject,
    handleCreateProject,
    handleCreateBlankProject,
    handlePickExistingFolder,
    handleArchiveProject,
    handleRenameProject,
    handleDeleteProject,
    handleSelectSession,
    handleNewSession,
    handleCreateGroup,
    handleDeleteSession,
    handleRenameSession,
  };
}

function normalizeRunEvent(raw: unknown): RunRead | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (typeof data.id !== "string" || typeof data.sessionId !== "string") return null;
  const status = normalizeRunStatus(data.status);
  if (!status) return null;
  return {
    id: data.id,
    sessionId: data.sessionId,
    projectId: typeof data.projectId === "string" ? data.projectId : null,
    mode: typeof data.mode === "string" ? data.mode : "single",
    status,
    currentMessageId: typeof data.currentMessageId === "string" ? data.currentMessageId : null,
    startedAt: typeof data.startedAt === "string" ? data.startedAt : chinaNowIso(),
    updatedAt: typeof data.updatedAt === "string" ? data.updatedAt : chinaNowIso(),
    completedAt: typeof data.completedAt === "string" ? data.completedAt : null,
    cancelReason: typeof data.cancelReason === "string" ? data.cancelReason : null,
    metadata: isRecord(data.metadata) ? data.metadata : null,
  };
}

function normalizeTaskEvent(raw: unknown): TaskRead | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (typeof data.id !== "string" || typeof data.runId !== "string" || typeof data.sessionId !== "string") {
    return null;
  }
  const status = normalizeTaskStatus(data.status);
  if (!status) return null;
  return {
    id: data.id,
    runId: data.runId,
    sessionId: data.sessionId,
    agentId: typeof data.agentId === "string" ? data.agentId : null,
    messageId: typeof data.messageId === "string" ? data.messageId : null,
    name: typeof data.name === "string" ? data.name : "primary",
    role: typeof data.role === "string" ? data.role : null,
    phase: typeof data.phase === "number" ? data.phase : null,
    status,
    dependsOn: Array.isArray(data.dependsOn) ? data.dependsOn.map(String) : [],
    startedAt: typeof data.startedAt === "string" ? data.startedAt : null,
    completedAt: typeof data.completedAt === "string" ? data.completedAt : null,
    metadata: isRecord(data.metadata) ? data.metadata : null,
  };
}

function normalizeApprovalEvent(raw: unknown): ApprovalCheckpoint | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (
    typeof data.id !== "string"
    || typeof data.runId !== "string"
    || typeof data.taskId !== "string"
    || typeof data.sessionId !== "string"
  ) return null;
  const status = normalizeApprovalStatus(data.status);
  if (!status) return null;
  return {
    id: data.id,
    runId: data.runId,
    taskId: data.taskId,
    sessionId: data.sessionId,
    messageId: typeof data.messageId === "string" ? data.messageId : null,
    artifactId: typeof data.artifactId === "string" ? data.artifactId : null,
    artifactVersion: typeof data.artifactVersion === "number" ? data.artifactVersion : null,
    title: typeof data.title === "string" ? data.title : "等待确认",
    summary: typeof data.summary === "string" ? data.summary : "",
    status,
    reason: typeof data.reason === "string" ? data.reason : null,
    createdAt: typeof data.createdAt === "string" ? data.createdAt : chinaNowIso(),
    decidedAt: typeof data.decidedAt === "string" ? data.decidedAt : null,
    metadata: isRecord(data.metadata) ? data.metadata : null,
  };
}

function normalizeArtifactEvent(raw: unknown): Artifact | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const id = data.id ?? data.artifactId;
  if (typeof id !== "string") return null;
  const type = data.type ?? data.artifactType;
  if (type !== "code_diff" && type !== "web_preview" && type !== "document" && type !== "file_tree") return null;
  const sessionId = typeof data.sessionId === "string" ? data.sessionId : "";
  const messageId = typeof data.messageId === "string" ? data.messageId : "";
  if (!sessionId || !messageId) return null;
  return {
    id,
    sessionId,
    messageId,
    projectId: typeof data.projectId === "string" ? data.projectId : null,
    type,
    title: typeof data.title === "string" ? data.title : "产物",
    content: typeof data.content === "string" ? data.content : "",
    status: data.status === "rendering" || data.status === "error" ? data.status : "ready",
    version: typeof data.version === "number" ? data.version : 1,
    parentArtifactId: typeof data.parentArtifactId === "string" ? data.parentArtifactId : null,
    filePath: typeof data.filePath === "string" ? data.filePath : null,
    previewId: typeof data.previewId === "string" ? data.previewId : null,
    source: typeof data.source === "string" ? data.source : null,
    createdAt: typeof data.createdAt === "string" ? data.createdAt : chinaNowIso(),
  };
}

function normalizeRunStatus(value: unknown): RunRead["status"] | null {
  if (
    value === "queued" || value === "running" || value === "pausing"
    || value === "paused" || value === "cancelling" || value === "cancelled"
    || value === "completed" || value === "failed"
  ) return value;
  return null;
}

function normalizeTaskStatus(value: unknown): TaskRead["status"] | null {
  if (
    value === "pending" || value === "running" || value === "paused"
    || value === "completed" || value === "failed" || value === "cancelled"
    || value === "rejected"
  ) return value;
  return null;
}

function normalizeApprovalStatus(value: unknown): ApprovalCheckpoint["status"] | null {
  if (value === "pending_review" || value === "approved" || value === "rejected") return value;
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
