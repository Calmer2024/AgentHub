import { useCallback } from "react";
import { useChatStore, type CollabSnapshot } from "../stores/chatStore";
import { useSessionStore } from "../stores/sessionStore";
import {
  checkSystemHealth,
  createChatStream,
  fetchArtifacts,
  fetchMessages,
  fetchRuns,
  fetchSession,
  markSessionRead,
} from "../api/client";
import type {
  Message, AgentStartEvent, Artifact, RouteDecisionEvent,
  OrchestratorExecution, Session,
} from "../types";
import { chinaNowIso } from "../utils/time";

function emptyCollab(): CollabSnapshot {
  return {
    routeAgents: null,
    routeType: null,
    routeReason: null,
  };
}

const taskKey = (agentId?: string, phase?: number, task?: string) =>
  `${agentId ?? ""}:${phase ?? 0}:${task ?? "primary"}`;


function publishSessionUpdated(session: Session) {
  useSessionStore.getState().updateSession(session);
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("agenthub:session-updated", {
      detail: { session },
    }));
  }
}

function stewardSummary(decision: RouteDecisionEvent): string {
  if (decision.routeType === "context_only") return "项目Leader已记录到群聊上下文";
  if (decision.routeType === "direct_turn") {
    const first = decision.selectedAgents[0];
    return first ? `已切换到和 @${first.name} 直接对话` : "已切换到直接对话";
  }
  const names = decision.selectedAgents.map((agent) => `@${agent.name}`).join("、");
  return `项目Leader将生成协作计划${names ? `：${names}` : ""}`;
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

  return useCallback(async (content: string, mentions: string[], attachmentIds: string[] = []) => {
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

    const createTaskPlaceholder = (task: { name: string; role: string; agent: string; agentId?: string; status: string; phase?: number }): string => {
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
        fetchSession(currentSessionId)
          .then(publishSessionUpdated)
          .catch(() => {});
        markSessionRead(currentSessionId).catch(() => {});
      },
      onRouteDecided: (decision) => {
        if (!isLiveStream()) return;
        const summary = stewardSummary(decision);
        setActiveProgress(summary, currentSessionId);
        saveCollab(collabKey, {
          ...emptyCollab(),
          routeAgents: decision.selectedAgents.length > 0 ? decision.selectedAgents : null,
          routeType: decision.routeType,
          routeReason: `${summary}。${decision.reason}`,
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
      onSessionTitleUpdated: (session) => {
        publishSessionUpdated(session);
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

      onPlanExecutionCreated: (execution: OrchestratorExecution, messageId) => {
        if (!isLiveStream() || !messageId) return;
        const targetId = localMessageForServer(messageId);
        const currentMessages = useChatStore.getState().messagesBySession[currentSessionId] ?? [];
        const currentMessage = currentMessages.find((message) => message.id === targetId);
        updateSessionMessage(currentSessionId, targetId, {
          metadata: {
            ...(currentMessage?.metadata ?? {}),
            orchestratorExecution: execution,
          },
        });
        setActiveRunId(execution.runId ?? null, currentSessionId);
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
      onAgentToken: (agentId, agentName, token, messageId, _role, phase, task) => {
        if (!isLiveStream()) return;
        const key = taskKey(agentId, phase, task);
        const localId = (messageId ? messagePlaceholders.get(messageId) : undefined)
          ?? agentPlaceholders.get(key)
          ?? agentPlaceholders.get(agentId);
        if (localId) appendAgentStreamingTokenToSession(currentSessionId, localId, agentName, token);
      },
    }, parentMessageId, attachmentIds);
    setActiveStreamAbort(streamKey, abortStream);

  }, [
    currentSessionId, sessions, appendMessageToSession,
    appendAgentStreamingTokenToSession, bindSessionMessageId, appendExecutionTraceItemToSession, upsertArtifact,
    finalizeExecutionTraceInSession, setArtifactsForSession, setMessagesForSession, setStreamingError,
    setActiveProgress, addInteractivePrompt, updateSessionMessage, clearRuntimeNotices,
    replaceSessionMessageWithServer,
    setRunsForSession, upsertRun, upsertTask,
    setSystemHealth, setHealthBlockingError,
    appendStreamingTokenToSessionMessage, startStreamRun, finishStreamRun,
    setActiveRunId, setActiveStreamAbort, getCollab, saveCollab, replyTarget, setReplyTarget,
  ]);
}
