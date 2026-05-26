import { create } from "zustand";
import type { Session, Message, Agent } from "../types";

interface ChatState {
  sessions: Session[];
  currentSessionId: string | null;
  messages: Message[];
  isStreaming: boolean;
  streamingError: string | null;
  agents: Agent[];
  settingsOpen: boolean;
  setSessions: (sessions: Session[]) => void;
  setCurrentSessionId: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  appendMessage: (msg: Message) => void;
  appendStreamingToken: (token: string) => void;
  setIsStreaming: (v: boolean) => void;
  setStreamingError: (error: string | null) => void;
  setAgents: (agents: Agent[]) => void;
  setSettingsOpen: (open: boolean) => void;
  updateSession: (session: Session) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  isStreaming: false,
  streamingError: null,
  agents: [],
  settingsOpen: false,
  setSessions: (sessions) => set({ sessions }),
  setCurrentSessionId: (id) => set({ currentSessionId: id }),
  setMessages: (messages) => set({ messages }),
  appendMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  appendStreamingToken: (token) => set((s) => {
    const lastMsg = s.messages[s.messages.length - 1];
    if (lastMsg && lastMsg.role === "assistant" && get().isStreaming) {
      return {
        messages: [
          ...s.messages.slice(0, -1),
          { ...lastMsg, content: lastMsg.content + token },
        ],
      };
    }
    return s;
  }),
  setIsStreaming: (v) => set({ isStreaming: v, streamingError: v ? get().streamingError : null }),
  setStreamingError: (error) => set({ streamingError: error }),
  setAgents: (agents) => set({ agents }),
  setSettingsOpen: (open) => set({ settingsOpen: open }),
  updateSession: (session) => set((s) => ({
    sessions: s.sessions.map((sess) => sess.id === session.id ? session : sess),
  })),
}));
