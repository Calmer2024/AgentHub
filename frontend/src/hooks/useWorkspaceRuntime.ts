import { useCallback, useEffect, useRef, useState } from "react";
import {
  archiveProject,
  createGroupSession,
  createProject,
  createSession,
  deleteProject,
  deleteSession,
  fetchAgents,
  fetchArtifacts,
  fetchMessages,
  fetchProjects,
  fetchSessionMembers,
  fetchSessions,
  pickProjectFolder,
  renameSession,
  summarizeSession,
  updateProject,
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
    setMessagesForSession,
    setArtifacts,
    setArtifactsForSession,
    setStreamingError,
    clearCollab,
  } = useChatStore();
  const {
    projects, currentProjectId, sessions, agents, sidebarTab,
    setProjects, setCurrentProjectId,
    setSessions, setAgents, setSidebarTab, updateSession,
  } = useSessionStore();

  const wsRef = useRef<WSClient | null>(null);
  const [sessionMembers, setSessionMembers] = useState<AgentConfig[]>([]);
  const [creatingProject, setCreatingProject] = useState(false);

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
      const activeRunId = useChatStore.getState().activeRunId;
      if (activeRunId?.includes(`run-${eventSessionId}-`)) return;
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
          try {
            setMessagesForSession(first.id, await fetchMessages(first.id));
          } catch {
            setMessagesForSession(first.id, []);
          }
          try {
            setArtifactsForSession(first.id, await fetchArtifacts(first.id));
          } catch {
            setArtifactsForSession(first.id, []);
          }
        } else {
          setMessages([]);
          setArtifacts([]);
        }
      }
    } catch {
      setSessions([]);
    }
  }, [
    currentSessionId,
    setArtifacts,
    setArtifactsForSession,
    setCurrentSessionId,
    setMessages,
    setMessagesForSession,
    setSessions,
  ]);

  const loadData = useCallback(async () => {
    try {
      const loadedProjects = await fetchProjects();
      setProjects(loadedProjects);
      const nextProjectId = currentProjectId ?? loadedProjects[0]?.id ?? null;
      if (nextProjectId !== currentProjectId) setCurrentProjectId(nextProjectId);
      await loadSessionsForProject(nextProjectId);
    } catch { /* ignore bootstrap failures */ }
    try { setAgents(await fetchAgents()); } catch { /* ignore */ }
  }, [
    currentProjectId,
    loadSessionsForProject,
    setAgents,
    setCurrentProjectId,
    setProjects,
  ]);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => { loadSessionsForProject(currentProjectId); }, [currentProjectId, loadSessionsForProject]);

  const handleSelectSession = async (id: string) => {
    setCurrentSessionId(id);
    setMessages([]);
    setArtifacts([]);
    setStreamingError(null);
    try {
      setMessagesForSession(id, await fetchMessages(id));
    } catch { /* ignore */ }
    try {
      setArtifactsForSession(id, await fetchArtifacts(id));
    } catch { /* ignore */ }

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

  const handleCreateBlankProject = async (inputName?: string) => {
    const name = inputName?.trim() || `项目 ${new Date().toLocaleString("zh-CN", {
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

  const handleRenameProject = async (id: string, name: string) => {
    const renamed = await updateProject(id, { name });
    setProjects(projects.map((project) => project.id === id ? renamed : project));
  };

  const handleDeleteProject = async (id: string, deleteFiles: boolean) => {
    await deleteProject(id, deleteFiles);
    const remaining = projects.filter((project) => project.id !== id);
    setProjects(remaining);
    if (currentProjectId === id) {
      const nextId = remaining[0]?.id ?? null;
      setCurrentProjectId(nextId);
      setSessions([]);
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
      setStreamingError(null);
    }
  };

  const handleNewSession = async (agentId?: string) => {
    if (!currentProjectId) return;
    const agent = agents.find((item) => item.id === agentId);
    const s = await createSession(agent?.name, agentId, currentProjectId);
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
    handleSummarizeSession,
  };
}
