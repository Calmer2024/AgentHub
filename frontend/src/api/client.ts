import type {
  Session, Message, Provider, AgentConfig, AgentConfigCreate, AgentConfigUpdate,
  Settings, SettingsUpdate, RouteAgent, CollabTask, ChainStep, ChainConfigInput,
  DAGPhase, PhaseChangeEvent, AgentStartEvent, OrchestratorSummaryStartEvent,
  Artifact, ArtifactDiff, ArtifactEditRequest, ArtifactEditResult, ArtifactVersion,
  OrchestratorDebugRequest, OrchestratorDebugResult,
} from "../types";
import { parseDagPhases, parseTasks } from "./orchestratorEvents";

const API_BASE = "/api";

export async function fetchProviders(): Promise<Provider[]> {
  const res = await fetch(`${API_BASE}/providers`);
  if (!res.ok) throw new Error("Failed to fetch providers");
  return res.json();
}

export async function fetchAgents(): Promise<AgentConfig[]> {
  const res = await fetch(`${API_BASE}/agents`);
  if (!res.ok) throw new Error("Failed to fetch agents");
  return res.json();
}

export async function createAgent(data: AgentConfigCreate): Promise<AgentConfig> {
  const res = await fetch(`${API_BASE}/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create agent");
  return res.json();
}

export async function updateAgent(id: string, data: AgentConfigUpdate): Promise<AgentConfig> {
  const res = await fetch(`${API_BASE}/agents/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update agent");
  return res.json();
}

export async function deleteAgent(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/agents/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete agent");
}

export async function fetchSessions(): Promise<Session[]> {
  const res = await fetch(`${API_BASE}/sessions`);
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function createGroupSession(title: string, agentConfigIds: string[]): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title || "群聊", mode: "group", agentConfigIds }),
  });
  if (!res.ok) throw new Error("Failed to create group session");
  return res.json();
}

export async function createSession(title?: string, agentConfigId?: string): Promise<Session> {
  const body: Record<string, string> = { title: title || "新对话" };
  if (agentConfigId) body.agentConfigId = agentConfigId;
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/sessions/${sessionId}`, { method: "DELETE" });
}

export async function renameSession(sessionId: string, title: string): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  return res.json();
}

export async function fetchSessionMembers(sessionId: string): Promise<Array<{ agentConfigId: string; agentName: string }>> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/members`);
  if (!res.ok) return [];
  return res.json();
}

export async function summarizeSession(sessionId: string): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/summarize`, { method: "POST" });
  return res.json();
}

export async function updateSessionAgent(sessionId: string, agentConfigId: string): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agentConfigId }),
  });
  if (!res.ok) throw new Error("Failed to update session");
  return res.json();
}

export async function fetchMessages(sessionId: string): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onDone: (messageId?: string, error?: string) => void;
  onRoute?: (agents: RouteAgent[]) => void;
  onTaskStarted?: (
    tasks: CollabTask[], intent: string, dagPhases: DAGPhase[], planSummary: string,
  ) => void;
  onChainStep?: (step: ChainStep) => void;
  onPhaseChange?: (event: PhaseChangeEvent) => void;
  onTaskCompleted?: (summary: string) => void;
  onAgentStart?: (event: AgentStartEvent) => void;
  onOrchestratorSummaryStart?: (event: OrchestratorSummaryStartEvent) => void;
  onOrchestratorSummaryToken?: (messageId: string, token: string) => void;
  onAgentToken?: (
    agentId: string,
    agentName: string,
    token: string,
    messageId?: string,
    role?: string,
    phase?: number,
    task?: string,
  ) => void;
}

export function createChatStream(
  sessionId: string,
  content: string,
  mentions: string[],
  callbacks: StreamCallbacks,
  chainConfig?: ChainConfigInput,
  parentMessageId?: string | null,
): () => void {
  const {
    onToken, onDone, onRoute, onTaskStarted, onChainStep, onPhaseChange,
    onTaskCompleted, onAgentStart, onOrchestratorSummaryStart,
    onOrchestratorSummaryToken, onAgentToken,
  } = callbacks;
  const url = `${API_BASE}/sessions/${sessionId}/chat`;
  const abortCtrl = new AbortController();

  (async () => {
    const body: Record<string, unknown> = { content };
    if (mentions.length > 0) body.mentions = mentions;
    if (parentMessageId) body.parentMessageId = parentMessageId;
    if (chainConfig) {
      body.chainConfig = {
        chainName: chainConfig.chainName,
        agentOrder: chainConfig.agentOrder,
      };
    }
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: abortCtrl.signal,
    });

    if (!response.ok) { onDone(undefined, `HTTP ${response.status}`); return; }

    const reader = response.body?.getReader();
    if (!reader) return;

    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let completed = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));

            // orchestrator.route
            if (data.type === "orchestrator.route" && onRoute) {
              onRoute(data.agents);
              continue;
            }

            // orchestrator.task_started (new)
            if (data.type === "orchestrator.task_started" && onTaskStarted) {
              onTaskStarted(
                parseTasks(data.tasks),
                data.intent || "general_qa",
                parseDagPhases(data.dag),
                typeof data.plan_summary === "string" ? data.plan_summary : "",
              );
              continue;
            }

            // orchestrator.chain_step (new)
            if (data.type === "orchestrator.chain_step" && onChainStep) {
              onChainStep({
                step: data.step ?? 0,
                agent: data.agent ?? "",
                role: data.role ?? "executor",
                total: data.total ?? 0,
                status: data.status ?? "running",
              });
              continue;
            }

            // orchestrator.phase_change
            if (data.type === "orchestrator.phase_change" && onPhaseChange) {
              const status = typeof data.status === "string" ? data.status : "running";
              onPhaseChange({
                phase: data.phase ?? 0,
                status: status === "pending" || status === "completed" || status === "error" ? status : "running",
                agents: Array.isArray(data.agents) ? data.agents.map(String) : [],
                tasks: Array.isArray(data.tasks) ? data.tasks.map(String) : [],
              });
              continue;
            }

            if (data.type === "orchestrator.summary_started") {
              if (onOrchestratorSummaryStart) {
                onOrchestratorSummaryStart({
                  messageId: data.messageId ?? "",
                  sourceType: "orchestrator",
                  sourceId: data.sourceId,
                  sourceName: data.sourceName ?? "Orchestrator 中枢",
                  contentType: "orchestrator_summary",
                  metadata: data.metadata,
                });
              }
              continue;
            }

            if (data.type === "orchestrator.summary_delta") {
              if (onOrchestratorSummaryToken && data.token) {
                onOrchestratorSummaryToken(data.messageId ?? "", data.token);
              }
              continue;
            }

            if (data.type === "orchestrator.summary_completed") {
              continue;
            }

            // orchestrator.task_completed (new)
            if (data.type === "orchestrator.task_completed" && onTaskCompleted) {
              onTaskCompleted(data.summary ?? "");
              completed = true;
              onDone(undefined, undefined);
              return;
            }

            // agent.start
            if (data.type === "agent.start") {
              if (onAgentStart) {
                onAgentStart({
                  agentId: data.agentId ?? "",
                  agentName: data.agentName ?? "",
                  messageId: data.messageId ?? "",
                  role: data.role,
                  phase: data.phase,
                  task: data.task,
                  callKey: data.callKey,
                });
              }
              continue;
            }

            // error event (global error)
            if (data.type === "error") {
              completed = true;
              onDone(undefined, data.error || "未知错误");
              return;
            }

            // token streaming
            if (data.agentId && data.token && onAgentToken) {
              onAgentToken(
                data.agentId,
                data.agentName || "",
                data.token,
                data.messageId,
                data.role,
                data.phase,
                data.task,
              );
            } else if (data.token) {
              onToken(data.token);
            }
            // 仅全局 done (无 agentId) 或全局 error 才终止流
            // 每个 Agent 的 done 事件 (有 agentId) 不终止，后续 Agent 还需流式输出
            if (data.done && !data.agentId) {
              completed = true;
              onDone(data.messageId, data.error);
              return;
            }
          } catch { /* parse error */ }
        }
      }
    }
    if (!completed) onDone(undefined, "Stream ended unexpectedly");
  })();

  return () => abortCtrl.abort();
}

export async function replyToMessage(messageId: string, content: string): Promise<Message> {
  const res = await fetch(`${API_BASE}/messages/${messageId}/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Failed to reply to message");
  return res.json();
}

export async function pinMessage(messageId: string): Promise<{ isPinned: boolean }> {
  const res = await fetch(`${API_BASE}/messages/${messageId}/pin`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to pin message");
  return res.json();
}

export async function unpinMessage(messageId: string): Promise<{ isPinned: boolean }> {
  const res = await fetch(`${API_BASE}/messages/${messageId}/pin`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to unpin message");
  return res.json();
}

export async function searchMessages(
  sessionId: string,
  query: string,
  limit = 20,
): Promise<Message[]> {
  const params = new URLSearchParams({ session_id: sessionId, q: query, limit: String(limit) });
  const res = await fetch(`${API_BASE}/messages/search?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to search messages");
  return res.json();
}

export async function fetchMessage(messageId: string): Promise<Message> {
  const res = await fetch(`${API_BASE}/messages/${messageId}`);
  if (!res.ok) throw new Error("Failed to fetch message");
  return res.json();
}

export function regenerateMessageStream(
  messageId: string,
  callbacks: Pick<StreamCallbacks, "onToken" | "onDone">,
): () => void {
  const abortCtrl = new AbortController();

  (async () => {
    const response = await fetch(`${API_BASE}/messages/${messageId}/regenerate`, {
      method: "POST",
      signal: abortCtrl.signal,
    });
    if (!response.ok) {
      callbacks.onDone(undefined, `HTTP ${response.status}`);
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) return;

    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.token) callbacks.onToken(data.token);
          if (data.done) {
            callbacks.onDone(data.messageId, data.error);
            return;
          }
        } catch { /* ignore malformed chunks */ }
      }
    }
    callbacks.onDone(undefined, "Stream ended unexpectedly");
  })();

  return () => abortCtrl.abort();
}

export async function fetchSettings(): Promise<Settings> {
  const res = await fetch(`${API_BASE}/settings`);
  if (!res.ok) throw new Error("Failed to fetch settings");
  return res.json();
}

export async function updateSettings(data: SettingsUpdate): Promise<Settings> {
  const res = await fetch(`${API_BASE}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update settings");
  return res.json();
}

export async function fetchArtifacts(sessionId: string): Promise<Artifact[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/artifacts`);
  if (!res.ok) throw new Error("Failed to fetch artifacts");
  return res.json();
}

export async function fetchArtifactVersions(artifactId: string): Promise<ArtifactVersion[]> {
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/versions`);
  if (!res.ok) throw new Error("Failed to fetch artifact versions");
  return res.json();
}

export async function fetchArtifactDiff(
  artifactId: string,
  fromVersion: number,
  toVersion: number,
): Promise<ArtifactDiff> {
  const params = new URLSearchParams({
    v1: String(fromVersion),
    v2: String(toVersion),
  });
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/diff?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to fetch artifact diff");
  return res.json();
}

export async function editArtifact(
  artifactId: string,
  data: ArtifactEditRequest,
): Promise<ArtifactEditResult> {
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to edit artifact");
  return res.json();
}

export async function dryRunOrchestrator(
  data: OrchestratorDebugRequest,
): Promise<OrchestratorDebugResult> {
  const res = await fetch(`${API_BASE}/debug/orchestrator/dry-run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}
