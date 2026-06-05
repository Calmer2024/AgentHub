import { useCallback } from "react";
import { useChatStore, type CollabSnapshot } from "../stores/chatStore";
import { useSessionStore } from "../stores/sessionStore";
import { createChatStream, fetchArtifacts, fetchMessages, summarizeSession } from "../api/client";
import type { Message, CollabTask, DAGPhase, PhaseChangeEvent, AgentStartEvent, Artifact } from "../types";

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

const taskKey = (agentId?: string, phase?: number, task?: string) =>
  `${agentId ?? ""}:${phase ?? 0}:${task ?? "primary"}`;

const updatePhases = (phases: DAGPhase[], event: PhaseChangeEvent): DAGPhase[] =>
  phases.map((phase) => {
    if (phase.phase !== event.phase) return phase;
    return {
      ...phase,
      status: event.status,
      tasks: phase.tasks.map((task) => ({ ...task, status: event.status })),
    };
  });

const findPhaseTasks = (phases: DAGPhase[], event: PhaseChangeEvent): CollabTask[] => {
  const phase = phases.find((p) => p.phase === event.phase);
  if (phase) return phase.tasks;
  return event.tasks.map((name) => ({
    name,
    role: "executor",
    agent: event.agents.join(", "),
    status: event.status,
    phase: event.phase,
  }));
};

export function useSendMessage() {
  const {
    currentSessionId,
    replyTarget,
    appendMessage,
    appendStreamingToken,
    appendStreamingTokenToMessage,
    appendAgentStreamingToken,
    bindMessageId,
    appendExecutionTraceItem,
    finalizeExecutionTrace,
    setMessagesForSession,
    setArtifactsForSession,
    upsertArtifact,
    setStreamingError,
    setActiveProgress,
    addInteractivePrompt,
    updateMessage,
    clearRuntimeNotices,
    startStreamRun,
    finishStreamRun,
    getCollab,
    saveCollab,
    setReplyTarget,
  } = useChatStore();
  const { agents, sessions, updateSession } = useSessionStore();

  return useCallback(async (content: string, mentions: string[]) => {
    if (!currentSessionId) return;
    const collabKey = currentSessionId;
    const runId = `run-${currentSessionId}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const isCurrentRun = () => useChatStore.getState().activeRunId === runId
      && useChatStore.getState().currentSessionId === currentSessionId;
    setStreamingError(null);
    clearRuntimeNotices();
    saveCollab(collabKey, emptyCollab());

    const currentSession = sessions.find((s) => s.id === currentSessionId);
    const currentMode = currentSession?.mode ?? "single";
    const shouldSummarizeTitle = shouldAutoSummarizeTitle(
      currentSession?.title ?? "",
      currentMode,
      currentSession?.agentConfigId ?? null,
      agents,
    );
    const userMsg: Message = {
      id: `local-${Date.now()}`, sessionId: currentSessionId,
      role: "user", content, agentName: null, createdAt: new Date().toISOString(),
      parentMessageId: replyTarget?.id ?? null,
    };
    appendMessage(userMsg);

    const singleAssistantLocalId = currentMode !== "group"
      ? `local-ai-${Date.now()}`
      : null;
    let singleAssistantBoundId = singleAssistantLocalId;
    const ensureSingleAssistantId = (serverId?: string) => {
      if (currentMode === "group" || !singleAssistantLocalId) return serverId ?? "";
      if (serverId && singleAssistantBoundId !== serverId) {
        bindMessageId(singleAssistantBoundId ?? singleAssistantLocalId, serverId);
        singleAssistantBoundId = serverId;
      }
      return singleAssistantBoundId ?? singleAssistantLocalId;
    };

    if (singleAssistantLocalId) {
      appendMessage({
        id: singleAssistantLocalId, sessionId: currentSessionId,
        role: "assistant", content: "", agentName: null,
        createdAt: new Date().toISOString(),
      });
    }
    startStreamRun(runId);

    const agentPlaceholders = new Map<string, string>();
    const messagePlaceholders = new Map<string, string>();

    const createTaskPlaceholder = (task: CollabTask): string => {
      const key = taskKey(task.agentId, task.phase, task.name);
      const existing = agentPlaceholders.get(key);
      if (existing) return existing;
      const localId = `local-agent-${task.agentId ?? task.agent}-${task.phase ?? 0}-${task.name}-${Date.now()}`;
      agentPlaceholders.set(key, localId);
      if (task.agentId) agentPlaceholders.set(task.agentId, localId);
      appendMessage({
        id: localId,
        sessionId: currentSessionId,
        role: "assistant",
        content: "",
        agentName: task.agent,
        agentRole: task.role,
        phase: task.phase ?? null,
        taskName: task.name,
        isCollaborating: true,
        createdAt: new Date().toISOString(),
      });
      return localId;
    };

    const parentMessageId = replyTarget?.id ?? null;
    setReplyTarget(null);

    const localMessageForServer = (serverMessageId: string) => {
      if (currentMode === "group") {
        return messagePlaceholders.get(serverMessageId) ?? serverMessageId;
      }
      return ensureSingleAssistantId(serverMessageId);
    };

    const patchArtifactBridge = (serverMessageId: string, bridge: Record<string, unknown>) => {
      const targetId = localMessageForServer(serverMessageId);
      updateMessage(targetId, {
        metadata: {
          ...(useChatStore.getState().messages.find((msg) => msg.id === targetId)?.metadata ?? {}),
          artifactBridge: bridge,
        },
      });
    };

    createChatStream(currentSessionId, content, mentions, {
      onToken: (token) => {
        if (!isCurrentRun()) return;
        if (currentMode === "group") {
          appendStreamingToken(token);
          return;
        }
        const targetId = ensureSingleAssistantId();
        if (targetId) appendStreamingTokenToMessage(targetId, token);
      },
      onDone: (messageId, error) => {
        if (!isCurrentRun()) return;
        finishStreamRun(runId);
        setActiveProgress(null);
        if (error) {
          setStreamingError(error === "Stream ended unexpectedly"
            ? "连接中断，请检查网络后重试" : `请求失败：${error}`);
          return;
        }
        if (messageId) ensureSingleAssistantId(messageId);
        fetchMessages(currentSessionId).then((messages) => {
          if (useChatStore.getState().latestRunId !== runId) return;
          setMessagesForSession(currentSessionId, messages);
        });
        fetchArtifacts(currentSessionId)
          .then((artifacts) => {
            if (useChatStore.getState().latestRunId !== runId) return;
            setArtifactsForSession(currentSessionId, artifacts);
          })
          .catch(() => {});
        if (shouldSummarizeTitle) {
          summarizeSession(currentSessionId)
            .then(updateSession)
            .catch(() => {});
        }
      },
      onRoute: (agents) => {
        if (!isCurrentRun()) return;
        saveCollab(collabKey, { ...emptyCollab(), routeAgents: agents });
      },
      onProgress: (progress) => {
        if (!isCurrentRun()) return;
        setActiveProgress(progress);
      },
      onInteractivePrompt: (prompt) => {
        if (!isCurrentRun()) return;
        addInteractivePrompt(prompt);
      },
      onTraceDelta: (messageId, item, meta) => {
        if (!isCurrentRun()) return;
        if (currentMode === "group") {
          const localId = messagePlaceholders.get(messageId);
          if (localId) appendExecutionTraceItem(localId, item, meta);
          return;
        }
        const targetId = ensureSingleAssistantId(messageId);
        if (targetId) appendExecutionTraceItem(targetId, item, meta);
      },
      onTraceCompleted: (messageId, status, exitCode) => {
        if (!isCurrentRun()) return;
        if (currentMode === "group") {
          const localId = messagePlaceholders.get(messageId);
          if (localId) finalizeExecutionTrace(localId, status, exitCode);
          return;
        }
        const targetId = ensureSingleAssistantId(messageId);
        if (targetId) finalizeExecutionTrace(targetId, status, exitCode);
      },
      onArtifactScanStarted: (messageId) => {
        if (!isCurrentRun()) return;
        patchArtifactBridge(messageId, { status: "scanning" });
      },
      onArtifactCreated: (artifact: Artifact) => {
        if (!isCurrentRun()) return;
        const messageId = localMessageForServer(artifact.messageId);
        upsertArtifact(currentMode === "group" ? { ...artifact, messageId } : artifact);
      },
      onArtifactScanCompleted: (messageId, summary) => {
        if (!isCurrentRun()) return;
        patchArtifactBridge(messageId, {
          status: "completed",
          ...summary,
          completedAt: new Date().toISOString(),
        });
      },
      onArtifactDetectionFailed: (messageId, reason) => {
        if (!isCurrentRun()) return;
        patchArtifactBridge(messageId, {
          status: "failed",
          reason: reason ?? "artifact detection failed",
          completedAt: new Date().toISOString(),
        });
      },
      onTaskStarted: (tasks, intent, nextPhases, planSummary) => {
        if (!isCurrentRun()) return;
        const snap = getCollab(collabKey);
        saveCollab(collabKey, {
          ...(snap ?? emptyCollab()),
          collabTasks: tasks,
          dagPhases: nextPhases,
          orchestratorIntent: intent,
          planSummary,
        });
        if (nextPhases.length === 0) tasks.forEach(createTaskPlaceholder);
      },
      onChainStep: (step) => {
        if (!isCurrentRun()) return;
        const snap = getCollab(collabKey);
        const existing = (snap?.chainSteps ?? []).filter((s) => s.step !== step.step);
        const updatedSteps = [...existing, step].sort((a, b) => a.step - b.step);
        const updatedTasks = (snap?.collabTasks ?? []).map((t, i) => (
          i === step.step ? {
            ...t,
            status: step.status === "interrupted" ? "error" as const
              : step.status === "completed" ? "completed" as const : "running" as const,
          } : t
        ));
        saveCollab(collabKey, {
          ...(snap ?? emptyCollab()),
          chainSteps: updatedSteps,
          collabTasks: updatedTasks,
        });
      },
      onPhaseChange: (event) => {
        if (!isCurrentRun()) return;
        const base = getCollab(collabKey) ?? emptyCollab();
        const phaseTasks = findPhaseTasks(base.dagPhases, event);
        saveCollab(collabKey, {
          ...base,
          collabTasks: base.collabTasks.map((task) => (
            task.phase === event.phase ? { ...task, status: event.status } : task
          )),
          dagPhases: updatePhases(base.dagPhases, event),
        });
        if (event.status === "running") phaseTasks.forEach(createTaskPlaceholder);
      },
      onTaskCompleted: (summary) => {
        if (!isCurrentRun()) return;
        const snap = getCollab(collabKey);
        saveCollab(collabKey, {
          ...(snap ?? emptyCollab()),
          collabCompleted: true,
          collabSummary: summary,
          collabTasks: (snap?.collabTasks ?? []).map((t) => (
            t.status === "error" ? t : { ...t, status: "completed" as const }
          )),
          dagPhases: (snap?.dagPhases ?? []).map((p) => (
            p.status === "error" ? p : {
              ...p,
              status: "completed" as const,
              tasks: p.tasks.map((t) => (
                t.status === "error" ? t : { ...t, status: "completed" as const }
              )),
            }
          )),
        });
      },
      onAgentStart: (event: AgentStartEvent) => {
        if (!isCurrentRun()) return;
        const key = event.callKey ?? taskKey(event.agentId, event.phase, event.task);
        let localId = agentPlaceholders.get(key);
        if (!localId) {
          localId = createTaskPlaceholder({
            name: event.task ?? "primary",
            role: event.role ?? "executor",
            agent: event.agentName,
            agentId: event.agentId,
            status: "running",
            phase: event.phase,
          });
        }
        agentPlaceholders.set(key, localId);
        messagePlaceholders.set(event.messageId, localId);
      },
      onOrchestratorSummaryStart: (event) => {
        if (!isCurrentRun()) return;
        appendMessage({
          id: event.messageId,
          sessionId: currentSessionId,
          role: "assistant",
          content: "",
          contentType: event.contentType,
          agentName: null,
          sourceType: event.sourceType,
          sourceId: event.sourceId ?? "orchestrator",
          sourceName: event.sourceName,
          metadata: event.metadata ?? null,
          isCollaborating: true,
          createdAt: new Date().toISOString(),
        });
      },
      onOrchestratorSummaryToken: (messageId, token) => {
        if (!isCurrentRun()) return;
        appendAgentStreamingToken(messageId, "Orchestrator 中枢", token);
      },
      onAgentToken: (agentId, agentName, token, messageId, _role, phase, task) => {
        if (!isCurrentRun()) return;
        const key = taskKey(agentId, phase, task);
        const localId = (messageId ? messagePlaceholders.get(messageId) : undefined)
          ?? agentPlaceholders.get(key)
          ?? agentPlaceholders.get(agentId);
        if (localId) appendAgentStreamingToken(localId, agentName, token);
      },
    }, undefined, parentMessageId);

  }, [
    currentSessionId, agents, sessions, updateSession, appendMessage, appendStreamingToken,
    appendAgentStreamingToken, bindMessageId, appendExecutionTraceItem, upsertArtifact,
    finalizeExecutionTrace, setArtifactsForSession, setMessagesForSession, setStreamingError,
    setActiveProgress, addInteractivePrompt, updateMessage, clearRuntimeNotices,
    appendStreamingTokenToMessage, startStreamRun, finishStreamRun,
    getCollab, saveCollab, replyTarget, setReplyTarget,
  ]);
}

function shouldAutoSummarizeTitle(
  title: string,
  mode: string,
  agentConfigId: string | null,
  agents: Array<{ id: string; name: string }>,
): boolean {
  const clean = title.trim();
  if (!clean) return true;
  if (clean === "新对话" || clean === "群聊") return true;
  if (mode === "group" && /^群聊\s*\d*$/.test(clean)) return true;
  const agentName = agents.find((agent) => agent.id === agentConfigId)?.name;
  return Boolean(agentName && clean === agentName);
}
