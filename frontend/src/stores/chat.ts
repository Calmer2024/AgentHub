import { create } from "zustand";
import type { Session, Message, AgentConfig, Provider } from "../types";

interface ChatState {
  sessions: Session[];
  currentSessionId: string | null;
  messages: Message[];
  isStreaming: boolean;
  streamingError: string | null;
  agents: AgentConfig[];
  providers: Provider[];
  sidebarTab: "sessions" | "agents" | "settings";
  setSessions: (sessions: Session[]) => void;
  setCurrentSessionId: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  appendMessage: (msg: Message) => void;
  appendStreamingToken: (token: string) => void;
  appendAgentStreamingToken: (localId: string, agentName: string, token: string) => void;
  setIsStreaming: (v: boolean) => void;
  setStreamingError: (error: string | null) => void;
  setAgents: (agents: AgentConfig[]) => void;
  setProviders: (providers: Provider[]) => void;
  setSidebarTab: (tab: "sessions" | "agents" | "settings") => void;
  updateSession: (session: Session) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  isStreaming: false,
  streamingError: null,
  agents: [],
  providers: [],
  sidebarTab: "sessions",
  setSessions: (sessions) => set({ sessions }),
  setCurrentSessionId: (id) => set({ currentSessionId: id }),
  setMessages: (messages) => set({ messages }),
  appendMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  appendStreamingToken: (token) => set((s) => {
    const lastMsg = s.messages[s.messages.length - 1];
    if (lastMsg && lastMsg.role === "assistant" && get().isStreaming) {
      return { messages: [...s.messages.slice(0, -1), { ...lastMsg, content: lastMsg.content + token }] };
    }
    return s;
  }),
  appendAgentStreamingToken: (localId, agentName, token) => set((s) => {
    const msgs = [...s.messages];
    const idx = msgs.findIndex((m) => m.id === localId);
    if (idx >= 0) {
      msgs[idx] = { ...msgs[idx], content: msgs[idx].content + token, agentName };
    }
    return { messages: msgs };
  }),
  setIsStreaming: (v) => set({ isStreaming: v, streamingError: v ? get().streamingError : null }),
  setStreamingError: (error) => set({ streamingError: error }),
  setAgents: (agents) => set({ agents }),
  setProviders: (providers) => set({ providers }),
  setSidebarTab: (tab) => set({ sidebarTab: tab }),
  updateSession: (session) => set((s) => ({
    sessions: s.sessions.map((sess) => sess.id === session.id ? session : sess),
  })),
}));
