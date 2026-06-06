import { create } from "zustand";
import type {
  Message, RouteAgent, CollabTask, ChainStep, DAGPhase, Artifact,
  InteractivePrompt, ExecutionTraceItem,
  DraftOrchestratorPlan,
} from "../types";

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
  draftPlan: DraftOrchestratorPlan | null;
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
    draftPlan: null,
  };
}

function mergeServerMessages(current: Message[], incoming: Message[]) {
  const incomingIds = new Set(incoming.map((message) => message.id));
  const liveAgentMessages = current.filter((message) => (
    !incomingIds.has(message.id)
    && !message.id.startsWith("local-")
    && message.sourceType === "agent"
    && Boolean(message.isCollaborating || message.agentRole)
    && (
      message.metadata?.executionTrace?.status === "running"
      || message.id.startsWith("msg_agent_")
    )
  ));
  return [...incoming, ...liveAgentMessages];
}

interface ChatState {
  currentSessionId: string | null;
  messages: Message[];
  artifacts: Artifact[];
  isStreaming: boolean;
  activeRunId: string | null;
  latestRunId: string | null;
  streamingError: string | null;
  replyTarget: Message | null;
  activeProgress: string | null;
  interactivePrompts: InteractivePrompt[];

  // === 协作状态 (per-session persisted) ===
  collabSnapshots: Record<string, CollabSnapshot>;
  getCollab: (sessionId: string) => CollabSnapshot;
  saveCollab: (sessionId: string, snap: CollabSnapshot) => void;
  clearCollab: (sessionId: string) => void;

  // === 原有 actions ===
  setCurrentSessionId: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  setMessagesForSession: (sessionId: string, messages: Message[]) => void;
  setArtifacts: (artifacts: Artifact[]) => void;
  setArtifactsForSession: (sessionId: string, artifacts: Artifact[]) => void;
  upsertArtifact: (artifact: Artifact) => void;
  appendMessage: (msg: Message) => void;
  appendStreamingToken: (token: string) => void;
  appendStreamingTokenToMessage: (messageId: string, token: string) => void;
  appendAgentStreamingToken: (localId: string, agentName: string, token: string) => void;
  ensureAgentMessage: (input: {
    id: string;
    sessionId: string;
    agentName: string;
    agentId?: string | null;
    role?: string | null;
    phase?: number | null;
    task?: string | null;
  }) => void;
  bindMessageId: (localId: string, serverId: string) => void;
  appendExecutionTraceItem: (
    messageId: string,
    item: ExecutionTraceItem,
    seed?: { agentName?: string; cliTool?: string; processId?: string },
  ) => void;
  finalizeExecutionTrace: (messageId: string, status: "completed" | "error", exitCode?: number | null) => void;
  updateMessage: (id: string, patch: Partial<Message>) => void;
  replaceMessageContent: (id: string, content: string) => void;
  setReplyTarget: (message: Message | null) => void;
  setActiveProgress: (progress: string | null) => void;
  addInteractivePrompt: (prompt: InteractivePrompt) => void;
  removeInteractivePrompt: (processId: string) => void;
  clearRuntimeNotices: () => void;
  startStreamRun: (runId: string) => void;
  finishStreamRun: (runId: string) => void;
  setIsStreaming: (v: boolean) => void;
  setStreamingError: (error: string | null) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  currentSessionId: null,
  messages: [],
  artifacts: [],
  isStreaming: false,
  activeRunId: null,
  latestRunId: null,
  streamingError: null,
  replyTarget: null,
  activeProgress: null,
  interactivePrompts: [],
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
  setMessagesForSession: (sessionId, messages) =>
    set((s) => (s.currentSessionId === sessionId ? {
      messages: mergeServerMessages(s.messages, messages),
    } : {})),
  setArtifacts: (artifacts) => set({ artifacts }),
  setArtifactsForSession: (sessionId, artifacts) =>
    set((s) => (s.currentSessionId === sessionId ? { artifacts } : {})),
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
  appendStreamingTokenToMessage: (messageId, token) =>
    set((s) => ({
      messages: s.messages.map((m) => (
        m.id === messageId ? { ...m, content: m.content + token } : m
      )),
    })),
  appendAgentStreamingToken: (localId, agentName, token) =>
    set((s) => {
      const msgs = [...s.messages];
      const idx = msgs.findIndex((m) => m.id === localId);
      if (idx >= 0) {
        msgs[idx] = { ...msgs[idx], content: msgs[idx].content + token, agentName };
      }
      return { messages: msgs };
    }),
  ensureAgentMessage: (input) =>
    set((s) => {
      if (s.currentSessionId !== input.sessionId) return {};
      if (s.messages.some((message) => message.id === input.id)) return {};
      return {
        messages: [
          ...s.messages,
          {
            id: input.id,
            sessionId: input.sessionId,
            role: "assistant",
            content: "",
            agentName: input.agentName,
            sourceType: "agent",
            sourceId: input.agentId ?? null,
            sourceName: input.agentName,
            agentRole: input.role ?? "executor",
            phase: input.phase ?? null,
            taskName: input.task ?? null,
            isCollaborating: true,
            createdAt: new Date().toISOString(),
          },
        ],
      };
    }),
  bindMessageId: (localId, serverId) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === localId ? { ...m, id: serverId } : m)),
    })),
  appendExecutionTraceItem: (messageId, item, seed) =>
    set((s) => ({
      messages: s.messages.map((m) => {
        if (m.id !== messageId) return m;
        const metadata = { ...(m.metadata ?? {}) };
        const current = metadata.executionTrace;
        metadata.executionTrace = {
          status: current?.status ?? "running",
          agentName: current?.agentName ?? seed?.agentName ?? m.agentName,
          cliTool: current?.cliTool ?? seed?.cliTool ?? null,
          workspacePath: current?.workspacePath ?? null,
          startedAt: current?.startedAt ?? item.timestamp,
          completedAt: current?.completedAt ?? null,
          processId: current?.processId ?? seed?.processId ?? item.processId ?? null,
          exitCode: current?.exitCode ?? null,
          items: [...(current?.items ?? []), item].slice(-300),
        };
        return { ...m, metadata };
      }),
    })),
  finalizeExecutionTrace: (messageId, status, exitCode = null) =>
    set((s) => ({
      messages: s.messages.map((m) => {
        if (m.id !== messageId || !m.metadata?.executionTrace) return m;
        return {
          ...m,
          metadata: {
            ...m.metadata,
            executionTrace: {
              ...m.metadata.executionTrace,
              status,
              exitCode,
              completedAt: new Date().toISOString(),
            },
          },
        };
      }),
    })),
  updateMessage: (id, patch) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    })),
  replaceMessageContent: (id, content) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, content } : m)),
    })),
  setReplyTarget: (message) => set({ replyTarget: message }),
  setActiveProgress: (progress) => set({ activeProgress: progress }),
  addInteractivePrompt: (prompt) =>
    set((s) => ({
      interactivePrompts: [
        ...s.interactivePrompts.filter((item) => item.processId !== prompt.processId),
        prompt,
      ],
    })),
  removeInteractivePrompt: (processId) =>
    set((s) => ({
      interactivePrompts: s.interactivePrompts.filter((item) => item.processId !== processId),
    })),
  clearRuntimeNotices: () => set({ activeProgress: null, interactivePrompts: [] }),
  startStreamRun: (runId) => set({ activeRunId: runId, latestRunId: runId, isStreaming: true }),
  finishStreamRun: (runId) =>
    set((s) => (s.activeRunId === runId ? {
      activeRunId: null,
      isStreaming: false,
    } : {})),
  setIsStreaming: (v) => set({ isStreaming: v }),
  setStreamingError: (error) => set({ streamingError: error }),
}));
