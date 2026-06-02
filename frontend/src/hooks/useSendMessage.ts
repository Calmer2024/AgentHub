import { useCallback } from "react";
import { useChatStore, type CollabSnapshot } from "../stores/chatStore";
import { useSessionStore } from "../stores/sessionStore";
import { createChatStream, fetchMessages } from "../api/client";
import type { Message, CollabTask, DAGPhase, PhaseChangeEvent, AgentStartEvent } from "../types";

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
    appendMessage,
    appendStreamingToken,
    appendAgentStreamingToken,
    setMessages,
    setIsStreaming,
    setStreamingError,
    getCollab,
    saveCollab,
  } = useChatStore();
  const { sessions } = useSessionStore();

  return useCallback(async (content: string, mentions: string[]) => {
    if (!currentSessionId) return;
    const collabKey = currentSessionId;
    setStreamingError(null);
    saveCollab(collabKey, emptyCollab());

    const currentMode = sessions.find((s) => s.id === currentSessionId)?.mode ?? "single";
    const userMsg: Message = {
      id: `local-${Date.now()}`, sessionId: currentSessionId,
      role: "user", content, agentName: null, createdAt: new Date().toISOString(),
    };
    appendMessage(userMsg);

    if (currentMode !== "group") {
      appendMessage({
        id: `local-ai-${Date.now()}`, sessionId: currentSessionId,
        role: "assistant", content: "", agentName: null,
        createdAt: new Date().toISOString(),
      });
    }

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

    createChatStream(currentSessionId, content, mentions, {
      onToken: (token) => appendStreamingToken(token),
      onDone: (messageId, error) => {
        setIsStreaming(false);
        if (error) {
          setStreamingError(error === "Stream ended unexpectedly"
            ? "连接中断，请检查网络后重试" : `请求失败：${error}`);
          return;
        }
        if (messageId) fetchMessages(currentSessionId).then(setMessages);
      },
      onRoute: (agents) => {
        saveCollab(collabKey, { ...emptyCollab(), routeAgents: agents });
        setIsStreaming(true);
      },
      onTaskStarted: (tasks, intent, nextPhases, planSummary) => {
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
        appendAgentStreamingToken(messageId, "Orchestrator 中枢", token);
      },
      onAgentToken: (agentId, agentName, token, messageId, _role, phase, task) => {
        const key = taskKey(agentId, phase, task);
        const localId = (messageId ? messagePlaceholders.get(messageId) : undefined)
          ?? agentPlaceholders.get(key)
          ?? agentPlaceholders.get(agentId);
        if (localId) appendAgentStreamingToken(localId, agentName, token);
      },
    });

    if (currentMode !== "group") setIsStreaming(true);
  }, [
    currentSessionId, sessions, appendMessage, appendStreamingToken,
    appendAgentStreamingToken, setMessages, setIsStreaming, setStreamingError,
    getCollab, saveCollab,
  ]);
}
