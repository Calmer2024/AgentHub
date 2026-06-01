import type { Session, Message, Provider, AgentConfig, AgentConfigCreate, AgentConfigUpdate, Settings, SettingsUpdate, RouteAgent, CollabTask, ChainStep, ChainConfigInput } from "../types";

const API_BASE = "/api";

// Providers
export async function fetchProviders(): Promise<Provider[]> {
  const res = await fetch(`${API_BASE}/providers`);
  if (!res.ok) throw new Error("Failed to fetch providers");
  return res.json();
}

// Agent CRUD
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

// Sessions
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

// Messages
export async function fetchMessages(sessionId: string): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onDone: (messageId?: string, error?: string) => void;
  onRoute?: (agents: RouteAgent[]) => void;
  onTaskStarted?: (tasks: CollabTask[], intent: string) => void;
  onChainStep?: (step: ChainStep) => void;
  onTaskCompleted?: (summary: string) => void;
  onAgentToken?: (agentId: string, agentName: string, token: string) => void;
}

export function createChatStream(
  sessionId: string,
  content: string,
  mentions: string[],
  callbacks: StreamCallbacks,
  chainConfig?: ChainConfigInput,
): () => void {
  const { onToken, onDone, onRoute, onTaskStarted, onChainStep, onTaskCompleted, onAgentToken } = callbacks;
  const url = `${API_BASE}/sessions/${sessionId}/chat`;
  const abortCtrl = new AbortController();

  (async () => {
    const body: Record<string, unknown> = { content };
    if (mentions.length > 0) body.mentions = mentions;
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
              onTaskStarted(data.tasks || [], data.intent || "general_qa");
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

            // orchestrator.task_completed (new)
            if (data.type === "orchestrator.task_completed" && onTaskCompleted) {
              onTaskCompleted(data.summary ?? "");
              continue;
            }

            // agent.start (skip in stream)
            if (data.type === "agent.start") continue;

            // error event (global error)
            if (data.type === "error") {
              completed = true;
              onDone(undefined, data.error || "未知错误");
              return;
            }

            // token streaming
            if (data.agentId && data.token && onAgentToken) {
              onAgentToken(data.agentId, data.agentName || "", data.token);
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

// Settings
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
