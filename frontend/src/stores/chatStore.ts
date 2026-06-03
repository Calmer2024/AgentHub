import { create } from "zustand";
import type { Message, RouteAgent, CollabTask, ChainStep, DAGPhase, Artifact } from "../types";

/** 每个会话的协作状态快照，切换会话时保留。 */
export interface CollabSnapshot {
  routeAgents: RouteAgent[] | null;
  collabTasks: CollabTask[];
  dagPhases: DAGPhase[];
  chainSteps: ChainStep[];
  orchestratorIntent: string | null;
  planSummary: string | null;
  collabCompleted: boolean;
  collabSummary: string | null;
}

function emptyCollab(): CollabSnapshot {
  return {
    routeAgents: null,
    collabTasks: [],
    dagPhases: [],
    chainSteps: [],
    orchestratorIntent: null,
    planSummary: null,
    collabCompleted: false,
    collabSummary: null,
  };
}

interface ChatState {
  currentSessionId: string | null;
  messages: Message[];
  artifacts: Artifact[];
  isStreaming: boolean;
  streamingError: string | null;
  replyTarget: Message | null;

  // === 协作状态 (per-session persisted) ===
  collabSnapshots: Record<string, CollabSnapshot>;
  getCollab: (sessionId: string) => CollabSnapshot;
  saveCollab: (sessionId: string, snap: CollabSnapshot) => void;
  clearCollab: (sessionId: string) => void;

  // === 原有 actions ===
  setCurrentSessionId: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  setArtifacts: (artifacts: Artifact[]) => void;
  upsertArtifact: (artifact: Artifact) => void;
  appendMessage: (msg: Message) => void;
  appendStreamingToken: (token: string) => void;
  appendAgentStreamingToken: (localId: string, agentName: string, token: string) => void;
  updateMessage: (id: string, patch: Partial<Message>) => void;
  replaceMessageContent: (id: string, content: string) => void;
  setReplyTarget: (message: Message | null) => void;
  setIsStreaming: (v: boolean) => void;
  setStreamingError: (error: string | null) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  currentSessionId: null,
  messages: [],
  artifacts: [],
  isStreaming: false,
  streamingError: null,
  replyTarget: null,
  collabSnapshots: {},

  getCollab: (sessionId) => get().collabSnapshots[sessionId] ?? emptyCollab(),
  saveCollab: (sessionId, snap) =>
    set((s) => ({ collabSnapshots: { ...s.collabSnapshots, [sessionId]: snap } })),
  clearCollab: (sessionId) =>
    set((s) => {
      const next = { ...s.collabSnapshots };
      delete next[sessionId];
      return { collabSnapshots: next };
    }),

  setCurrentSessionId: (id) => set({ currentSessionId: id }),
  setMessages: (messages) => set({ messages }),
  setArtifacts: (artifacts) => set({ artifacts }),
  upsertArtifact: (artifact) =>
    set((s) => {
      const withoutChain = s.artifacts.filter((a) => (
        a.id !== artifact.id
        && a.parentArtifactId !== artifact.id
        && artifact.parentArtifactId !== a.id
      ));
      return { artifacts: [artifact, ...withoutChain] };
    }),
  appendMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  appendStreamingToken: (token) =>
    set((s) => {
      const msgs = s.messages;
      const lastMsg = msgs[msgs.length - 1];
      if (lastMsg && lastMsg.role === "assistant" && get().isStreaming) {
        return { messages: [...msgs.slice(0, -1), { ...lastMsg, content: lastMsg.content + token }] };
      }
      return s;
    }),
  appendAgentStreamingToken: (localId, agentName, token) =>
    set((s) => {
      const msgs = [...s.messages];
      const idx = msgs.findIndex((m) => m.id === localId);
      if (idx >= 0) {
        msgs[idx] = { ...msgs[idx], content: msgs[idx].content + token, agentName };
      }
      return { messages: msgs };
    }),
  updateMessage: (id, patch) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    })),
  replaceMessageContent: (id, content) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, content } : m)),
    })),
  setReplyTarget: (message) => set({ replyTarget: message }),
  setIsStreaming: (v) => set({ isStreaming: v }),
  setStreamingError: (error) => set({ streamingError: error }),
}));
