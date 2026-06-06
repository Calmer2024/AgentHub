import { create } from "zustand";
import type { Session, AgentConfig, Project } from "../types";

export type SidebarTab = "sessions" | "agents" | "debug";

interface SessionState {
  projects: Project[];
  currentProjectId: string | null;
  sessions: Session[];
  agents: AgentConfig[];
  sidebarTab: SidebarTab;
  setProjects: (projects: Project[]) => void;
  setCurrentProjectId: (id: string | null) => void;
  setSessions: (sessions: Session[]) => void;
  setAgents: (agents: AgentConfig[]) => void;
  setSidebarTab: (tab: SidebarTab) => void;
  updateSession: (session: Session) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  projects: [],
  currentProjectId: null,
  sessions: [],
  agents: [],
  sidebarTab: "sessions",
  setProjects: (projects) => set({ projects }),
  setCurrentProjectId: (id) => set({ currentProjectId: id }),
  setSessions: (sessions) => set({ sessions }),
  setAgents: (agents) => set({ agents }),
  setSidebarTab: (tab) => set({ sidebarTab: tab }),
  updateSession: (session) => set((s) => ({
    sessions: s.sessions.map((sess) => sess.id === session.id ? session : sess),
  })),
}));
