import { create } from "zustand";
import type { Session, AgentConfig, Provider } from "../types";

interface SessionState {
  sessions: Session[];
  agents: AgentConfig[];
  providers: Provider[];
  sidebarTab: "sessions" | "agents" | "settings";
  setSessions: (sessions: Session[]) => void;
  setAgents: (agents: AgentConfig[]) => void;
  setProviders: (providers: Provider[]) => void;
  setSidebarTab: (tab: "sessions" | "agents" | "settings") => void;
  updateSession: (session: Session) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  agents: [],
  providers: [],
  sidebarTab: "sessions",
  setSessions: (sessions) => set({ sessions }),
  setAgents: (agents) => set({ agents }),
  setProviders: (providers) => set({ providers }),
  setSidebarTab: (tab) => set({ sidebarTab: tab }),
  updateSession: (session) => set((s) => ({
    sessions: s.sessions.map((sess) => sess.id === session.id ? session : sess),
  })),
}));
