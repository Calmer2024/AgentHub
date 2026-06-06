import { create } from "zustand";
import type {
  Message, RouteAgent, CollabTask, ChainStep, DAGPhase, Artifact, CodeReference,
  InteractivePrompt, ExecutionTraceItem, RunRead, TaskRead, ApprovalCheckpoint,
  SystemHealthRead,
} from "../types";

const TERMINAL_RUN_STATUSES = new Set<RunRead["status"]>(["completed", "failed", "cancelled"]);
const TERMINAL_TASK_STATUSES = new Set<TaskRead["status"]>(["completed", "failed", "cancelled", "rejected"]);

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
  activeStreamKey: string | null;
  activeRunId: string | null;
  activeStreamAbort: (() => void) | null;
  latestRunId: string | null;
  streamingError: string | null;
  replyTarget: Message | null;
  codeReference: CodeReference | null;
  activeProgress: string | null;
  interactivePrompts: InteractivePrompt[];
  runs: RunRead[];
  tasksByRun: Record<string, TaskRead[]>;
  approvals: ApprovalCheckpoint[];
  systemHealth: SystemHealthRead | null;
  healthBlockingError: string | null;

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
  setRunsForSession: (sessionId: string, runs: RunRead[]) => void;
  upsertRun: (run: RunRead) => void;
  setTasksForRun: (runId: string, tasks: TaskRead[]) => void;
  upsertTask: (task: TaskRead) => void;
  setApprovalsForSession: (sessionId: string, approvals: ApprovalCheckpoint[]) => void;
  upsertApproval: (approval: ApprovalCheckpoint) => void;
  clearRuntimeState: () => void;
  setSystemHealth: (health: SystemHealthRead | null) => void;
  setHealthBlockingError: (error: string | null) => void;
  appendMessage: (msg: Message) => void;
  appendStreamingToken: (token: string) => void;
  appendStreamingTokenToMessage: (messageId: string, token: string) => void;
  appendAgentStreamingToken: (localId: string, agentName: string, token: string) => void;
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
  setCodeReference: (reference: CodeReference | null) => void;
  setActiveProgress: (progress: string | null) => void;
  addInteractivePrompt: (prompt: InteractivePrompt) => void;
  removeInteractivePrompt: (processId: string) => void;
  clearRuntimeNotices: () => void;
  startStreamRun: (runId: string) => void;
  finishStreamRun: (runId: string) => void;
  setActiveRunId: (runId: string | null) => void;
  setActiveStreamAbort: (abort: (() => void) | null) => void;
  cancelActiveStream: () => void;
  cancelRunLocally: (runId: string, reason?: string | null) => void;
  setIsStreaming: (v: boolean) => void;
  setStreamingError: (error: string | null) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  currentSessionId: null,
  messages: [],
  artifacts: [],
  isStreaming: false,
  activeStreamKey: null,
  activeRunId: null,
  activeStreamAbort: null,
  latestRunId: null,
  streamingError: null,
  replyTarget: null,
  codeReference: null,
  activeProgress: null,
  interactivePrompts: [],
  runs: [],
  tasksByRun: {},
  approvals: [],
  systemHealth: null,
  healthBlockingError: null,
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
    set((s) => (s.currentSessionId === sessionId ? { messages } : {})),
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
  setRunsForSession: (sessionId, runs) =>
    set((s) => (s.currentSessionId === sessionId ? { runs } : {})),
  upsertRun: (run) =>
    set((s) => {
      if (s.currentSessionId !== run.sessionId) return {};
      const existing = s.runs.filter((item) => item.id !== run.id);
      return { runs: [run, ...existing] };
    }),
  setTasksForRun: (runId, tasks) =>
    set((s) => ({
      tasksByRun: { ...s.tasksByRun, [runId]: tasks },
    })),
  upsertTask: (task) =>
    set((s) => {
      if (s.currentSessionId !== task.sessionId) return {};
      const current = s.tasksByRun[task.runId] ?? [];
      const next = [task, ...current.filter((item) => item.id !== task.id)]
        .sort((left, right) => (left.phase ?? 0) - (right.phase ?? 0));
      return { tasksByRun: { ...s.tasksByRun, [task.runId]: next } };
    }),
  setApprovalsForSession: (sessionId, approvals) =>
    set((s) => (s.currentSessionId === sessionId ? { approvals } : {})),
  upsertApproval: (approval) =>
    set((s) => {
      if (s.currentSessionId !== approval.sessionId) return {};
      const next = [approval, ...s.approvals.filter((item) => item.id !== approval.id)]
        .sort((left, right) => left.createdAt.localeCompare(right.createdAt));
      return { approvals: next };
    }),
  clearRuntimeState: () => set({ runs: [], tasksByRun: {}, approvals: [] }),
  setSystemHealth: (health) => set({ systemHealth: health }),
  setHealthBlockingError: (error) => set({ healthBlockingError: error }),
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
  setCodeReference: (reference) => set({ codeReference: reference }),
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
  startStreamRun: (runId) => set({
    activeStreamKey: runId,
    activeRunId: runId,
    latestRunId: runId,
    isStreaming: true,
  }),
  finishStreamRun: (runId) =>
    set((s) => (s.activeStreamKey === runId ? {
      activeStreamKey: null,
      activeRunId: null,
      activeStreamAbort: null,
      isStreaming: false,
    } : {})),
  setActiveRunId: (runId) => set({ activeRunId: runId }),
  setActiveStreamAbort: (abort) => set({ activeStreamAbort: abort }),
  cancelActiveStream: () => {
    const abort = get().activeStreamAbort;
    if (abort) abort();
    set({
      activeStreamKey: null,
      activeRunId: null,
      activeStreamAbort: null,
      isStreaming: false,
      activeProgress: null,
      interactivePrompts: [],
    });
  },
  cancelRunLocally: (runId, reason = null) => {
    const abort = get().activeStreamAbort;
    if (abort) abort();
    const now = new Date().toISOString();
    set((s) => {
      const run = s.runs.find((item) => item.id === runId);
      const sessionId = run?.sessionId ?? s.currentSessionId;
      const currentMessageId = run?.currentMessageId ?? null;
      const cancelTraceItem: ExecutionTraceItem = {
        id: `local-cancel-trace-${runId}-${Date.now()}`,
        kind: "info",
        text: "用户已中止本次运行",
        action: "complete",
        level: "warning",
        source: "system",
        chunkType: "cancelled",
        timestamp: now,
      };
      const messages = s.messages.map((message) => {
        const metadataRunId = typeof message.metadata?.runId === "string"
          ? message.metadata.runId
          : null;
        if (metadataRunId !== runId && message.id !== currentMessageId) return message;
        const metadata = {
          ...(message.metadata ?? {}),
          runId,
          runStatus: "cancelled",
          cancelReason: reason,
        } as NonNullable<Message["metadata"]>;
        const trace = metadata.executionTrace;
        if (trace?.status === "running") {
          metadata.executionTrace = {
            ...trace,
            status: "cancelled",
            completedAt: now,
            items: [...trace.items, cancelTraceItem].slice(-300),
          };
        }
        return { ...message, metadata };
      });
      const hasCancelNotice = messages.some((message) => (
        message.sourceName === "运行控制"
        && message.metadata?.runId === runId
        && message.metadata?.runStatus === "cancelled"
      ));
      if (sessionId && s.currentSessionId === sessionId && !hasCancelNotice) {
        messages.push({
          id: `local-cancel-${runId}-${Date.now()}`,
          sessionId,
          role: "system",
          content: "本次运行已中止成功，可以继续发送新消息。",
          contentType: "text",
          agentName: null,
          sourceType: "system",
          sourceName: "运行控制",
          metadata: { runId, runStatus: "cancelled", cancelReason: reason },
          createdAt: now,
        });
      }
      const runs = s.runs.map((item) => (
        item.id === runId && !TERMINAL_RUN_STATUSES.has(item.status)
          ? {
            ...item,
            status: "cancelled" as const,
            updatedAt: now,
            completedAt: item.completedAt ?? now,
            cancelReason: reason,
          }
          : item
      ));
      const currentTasks = s.tasksByRun[runId] ?? [];
      const tasksByRun = currentTasks.length > 0
        ? {
          ...s.tasksByRun,
          [runId]: currentTasks.map((task) => (
            TERMINAL_TASK_STATUSES.has(task.status)
              ? task
              : { ...task, status: "cancelled" as const, completedAt: task.completedAt ?? now }
          )),
        }
        : s.tasksByRun;
      return {
        messages,
        runs,
        tasksByRun,
        activeStreamKey: null,
        activeRunId: null,
        activeStreamAbort: null,
        isStreaming: false,
        activeProgress: null,
        interactivePrompts: [],
      };
    });
  },
  setIsStreaming: (v) => set({ isStreaming: v }),
  setStreamingError: (error) => set({ streamingError: error }),
}));
