import { useCallback } from "react";
import { useChatStore, type CollabSnapshot } from "../stores/chatStore";
import { useSessionStore } from "../stores/sessionStore";
import {
  checkSystemHealth,
  createChatStream,
  fetchApprovals,
  fetchArtifacts,
  fetchMessages,
  fetchRuns,
  markSessionRead,
} from "../api/client";
import type {
  Message, CollabTask, DAGPhase, PhaseChangeEvent, AgentStartEvent, Artifact, StewardDecisionEvent,
} from "../types";
import { chinaNowIso } from "../utils/time";

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

function stewardSummary(decision: StewardDecisionEvent): string {
  if (decision.routeType === "context_only") return "Orchestrator 调度器已记录到群聊上下文";
  if (decision.routeType === "draft_plan") return "Orchestrator 调度器建议先生成计划，等待确认后再执行";
  if (decision.routeType === "mini_collab") {
    const names = decision.selectedAgents.map((agent) => `@${agent.name}`).join("、");
    return `Orchestrator 调度器建议先生成小型协作计划${names ? `：${names}` : ""}`;
  }
  const first = decision.selectedAgents[0];
  return first ? `Orchestrator 调度器已分派给 @${first.name}` : "Orchestrator 调度器已完成分流";
}

export function useSendMessage() {
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const replyTarget = useChatStore((state) => state.replyTarget);
  const appendMessageToSession = useChatStore((state) => state.appendMessageToSession);
  const appendStreamingTokenToSessionMessage = useChatStore((state) => state.appendStreamingTokenToSessionMessage);
  const appendAgentStreamingTokenToSession = useChatStore((state) => state.appendAgentStreamingTokenToSession);
  const bindSessionMessageId = useChatStore((state) => state.bindSessionMessageId);
  const appendExecutionTraceItemToSession = useChatStore((state) => state.appendExecutionTraceItemToSession);
  const finalizeExecutionTraceInSession = useChatStore((state) => state.finalizeExecutionTraceInSession);
  const setMessagesForSession = useChatStore((state) => state.setMessagesForSession);
  const setArtifactsForSession = useChatStore((state) => state.setArtifactsForSession);
  const upsertArtifact = useChatStore((state) => state.upsertArtifact);
  const setRunsForSession = useChatStore((state) => state.setRunsForSession);
  const upsertRun = useChatStore((state) => state.upsertRun);
  const upsertTask = useChatStore((state) => state.upsertTask);
  const setApprovalsForSession = useChatStore((state) => state.setApprovalsForSession);
  const upsertApproval = useChatStore((state) => state.upsertApproval);
  const setSystemHealth = useChatStore((state) => state.setSystemHealth);
  const setHealthBlockingError = useChatStore((state) => state.setHealthBlockingError);
  const setStreamingError = useChatStore((state) => state.setStreamingError);
  const setActiveProgress = useChatStore((state) => state.setActiveProgress);
  const addInteractivePrompt = useChatStore((state) => state.addInteractivePrompt);
  const updateSessionMessage = useChatStore((state) => state.updateSessionMessage);
  const replaceSessionMessageWithServer = useChatStore((state) => state.replaceSessionMessageWithServer);
  const clearRuntimeNotices = useChatStore((state) => state.clearRuntimeNotices);
  const startStreamRun = useChatStore((state) => state.startStreamRun);
  const finishStreamRun = useChatStore((state) => state.finishStreamRun);
  const setActiveRunId = useChatStore((state) => state.setActiveRunId);
  const setActiveStreamAbort = useChatStore((state) => state.setActiveStreamAbort);
  const getCollab = useChatStore((state) => state.getCollab);
  const saveCollab = useChatStore((state) => state.saveCollab);
  const setReplyTarget = useChatStore((state) => state.setReplyTarget);
  const sessions = useSessionStore((state) => state.sessions);

  return useCallback(async (content: string, mentions: string[]) => {
    if (!currentSessionId) return;
    const collabKey = currentSessionId;
    const streamKey = `stream-${currentSessionId}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const isLiveStream = () => Boolean(useChatStore.getState().activeStreamsByKey[streamKey]);
    setStreamingError(null, currentSessionId);
    clearRuntimeNotices(currentSessionId);
    saveCollab(collabKey, emptyCollab());

    const currentSession = sessions.find((s) => s.id === currentSessionId);
    const currentMode = currentSession?.mode ?? "single";
    try {
      const health = await checkSystemHealth({
        projectId: currentSession?.projectId ?? null,
        sessionId: currentSessionId,
        agentId: currentMode === "single" ? currentSession?.agentConfigId ?? null : null,
      });
      setSystemHealth(health);
      if (health.blockingReasons.length > 0) {
        const message = health.blockingReasons.join("；");
        setHealthBlockingError(message);
        setStreamingError(`环境体检阻断：${message}`, currentSessionId);
        return;
      }
      setHealthBlockingError(null);
    } catch {
      setHealthBlockingError(null);
    }
    const userMsg: Message = {
      id: `local-${Date.now()}`, sessionId: currentSessionId,
      role: "user", content, agentName: null, createdAt: chinaNowIso(),
      parentMessageId: replyTarget?.id ?? null,
    };
    appendMessageToSession(currentSessionId, userMsg);

    const singleAssistantLocalId = currentMode !== "group"
      ? `local-ai-${Date.now()}`
      : null;
    let singleAssistantBoundId = singleAssistantLocalId;
    const ensureSingleAssistantId = (serverId?: string) => {
      if (currentMode === "group" || !singleAssistantLocalId) return serverId ?? "";
      if (serverId && singleAssistantBoundId !== serverId) {
        bindSessionMessageId(currentSessionId, singleAssistantBoundId ?? singleAssistantLocalId, serverId);
        singleAssistantBoundId = serverId;
      }
      return singleAssistantBoundId ?? singleAssistantLocalId;
    };

    if (singleAssistantLocalId) {
      appendMessageToSession(currentSessionId, {
        id: singleAssistantLocalId, sessionId: currentSessionId,
        role: "assistant", content: "", agentName: null,
        createdAt: chinaNowIso(),
      });
    }
    startStreamRun(currentSessionId, streamKey);

    const agentPlaceholders = new Map<string, string>();
    const messagePlaceholders = new Map<string, string>();

    const createTaskPlaceholder = (task: CollabTask): string => {
      const key = taskKey(task.agentId, task.phase, task.name);
      const existing = agentPlaceholders.get(key);
      if (existing) return existing;
      const localId = `local-agent-${task.agentId ?? task.agent}-${task.phase ?? 0}-${task.name}-${Date.now()}`;
      agentPlaceholders.set(key, localId);
      if (task.agentId) agentPlaceholders.set(task.agentId, localId);
      appendMessageToSession(currentSessionId, {
        id: localId,
        sessionId: currentSessionId,
        role: "assistant",
        content: "",
        agentName: task.agent,
        agentRole: task.role,
        phase: task.phase ?? null,
        taskName: task.name,
        isCollaborating: true,
        createdAt: chinaNowIso(),
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
      updateSessionMessage(currentSessionId, targetId, {
        metadata: {
          ...((useChatStore.getState().messagesBySession[currentSessionId] ?? [])
            .find((msg) => msg.id === targetId)?.metadata ?? {}),
          artifactBridge: bridge,
        },
      });
    };

    const abortStream = createChatStream(currentSessionId, content, mentions, {
      onToken: (token) => {
        if (!isLiveStream()) return;
        if (currentMode === "group") {
          const targetId = ensureSingleAssistantId();
          if (targetId) appendStreamingTokenToSessionMessage(currentSessionId, targetId, token);
          return;
        }
        const targetId = ensureSingleAssistantId();
        if (targetId) appendStreamingTokenToSessionMessage(currentSessionId, targetId, token);
      },
      onDone: (messageId, error) => {
        const active = isLiveStream();
        finishStreamRun(streamKey, currentSessionId);
        setActiveProgress(null, currentSessionId);
        if (error) {
          if (active) {
            setStreamingError(error === "Stream ended unexpectedly"
              ? "连接中断，请检查网络后重试" : `请求失败：${error}`, currentSessionId);
          }
          return;
        }
        if (active && messageId) ensureSingleAssistantId(messageId);
        fetchMessages(currentSessionId).then((messages) => {
          if (currentMode === "group") {
            for (const serverMessage of messages) {
              const localId = messagePlaceholders.get(serverMessage.id);
              if (localId) {
                replaceSessionMessageWithServer(currentSessionId, localId, serverMessage);
              }
            }
          }
          setMessagesForSession(currentSessionId, messages);
        });
        fetchArtifacts(currentSessionId)
          .then((artifacts) => {
            setArtifactsForSession(currentSessionId, artifacts);
          })
          .catch(() => {});
        fetchRuns(currentSessionId)
          .then((runs) => setRunsForSession(currentSessionId, runs))
          .catch(() => {});
        fetchApprovals(currentSessionId)
          .then((approvals) => setApprovalsForSession(currentSessionId, approvals))
          .catch(() => {});
        markSessionRead(currentSessionId).catch(() => {});
      },
      onRoute: (agents) => {
        if (!isLiveStream()) return;
        const snap = getCollab(collabKey);
        saveCollab(collabKey, { ...(snap ?? emptyCollab()), routeAgents: agents });
      },
      onStewardDecision: (decision) => {
        if (!isLiveStream()) return;
        const summary = stewardSummary(decision);
        setActiveProgress(summary, currentSessionId);
        saveCollab(collabKey, {
          ...emptyCollab(),
          routeAgents: decision.selectedAgents.length > 0 ? decision.selectedAgents : null,
          orchestratorIntent: decision.intent,
          planSummary: `${summary}。${decision.reason}`,
        });
      },
      onProgress: (progress) => {
        if (!isLiveStream()) return;
        setActiveProgress(progress, currentSessionId);
      },
      onInteractivePrompt: (prompt) => {
        if (!isLiveStream()) return;
        addInteractivePrompt(prompt);
      },
      onRunStarted: (run) => {
        if (isLiveStream()) setActiveRunId(run.id, currentSessionId);
        upsertRun(run);
      },
      onRunStatusChanged: (run) => {
        upsertRun(run);
      },
      onTaskStatusChanged: (task) => {
        upsertTask(task);
      },
      onApprovalCreated: (approval) => {
        upsertApproval(approval);
      },
      onApprovalStatusChanged: (approval) => {
        upsertApproval(approval);
      },
      onTraceDelta: (messageId, item, meta) => {
        if (!isLiveStream()) return;
        if (currentMode === "group") {
          const localId = messagePlaceholders.get(messageId);
          if (localId) appendExecutionTraceItemToSession(currentSessionId, localId, item, meta);
          return;
        }
        const targetId = ensureSingleAssistantId(messageId);
        if (targetId) appendExecutionTraceItemToSession(currentSessionId, targetId, item, meta);
      },
      onTraceCompleted: (messageId, status, exitCode) => {
        if (!isLiveStream()) return;
        if (currentMode === "group") {
          const localId = messagePlaceholders.get(messageId);
          if (localId) finalizeExecutionTraceInSession(currentSessionId, localId, status, exitCode);
          return;
        }
        const targetId = ensureSingleAssistantId(messageId);
        if (targetId) finalizeExecutionTraceInSession(currentSessionId, targetId, status, exitCode);
      },
      onArtifactScanStarted: (messageId) => {
        if (!isLiveStream()) return;
        patchArtifactBridge(messageId, { status: "scanning" });
      },
      onArtifactCreated: (artifact: Artifact) => {
        if (!isLiveStream()) return;
        const messageId = localMessageForServer(artifact.messageId);
        upsertArtifact(currentMode === "group" ? { ...artifact, messageId } : artifact);
      },
      onArtifactScanCompleted: (messageId, summary) => {
        if (!isLiveStream()) return;
        patchArtifactBridge(messageId, {
          status: "completed",
          ...summary,
          completedAt: chinaNowIso(),
        });
      },
      onArtifactDetectionFailed: (messageId, reason) => {
        if (!isLiveStream()) return;
        patchArtifactBridge(messageId, {
          status: "failed",
          reason: reason ?? "artifact detection failed",
          completedAt: chinaNowIso(),
        });
      },
      onTaskStarted: (tasks, intent, nextPhases, planSummary) => {
        if (!isLiveStream()) return;
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
        if (!isLiveStream()) return;
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
        if (!isLiveStream()) return;
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
        if (!isLiveStream()) return;
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
        if (!isLiveStream()) return;
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
        if (!isLiveStream()) return;
        appendMessageToSession(currentSessionId, {
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
          createdAt: chinaNowIso(),
        });
      },
      onOrchestratorSummaryToken: (messageId, token) => {
        if (!isLiveStream()) return;
        appendAgentStreamingTokenToSession(currentSessionId, messageId, "Orchestrator 中枢", token);
      },
      onAgentToken: (agentId, agentName, token, messageId, _role, phase, task) => {
        if (!isLiveStream()) return;
        const key = taskKey(agentId, phase, task);
        const localId = (messageId ? messagePlaceholders.get(messageId) : undefined)
          ?? agentPlaceholders.get(key)
          ?? agentPlaceholders.get(agentId);
        if (localId) appendAgentStreamingTokenToSession(currentSessionId, localId, agentName, token);
      },
    }, undefined, parentMessageId);
    setActiveStreamAbort(streamKey, abortStream);

  }, [
    currentSessionId, sessions, appendMessageToSession,
    appendAgentStreamingTokenToSession, bindSessionMessageId, appendExecutionTraceItemToSession, upsertArtifact,
    finalizeExecutionTraceInSession, setArtifactsForSession, setMessagesForSession, setStreamingError,
    setActiveProgress, addInteractivePrompt, updateSessionMessage, clearRuntimeNotices,
    replaceSessionMessageWithServer,
    setRunsForSession, upsertRun, upsertTask, setApprovalsForSession, upsertApproval,
    setSystemHealth, setHealthBlockingError,
    appendStreamingTokenToSessionMessage, startStreamRun, finishStreamRun,
    setActiveRunId, setActiveStreamAbort, getCollab, saveCollab, replyTarget, setReplyTarget,
  ]);
}
