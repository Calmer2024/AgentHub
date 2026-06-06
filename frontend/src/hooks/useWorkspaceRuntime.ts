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
import type { AgentConfig, ProjectCreateInput } from "../types";
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
  const clearRuntimeState = useChatStore((state) => state.clearRuntimeState);
  const setSystemHealth = useChatStore((state) => state.setSystemHealth);
  const setStreamingError = useChatStore((state) => state.setStreamingError);
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
    if (runs.status === "fulfilled") setRunsForSession(id, runs.value);
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
    if (first) {
      resetSessionView(first.id);
      void hydrateSession(first.id);
    }
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
