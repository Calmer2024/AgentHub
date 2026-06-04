import { useCallback, useEffect, useRef, useState } from "react";
import {
  archiveProject,
  createGroupSession,
  createProject,
  createSession,
  deleteSession,
  fetchAgents,
  fetchArtifacts,
  fetchMessages,
  fetchProjects,
  fetchProviders,
  fetchSessionMembers,
  fetchSessions,
  pickProjectFolder,
  renameSession,
  summarizeSession,
  updateSessionAgent,
} from "../api/client";
import { WSClient } from "../api/wsClient";
import { useChatStore } from "../stores/chatStore";
import { useSessionStore } from "../stores/sessionStore";
import type { AgentConfig, ProjectCreateInput } from "../types";

export function useWorkspaceRuntime() {
  const {
    currentSessionId,
    setCurrentSessionId,
    setMessages,
    setArtifacts,
    appendStreamingToken,
    setStreamingError,
    clearCollab,
  } = useChatStore();
  const {
    projects, currentProjectId, sessions, agents, providers, sidebarTab,
    setProjects, setCurrentProjectId,
    setSessions, setAgents, setProviders, setSidebarTab, updateSession,
  } = useSessionStore();

  const wsRef = useRef<WSClient | null>(null);
  const [sessionMembers, setSessionMembers] = useState<AgentConfig[]>([]);
  const [creatingProject, setCreatingProject] = useState(false);

  useEffect(() => {
    if (!currentSessionId) return;
    const ws = new WSClient();
    wsRef.current = ws;

    ws.on("token", (data) => {
      if (data.token && typeof data.token === "string") {
        appendStreamingToken(data.token);
      }
    });
    ws.on("message.completed", () => {
      fetchMessages(currentSessionId).then(setMessages);
      fetchArtifacts(currentSessionId).then(setArtifacts).catch(() => {});
    });
    ws.on("agent.changed", (data) => {
      if (typeof data.agentConfigId !== "string") return;
      const sess = sessions.find((s) => s.id === currentSessionId);
      if (sess) updateSession({ ...sess, agentConfigId: data.agentConfigId });
    });

    ws.connect(currentSessionId);
    return () => { ws.disconnect(); };
  }, [appendStreamingToken, currentSessionId, sessions, setArtifacts, setMessages, updateSession]);

  const loadSessionsForProject = useCallback(async (projectId: string | null) => {
    if (!projectId) {
      setSessions([]);
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
      return;
    }
    try {
      const loaded = await fetchSessions(projectId);
      setSessions(loaded);
      const currentStillVisible = loaded.some((session) => session.id === currentSessionId);
      if (!currentStillVisible) {
        const first = loaded[0] ?? null;
        setCurrentSessionId(first?.id ?? null);
        if (first) {
          try { setMessages(await fetchMessages(first.id)); } catch { setMessages([]); }
          try { setArtifacts(await fetchArtifacts(first.id)); } catch { setArtifacts([]); }
        } else {
          setMessages([]);
          setArtifacts([]);
        }
      }
    } catch {
      setSessions([]);
    }
  }, [currentSessionId, setArtifacts, setCurrentSessionId, setMessages, setSessions]);

  const loadData = useCallback(async () => {
    try {
      const loadedProjects = await fetchProjects();
      setProjects(loadedProjects);
      const nextProjectId = currentProjectId ?? loadedProjects[0]?.id ?? null;
      if (nextProjectId !== currentProjectId) setCurrentProjectId(nextProjectId);
      await loadSessionsForProject(nextProjectId);
    } catch { /* ignore bootstrap failures */ }
    try { setAgents(await fetchAgents()); } catch { /* ignore */ }
    try { setProviders(await fetchProviders()); } catch { /* ignore */ }
  }, [
    currentProjectId,
    loadSessionsForProject,
    setAgents,
    setCurrentProjectId,
    setProjects,
    setProviders,
  ]);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => { loadSessionsForProject(currentProjectId); }, [currentProjectId, loadSessionsForProject]);

  const handleSelectSession = async (id: string) => {
    setCurrentSessionId(id);
    setMessages([]);
    setArtifacts([]);
    setStreamingError(null);
    try { setMessages(await fetchMessages(id)); } catch { /* ignore */ }
    try { setArtifacts(await fetchArtifacts(id)); } catch { /* ignore */ }

    const sess = sessions.find((s) => s.id === id);
    if (sess?.mode !== "group") {
      setSessionMembers([]);
      return;
    }
    try {
      const members = await fetchSessionMembers(id);
      setSessionMembers(members.map((m) => ({
        id: m.agentConfigId,
        name: m.agentName,
      } as AgentConfig)));
    } catch {
      setSessionMembers([]);
    }
  };

  const handleSelectProject = (id: string) => {
    if (id === currentProjectId) return;
    setCurrentProjectId(id);
    setCurrentSessionId(null);
    setMessages([]);
    setArtifacts([]);
    setStreamingError(null);
  };

  const handleCreateProject = async (data: ProjectCreateInput) => {
    setCreatingProject(true);
    try {
      const project = await createProject(data);
      setProjects([project, ...projects]);
      setCurrentProjectId(project.id);
      setSessions([]);
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
      setSidebarTab("sessions");
    } finally {
      setCreatingProject(false);
    }
  };

  const handleCreateBlankProject = async () => {
    const name = `项目 ${new Date().toLocaleString("zh-CN", {
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
    setProjects(remaining);
    if (currentProjectId === id) {
      const nextId = remaining[0]?.id ?? null;
      setCurrentProjectId(nextId);
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
    }
  };

  const handleNewSession = async () => {
    if (!currentProjectId) return;
    const s = await createSession(undefined, undefined, currentProjectId);
    setSessions([s, ...sessions]);
    setCurrentSessionId(s.id);
    setMessages([]);
    setArtifacts([]);
    setStreamingError(null);
  };

  const handleCreateGroup = async (title: string, selectedIds: string[]) => {
    if (!currentProjectId) return;
    const s = await createGroupSession(title || "群聊", selectedIds, currentProjectId);
    setSessions([s, ...sessions]);
    setCurrentSessionId(s.id);
    setMessages([]);
    setArtifacts([]);
    setStreamingError(null);
    clearCollab(s.id);
  };

  const handleDeleteSession = async (id: string) => {
    await deleteSession(id);
    setSessions(sessions.filter((s) => s.id !== id));
    if (currentSessionId === id) {
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
    }
    clearCollab(id);
  };

  const handleRenameSession = async (id: string, title: string) => {
    updateSession(await renameSession(id, title));
  };

  const handleSummarizeSession = async (id: string) => {
    updateSession(await summarizeSession(id));
  };

  const handleSwitchAgent = async (agentId: string) => {
    if (!currentSessionId) return;
    try { updateSession(await updateSessionAgent(currentSessionId, agentId)); } catch { /* ignore */ }
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
    providers,
    sidebarTab,
    creatingProject,
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
    handleSelectSession,
    handleNewSession,
    handleCreateGroup,
    handleDeleteSession,
    handleRenameSession,
    handleSummarizeSession,
    handleSwitchAgent,
  };
}
