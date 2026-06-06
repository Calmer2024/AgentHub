import { create } from "zustand";
import type {
  Message, RouteAgent, CollabTask, ChainStep, DAGPhase, Artifact, CodeReference,
  InteractivePrompt, ExecutionTraceItem, RunRead, TaskRead, ApprovalCheckpoint,
  SystemHealthRead,
} from "../types";
import { chinaNowIso } from "../utils/time";

const ACTIVE_RUN_STATUSES = new Set<RunRead["status"]>(["queued", "running", "pausing", "paused", "cancelling"]);
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

interface SessionRuntimeState {
  isStreaming: boolean;
  activeStreamKey: string | null;
  activeRunId: string | null;
  activeStreamAbort: (() => void) | null;
  activeProgress: string | null;
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

function emptyRuntime(): SessionRuntimeState {
  return {
    isStreaming: false,
    activeStreamKey: null,
    activeRunId: null,
    activeStreamAbort: null,
    activeProgress: null,
  };
}

function withoutSession<T>(record: Record<string, T>, sessionId: string) {
  const next = { ...record };
  delete next[sessionId];
  return next;
}

function applyCurrentSession<T extends Partial<ChatState>>(
  state: ChatState,
  sessionId: string | null,
  patch: T,
): T | Record<string, never> {
  return state.currentSessionId === sessionId ? patch : {};
}

function replaceById<T extends { id: string }>(items: T[], item: T) {
  return [item, ...items.filter((existing) => existing.id !== item.id)];
}

function updateMessageInList(messages: Message[], id: string, updater: (message: Message) => Message) {
  return messages.map((message) => (message.id === id ? updater(message) : message));
}

function mergeHydratedMessages(
  sessionId: string,
  current: Message[],
  incoming: Message[],
  runtime: SessionRuntimeState,
  runs: RunRead[],
) {
  const hasActiveRuntime = runtime.isStreaming || runs.some((run) => ACTIVE_RUN_STATUSES.has(run.status));
  if (!hasActiveRuntime || current.length === 0) return incoming;

  const incomingIds = new Set(incoming.map((message) => message.id));
  const liveMessages = current.filter((message) => (
    !incomingIds.has(message.id)
    && message.sessionId === sessionId
    && shouldPreserveLiveMessage(message, runs)
  ));
  if (liveMessages.length === 0) return incoming;
  return [...incoming, ...liveMessages];
}

function shouldPreserveLiveMessage(message: Message, runs: RunRead[]) {
  if (message.role !== "assistant") return false;
  if (message.id.startsWith("local-")) return true;
  if (message.metadata?.executionTrace?.status === "running") return true;
  const metadataRunId = typeof message.metadata?.runId === "string" ? message.metadata.runId : null;
  return runs.some((run) => (
    ACTIVE_RUN_STATUSES.has(run.status)
    && (run.currentMessageId === message.id || (metadataRunId && run.id === metadataRunId))
  ));
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

  messagesBySession: Record<string, Message[]>;
  artifactsBySession: Record<string, Artifact[]>;
  runsBySession: Record<string, RunRead[]>;
  approvalsBySession: Record<string, ApprovalCheckpoint[]>;
  runtimeBySession: Record<string, SessionRuntimeState>;
  streamingErrorBySession: Record<string, string | null>;
  activeStreamsByKey: Record<string, { sessionId: string; abort: (() => void) | null }>;

  // === 协作状态 (per-session persisted) ===
  collabSnapshots: Record<string, CollabSnapshot>;
  getCollab: (sessionId: string) => CollabSnapshot;
  saveCollab: (sessionId: string, snap: CollabSnapshot) => void;
  clearCollab: (sessionId: string) => void;

  // === 原有 actions ===
  setCurrentSessionId: (id: string | null) => void;
  resetSessionView: (sessionId?: string | null) => void;
  clearSessionCache: (sessionId: string) => void;
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
  clearRuntimeState: (sessionId?: string) => void;
  setSystemHealth: (health: SystemHealthRead | null) => void;
  setHealthBlockingError: (error: string | null) => void;
  appendMessage: (msg: Message) => void;
  appendMessageToSession: (sessionId: string, msg: Message) => void;
  appendStreamingToken: (token: string) => void;
  appendStreamingTokenToMessage: (messageId: string, token: string) => void;
  appendStreamingTokenToSessionMessage: (sessionId: string, messageId: string, token: string) => void;
  appendAgentStreamingToken: (localId: string, agentName: string, token: string) => void;
  appendAgentStreamingTokenToSession: (sessionId: string, localId: string, agentName: string, token: string) => void;
  bindMessageId: (localId: string, serverId: string) => void;
  bindSessionMessageId: (sessionId: string, localId: string, serverId: string) => void;
  appendExecutionTraceItem: (
    messageId: string,
    item: ExecutionTraceItem,
    seed?: { agentName?: string; cliTool?: string; processId?: string },
  ) => void;
  appendExecutionTraceItemToSession: (
    sessionId: string,
    messageId: string,
    item: ExecutionTraceItem,
    seed?: { agentName?: string; cliTool?: string; processId?: string },
  ) => void;
  finalizeExecutionTrace: (messageId: string, status: "completed" | "error", exitCode?: number | null) => void;
  finalizeExecutionTraceInSession: (
    sessionId: string,
    messageId: string,
    status: "completed" | "error" | "cancelled",
    exitCode?: number | null,
  ) => void;
  updateMessage: (id: string, patch: Partial<Message>) => void;
  updateSessionMessage: (sessionId: string, id: string, patch: Partial<Message>) => void;
  replaceMessageContent: (id: string, content: string) => void;
  replaceSessionMessageContent: (sessionId: string, id: string, content: string) => void;
  setReplyTarget: (message: Message | null) => void;
  setCodeReference: (reference: CodeReference | null) => void;
  setActiveProgress: (progress: string | null, sessionId?: string) => void;
  addInteractivePrompt: (prompt: InteractivePrompt) => void;
  removeInteractivePrompt: (processId: string) => void;
  clearRuntimeNotices: (sessionId?: string) => void;
  startStreamRun: (sessionId: string, streamKey: string, abort?: (() => void) | null) => void;
  finishStreamRun: (streamKey: string, sessionId?: string) => void;
  setActiveRunId: (runId: string | null, sessionId?: string) => void;
  setActiveStreamAbort: (streamKeyOrAbort: string | (() => void) | null, abort?: (() => void) | null) => void;
  isSessionStreaming: (sessionId: string | null) => boolean;
  getSessionRuntime: (sessionId: string | null) => SessionRuntimeState;
  cancelActiveStream: (sessionId?: string) => void;
  cancelRunLocally: (runId: string, reason?: string | null) => void;
  setIsStreaming: (v: boolean, sessionId?: string) => void;
  setStreamingError: (error: string | null, sessionId?: string | null) => void;
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
  messagesBySession: {},
  artifactsBySession: {},
  runsBySession: {},
  approvalsBySession: {},
  runtimeBySession: {},
  streamingErrorBySession: {},
  activeStreamsByKey: {},
  collabSnapshots: {},

  getCollab: (sessionId) => get().collabSnapshots[sessionId] ?? emptyCollab(),
  saveCollab: (sessionId, snap) =>
    set((s) => ({ collabSnapshots: { ...s.collabSnapshots, [sessionId]: snap } })),
  clearCollab: (sessionId) =>
    set((s) => ({ collabSnapshots: withoutSession(s.collabSnapshots, sessionId) })),

  setCurrentSessionId: (id) =>
    set((s) => {
      const runtime = id ? s.runtimeBySession[id] ?? emptyRuntime() : emptyRuntime();
      return {
        currentSessionId: id,
        messages: id ? s.messagesBySession[id] ?? [] : [],
        artifacts: id ? s.artifactsBySession[id] ?? [] : [],
        runs: id ? s.runsBySession[id] ?? [] : [],
        approvals: id ? s.approvalsBySession[id] ?? [] : [],
        isStreaming: runtime.isStreaming,
        activeStreamKey: runtime.activeStreamKey,
        activeRunId: runtime.activeRunId,
        activeStreamAbort: runtime.activeStreamAbort,
        activeProgress: runtime.activeProgress,
        streamingError: id ? s.streamingErrorBySession[id] ?? null : null,
      };
    }),

  resetSessionView: (sessionId) =>
    set((s) => {
      const target = sessionId ?? s.currentSessionId;
      const runtime = target ? s.runtimeBySession[target] ?? emptyRuntime() : emptyRuntime();
      return {
        messages: target ? s.messagesBySession[target] ?? [] : [],
        artifacts: target ? s.artifactsBySession[target] ?? [] : [],
        runs: target ? s.runsBySession[target] ?? [] : [],
        approvals: target ? s.approvalsBySession[target] ?? [] : [],
        isStreaming: runtime.isStreaming,
        activeStreamKey: runtime.activeStreamKey,
        activeRunId: runtime.activeRunId,
        activeStreamAbort: runtime.activeStreamAbort,
        activeProgress: runtime.activeProgress,
      };
    }),

  clearSessionCache: (sessionId) =>
    set((s) => ({
      messagesBySession: withoutSession(s.messagesBySession, sessionId),
      artifactsBySession: withoutSession(s.artifactsBySession, sessionId),
      runsBySession: withoutSession(s.runsBySession, sessionId),
      approvalsBySession: withoutSession(s.approvalsBySession, sessionId),
      runtimeBySession: withoutSession(s.runtimeBySession, sessionId),
      streamingErrorBySession: withoutSession(s.streamingErrorBySession, sessionId),
      messages: s.currentSessionId === sessionId ? [] : s.messages,
      artifacts: s.currentSessionId === sessionId ? [] : s.artifacts,
      runs: s.currentSessionId === sessionId ? [] : s.runs,
      approvals: s.currentSessionId === sessionId ? [] : s.approvals,
      streamingError: s.currentSessionId === sessionId ? null : s.streamingError,
      ...(s.currentSessionId === sessionId ? emptyRuntime() : {}),
    })),

  setMessages: (messages) =>
    set((s) => ({
      messages,
      messagesBySession: s.currentSessionId
        ? { ...s.messagesBySession, [s.currentSessionId]: messages }
        : s.messagesBySession,
    })),
  setMessagesForSession: (sessionId, messages) =>
    set((s) => {
      const current = s.messagesBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.messages : []);
      const runtime = s.runtimeBySession[sessionId] ?? emptyRuntime();
      const runs = s.runsBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.runs : []);
      const merged = mergeHydratedMessages(sessionId, current, messages, runtime, runs);
      return {
        messagesBySession: { ...s.messagesBySession, [sessionId]: merged },
        ...applyCurrentSession(s, sessionId, { messages: merged }),
      };
    }),
  setArtifacts: (artifacts) =>
    set((s) => ({
      artifacts,
      artifactsBySession: s.currentSessionId
        ? { ...s.artifactsBySession, [s.currentSessionId]: artifacts }
        : s.artifactsBySession,
    })),
  setArtifactsForSession: (sessionId, artifacts) =>
    set((s) => ({
      artifactsBySession: { ...s.artifactsBySession, [sessionId]: artifacts },
      ...applyCurrentSession(s, sessionId, { artifacts }),
    })),
  upsertArtifact: (artifact) =>
    set((s) => {
      const sessionId = artifact.sessionId || s.currentSessionId;
      if (!sessionId) return {};
      const current = s.artifactsBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.artifacts : []);
      const withoutChain = current.filter((a) => (
        a.id !== artifact.id
        && a.parentArtifactId !== artifact.id
        && artifact.parentArtifactId !== a.id
      ));
      const artifacts = [artifact, ...withoutChain];
      return {
        artifactsBySession: { ...s.artifactsBySession, [sessionId]: artifacts },
        ...applyCurrentSession(s, sessionId, { artifacts }),
      };
    }),
  setRunsForSession: (sessionId, runs) =>
    set((s) => ({
      runsBySession: { ...s.runsBySession, [sessionId]: runs },
      ...applyCurrentSession(s, sessionId, { runs }),
    })),
  upsertRun: (run) =>
    set((s) => {
      const current = s.runsBySession[run.sessionId] ?? (s.currentSessionId === run.sessionId ? s.runs : []);
      const runs = replaceById(current, run);
      const runtime = s.runtimeBySession[run.sessionId] ?? emptyRuntime();
      const terminalForActiveRun = TERMINAL_RUN_STATUSES.has(run.status)
        && (
          runtime.activeRunId === run.id
          || (!runtime.activeRunId && Boolean(runtime.activeStreamKey))
        );
      const nextRuntime = terminalForActiveRun
        ? { ...runtime, isStreaming: false, activeRunId: null, activeStreamKey: null, activeStreamAbort: null, activeProgress: null }
        : runtime;
      const activeStreamsByKey = terminalForActiveRun && runtime.activeStreamKey
        ? withoutSession(s.activeStreamsByKey, runtime.activeStreamKey)
        : s.activeStreamsByKey;
      return {
        runsBySession: { ...s.runsBySession, [run.sessionId]: runs },
        runtimeBySession: { ...s.runtimeBySession, [run.sessionId]: nextRuntime },
        activeStreamsByKey,
        ...applyCurrentSession(s, run.sessionId, {
          runs,
          isStreaming: nextRuntime.isStreaming,
          activeRunId: nextRuntime.activeRunId,
          activeStreamKey: nextRuntime.activeStreamKey,
          activeStreamAbort: nextRuntime.activeStreamAbort,
          activeProgress: nextRuntime.activeProgress,
        }),
      };
    }),
  setTasksForRun: (runId, tasks) =>
    set((s) => ({
      tasksByRun: { ...s.tasksByRun, [runId]: tasks },
    })),
  upsertTask: (task) =>
    set((s) => {
      const current = s.tasksByRun[task.runId] ?? [];
      const next = [task, ...current.filter((item) => item.id !== task.id)]
        .sort((left, right) => (left.phase ?? 0) - (right.phase ?? 0));
      return { tasksByRun: { ...s.tasksByRun, [task.runId]: next } };
    }),
  setApprovalsForSession: (sessionId, approvals) =>
    set((s) => ({
      approvalsBySession: { ...s.approvalsBySession, [sessionId]: approvals },
      ...applyCurrentSession(s, sessionId, { approvals }),
    })),
  upsertApproval: (approval) =>
    set((s) => {
      const current = s.approvalsBySession[approval.sessionId] ?? (s.currentSessionId === approval.sessionId ? s.approvals : []);
      const approvals = [approval, ...current.filter((item) => item.id !== approval.id)]
        .sort((left, right) => left.createdAt.localeCompare(right.createdAt));
      return {
        approvalsBySession: { ...s.approvalsBySession, [approval.sessionId]: approvals },
        ...applyCurrentSession(s, approval.sessionId, { approvals }),
      };
    }),
  clearRuntimeState: (sessionId) =>
    set((s) => {
      const target = sessionId ?? s.currentSessionId;
      if (!target) return { runs: [], tasksByRun: {}, approvals: [] };
      return {
        runsBySession: { ...s.runsBySession, [target]: [] },
        approvalsBySession: { ...s.approvalsBySession, [target]: [] },
        runtimeBySession: { ...s.runtimeBySession, [target]: emptyRuntime() },
        ...applyCurrentSession(s, target, {
          runs: [],
          approvals: [],
          ...emptyRuntime(),
        }),
      };
    }),
  setSystemHealth: (health) => set({ systemHealth: health }),
  setHealthBlockingError: (error) => set({ healthBlockingError: error }),

  appendMessage: (msg) => get().appendMessageToSession(msg.sessionId, msg),
  appendMessageToSession: (sessionId, msg) =>
    set((s) => {
      const current = s.messagesBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.messages : []);
      const messages = [...current, msg];
      return {
        messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
        ...applyCurrentSession(s, sessionId, { messages }),
      };
    }),
  appendStreamingToken: (token) =>
    set((s) => {
      const sessionId = s.currentSessionId;
      if (!sessionId) return {};
      const msgs = s.messagesBySession[sessionId] ?? s.messages;
      const lastMsg = msgs[msgs.length - 1];
      const runtime = s.runtimeBySession[sessionId] ?? emptyRuntime();
      if (lastMsg && lastMsg.role === "assistant" && runtime.isStreaming) {
        const messages = [...msgs.slice(0, -1), { ...lastMsg, content: lastMsg.content + token }];
        return {
          messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
          messages,
        };
      }
      return {};
    }),
  appendStreamingTokenToMessage: (messageId, token) => {
    const sessionId = get().currentSessionId;
    if (!sessionId) return;
    get().appendStreamingTokenToSessionMessage(sessionId, messageId, token);
  },
  appendStreamingTokenToSessionMessage: (sessionId, messageId, token) =>
    set((s) => {
      const current = s.messagesBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.messages : []);
      const messages = updateMessageInList(current, messageId, (m) => ({ ...m, content: m.content + token }));
      return {
        messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
        ...applyCurrentSession(s, sessionId, { messages }),
      };
    }),
  appendAgentStreamingToken: (localId, agentName, token) => {
    const sessionId = get().currentSessionId;
    if (!sessionId) return;
    get().appendAgentStreamingTokenToSession(sessionId, localId, agentName, token);
  },
  appendAgentStreamingTokenToSession: (sessionId, localId, agentName, token) =>
    set((s) => {
      const current = s.messagesBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.messages : []);
      const messages = updateMessageInList(current, localId, (m) => ({
        ...m,
        content: m.content + token,
        agentName,
      }));
      return {
        messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
        ...applyCurrentSession(s, sessionId, { messages }),
      };
    }),
  bindMessageId: (localId, serverId) => {
    const sessionId = get().currentSessionId;
    if (!sessionId) return;
    get().bindSessionMessageId(sessionId, localId, serverId);
  },
  bindSessionMessageId: (sessionId, localId, serverId) =>
    set((s) => {
      const current = s.messagesBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.messages : []);
      const messages = updateMessageInList(current, localId, (m) => ({ ...m, id: serverId }));
      return {
        messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
        ...applyCurrentSession(s, sessionId, { messages }),
      };
    }),
  appendExecutionTraceItem: (messageId, item, seed) => {
    const sessionId = get().currentSessionId;
    if (!sessionId) return;
    get().appendExecutionTraceItemToSession(sessionId, messageId, item, seed);
  },
  appendExecutionTraceItemToSession: (sessionId, messageId, item, seed) =>
    set((s) => {
      const current = s.messagesBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.messages : []);
      const messages = current.map((m) => {
        if (m.id !== messageId) return m;
        const metadata = { ...(m.metadata ?? {}) };
        const currentTrace = metadata.executionTrace;
        metadata.executionTrace = {
          status: currentTrace?.status ?? "running",
          agentName: currentTrace?.agentName ?? seed?.agentName ?? m.agentName,
          cliTool: currentTrace?.cliTool ?? seed?.cliTool ?? null,
          workspacePath: currentTrace?.workspacePath ?? null,
          startedAt: currentTrace?.startedAt ?? item.timestamp,
          completedAt: currentTrace?.completedAt ?? null,
          processId: currentTrace?.processId ?? seed?.processId ?? item.processId ?? null,
          exitCode: currentTrace?.exitCode ?? null,
          items: [...(currentTrace?.items ?? []), item].slice(-300),
        };
        return { ...m, metadata };
      });
      return {
        messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
        ...applyCurrentSession(s, sessionId, { messages }),
      };
    }),
  finalizeExecutionTrace: (messageId, status, exitCode = null) => {
    const sessionId = get().currentSessionId;
    if (!sessionId) return;
    get().finalizeExecutionTraceInSession(sessionId, messageId, status, exitCode);
  },
  finalizeExecutionTraceInSession: (sessionId, messageId, status, exitCode = null) =>
    set((s) => {
      const current = s.messagesBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.messages : []);
      const messages = current.map((m) => {
        if (m.id !== messageId || !m.metadata?.executionTrace) return m;
        return {
          ...m,
          metadata: {
            ...m.metadata,
            executionTrace: {
              ...m.metadata.executionTrace,
              status,
              exitCode,
              completedAt: chinaNowIso(),
            },
          },
        };
      });
      return {
        messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
        ...applyCurrentSession(s, sessionId, { messages }),
      };
    }),
  updateMessage: (id, patch) => {
    const sessionId = get().currentSessionId;
    if (!sessionId) return;
    get().updateSessionMessage(sessionId, id, patch);
  },
  updateSessionMessage: (sessionId, id, patch) =>
    set((s) => {
      const current = s.messagesBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.messages : []);
      const messages = updateMessageInList(current, id, (m) => ({ ...m, ...patch }));
      return {
        messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
        ...applyCurrentSession(s, sessionId, { messages }),
      };
    }),
  replaceMessageContent: (id, content) => {
    const sessionId = get().currentSessionId;
    if (!sessionId) return;
    get().replaceSessionMessageContent(sessionId, id, content);
  },
  replaceSessionMessageContent: (sessionId, id, content) =>
    set((s) => {
      const current = s.messagesBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.messages : []);
      const messages = updateMessageInList(current, id, (m) => ({ ...m, content }));
      return {
        messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
        ...applyCurrentSession(s, sessionId, { messages }),
      };
    }),
  setReplyTarget: (message) => set({ replyTarget: message }),
  setCodeReference: (reference) => set({ codeReference: reference }),
  setActiveProgress: (progress, sessionId) =>
    set((s) => {
      const target = sessionId ?? s.currentSessionId;
      if (!target) return { activeProgress: progress };
      const runtime = { ...(s.runtimeBySession[target] ?? emptyRuntime()), activeProgress: progress };
      return {
        runtimeBySession: { ...s.runtimeBySession, [target]: runtime },
        ...applyCurrentSession(s, target, { activeProgress: progress }),
      };
    }),
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
  clearRuntimeNotices: (sessionId) =>
    set((s) => {
      const target = sessionId ?? s.currentSessionId;
      const prompts = target
        ? s.interactivePrompts.filter((prompt) => prompt.sessionId !== target)
        : [];
      if (!target) return { activeProgress: null, interactivePrompts: prompts };
      const runtime = { ...(s.runtimeBySession[target] ?? emptyRuntime()), activeProgress: null };
      return {
        interactivePrompts: prompts,
        runtimeBySession: { ...s.runtimeBySession, [target]: runtime },
        ...applyCurrentSession(s, target, { activeProgress: null }),
      };
    }),
  startStreamRun: (sessionId, streamKey, abort = null) =>
    set((s) => {
      const runtime = {
        ...(s.runtimeBySession[sessionId] ?? emptyRuntime()),
        activeStreamKey: streamKey,
        activeStreamAbort: abort,
        isStreaming: true,
      };
      return {
        runtimeBySession: { ...s.runtimeBySession, [sessionId]: runtime },
        activeStreamsByKey: {
          ...s.activeStreamsByKey,
          [streamKey]: { sessionId, abort },
        },
        latestRunId: streamKey,
        ...applyCurrentSession(s, sessionId, {
          activeStreamKey: streamKey,
          activeStreamAbort: abort,
          isStreaming: true,
        }),
      };
    }),
  finishStreamRun: (streamKey, sessionId) =>
    set((s) => {
      const target = sessionId ?? s.activeStreamsByKey[streamKey]?.sessionId;
      if (!target) return {};
      const current = s.runtimeBySession[target] ?? emptyRuntime();
      const nextStreams = withoutSession(s.activeStreamsByKey, streamKey);
      if (current.activeStreamKey !== streamKey) {
        return { activeStreamsByKey: nextStreams };
      }
      const runtime = {
        ...current,
        activeStreamKey: null,
        activeRunId: null,
        activeStreamAbort: null,
        isStreaming: false,
        activeProgress: null,
      };
      return {
        activeStreamsByKey: nextStreams,
        runtimeBySession: { ...s.runtimeBySession, [target]: runtime },
        ...applyCurrentSession(s, target, {
          activeStreamKey: null,
          activeRunId: null,
          activeStreamAbort: null,
          isStreaming: false,
          activeProgress: null,
        }),
      };
    }),
  setActiveRunId: (runId, sessionId) =>
    set((s) => {
      const target = sessionId ?? s.currentSessionId;
      if (!target) return { activeRunId: runId };
      const runtime = { ...(s.runtimeBySession[target] ?? emptyRuntime()), activeRunId: runId };
      return {
        runtimeBySession: { ...s.runtimeBySession, [target]: runtime },
        ...applyCurrentSession(s, target, { activeRunId: runId }),
      };
    }),
  setActiveStreamAbort: (streamKeyOrAbort, abort) =>
    set((s) => {
      if (typeof streamKeyOrAbort !== "string") {
        const target = s.currentSessionId;
        if (!target) return { activeStreamAbort: streamKeyOrAbort };
        const runtime = {
          ...(s.runtimeBySession[target] ?? emptyRuntime()),
          activeStreamAbort: streamKeyOrAbort,
        };
        const streamKey = runtime.activeStreamKey;
        return {
          runtimeBySession: { ...s.runtimeBySession, [target]: runtime },
          activeStreamsByKey: streamKey
            ? { ...s.activeStreamsByKey, [streamKey]: { sessionId: target, abort: streamKeyOrAbort } }
            : s.activeStreamsByKey,
          ...applyCurrentSession(s, target, { activeStreamAbort: streamKeyOrAbort }),
        };
      }
      const entry = s.activeStreamsByKey[streamKeyOrAbort];
      const target = entry?.sessionId ?? s.currentSessionId;
      if (!target) return {};
      const runtime = {
        ...(s.runtimeBySession[target] ?? emptyRuntime()),
        activeStreamAbort: abort ?? null,
      };
      return {
        runtimeBySession: { ...s.runtimeBySession, [target]: runtime },
        activeStreamsByKey: {
          ...s.activeStreamsByKey,
          [streamKeyOrAbort]: { sessionId: target, abort: abort ?? null },
        },
        ...applyCurrentSession(s, target, { activeStreamAbort: abort ?? null }),
      };
    }),
  isSessionStreaming: (sessionId) => {
    if (!sessionId) return false;
    return Boolean(get().runtimeBySession[sessionId]?.isStreaming);
  },
  getSessionRuntime: (sessionId) => {
    if (!sessionId) return emptyRuntime();
    return get().runtimeBySession[sessionId] ?? emptyRuntime();
  },
  cancelActiveStream: (sessionId) => {
    const state = get();
    const target = sessionId ?? state.currentSessionId;
    if (!target) return;
    const runtime = state.runtimeBySession[target] ?? emptyRuntime();
    if (runtime.activeStreamAbort) runtime.activeStreamAbort();
    set((s) => {
      const nextStreams = runtime.activeStreamKey
        ? withoutSession(s.activeStreamsByKey, runtime.activeStreamKey)
        : s.activeStreamsByKey;
      const nextRuntime = emptyRuntime();
      return {
        activeStreamsByKey: nextStreams,
        runtimeBySession: { ...s.runtimeBySession, [target]: nextRuntime },
        interactivePrompts: s.interactivePrompts.filter((prompt) => prompt.sessionId !== target),
        ...applyCurrentSession(s, target, nextRuntime),
      };
    });
  },
  cancelRunLocally: (runId, reason = null) => {
    const state = get();
    const run = Object.values(state.runsBySession).flat().find((item) => item.id === runId)
      ?? state.runs.find((item) => item.id === runId);
    const sessionId = run?.sessionId ?? state.currentSessionId;
    if (!sessionId) return;
    const runtime = state.runtimeBySession[sessionId] ?? emptyRuntime();
    if (runtime.activeStreamAbort) runtime.activeStreamAbort();
    const now = chinaNowIso();
    set((s) => {
      const sessionMessages = s.messagesBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.messages : []);
      const sessionRuns = s.runsBySession[sessionId] ?? (s.currentSessionId === sessionId ? s.runs : []);
      const activeRun = sessionRuns.find((item) => item.id === runId) ?? run;
      const currentMessageId = activeRun?.currentMessageId ?? null;
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
      const messages = sessionMessages.map((message) => {
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
      if (!hasCancelNotice) {
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
      const runs = sessionRuns.map((item) => (
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
      const nextStreams = runtime.activeStreamKey
        ? withoutSession(s.activeStreamsByKey, runtime.activeStreamKey)
        : s.activeStreamsByKey;
      const nextRuntime = emptyRuntime();
      return {
        messagesBySession: { ...s.messagesBySession, [sessionId]: messages },
        runsBySession: { ...s.runsBySession, [sessionId]: runs },
        tasksByRun,
        activeStreamsByKey: nextStreams,
        runtimeBySession: { ...s.runtimeBySession, [sessionId]: nextRuntime },
        interactivePrompts: s.interactivePrompts.filter((prompt) => prompt.sessionId !== sessionId),
        ...applyCurrentSession(s, sessionId, {
          messages,
          runs,
          ...nextRuntime,
        }),
      };
    });
  },
  setIsStreaming: (v, sessionId) =>
    set((s) => {
      const target = sessionId ?? s.currentSessionId;
      if (!target) return { isStreaming: v };
      const runtime = { ...(s.runtimeBySession[target] ?? emptyRuntime()), isStreaming: v };
      return {
        runtimeBySession: { ...s.runtimeBySession, [target]: runtime },
        ...applyCurrentSession(s, target, { isStreaming: v }),
      };
    }),
  setStreamingError: (error, sessionId) =>
    set((s) => {
      const target = sessionId ?? s.currentSessionId;
      if (!target) return { streamingError: error };
      return {
        streamingErrorBySession: { ...s.streamingErrorBySession, [target]: error },
        ...applyCurrentSession(s, target, { streamingError: error }),
      };
    }),
}));
