import type {
  Session, Message, AgentConfig, AgentConfigCreate, AgentConfigUpdate,
  RouteAgent, CollabTask, ChainStep, ChainConfigInput,
  DAGPhase, PhaseChangeEvent, AgentStartEvent, OrchestratorSummaryStartEvent,
  Artifact, ArtifactDiff, ArtifactEditRequest, ArtifactEditResult, ArtifactVersion,
  Project, ProjectCreateInput, ProjectUpdateInput, ProjectDeleteResult, FolderPickResult,
  PreviewResult,
  ExecutionTraceItem,
  CodexLocalConfig, CodexLocalConfigUpdate,
  SkillDefinition, DraftOrchestratorPlan,
} from "../types";
import { parseDagPhases, parseTasks } from "./orchestratorEvents";

const API_BASE = "/api";

export async function fetchAgents(): Promise<AgentConfig[]> {
  const res = await fetch(`${API_BASE}/agents`);
  if (!res.ok) throw new Error("Failed to fetch agents");
  return res.json();
}

export async function fetchSkills(): Promise<SkillDefinition[]> {
  const res = await fetch(`${API_BASE}/skills`);
  if (!res.ok) throw new Error("Failed to fetch skills");
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

export async function checkAgentExecutable(path: string): Promise<{
  found: boolean;
  status: string;
  version?: string | null;
  path?: string | null;
}> {
  const params = new URLSearchParams({ path });
  const res = await fetch(`${API_BASE}/agents/check-executable?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to check executable");
  return res.json();
}

export async function fetchCodexLocalConfig(): Promise<CodexLocalConfig> {
  const res = await fetch(`${API_BASE}/agents/codex-config`);
  if (!res.ok) throw new Error("Failed to fetch Codex config");
  return res.json();
}

export async function updateCodexLocalConfig(data: CodexLocalConfigUpdate): Promise<CodexLocalConfig> {
  const res = await fetch(`${API_BASE}/agents/codex-config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    let detail = "Failed to update Codex config";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch { /* keep fallback */ }
    throw new Error(detail);
  }
  return res.json();
}

export async function replyToInteractivePrompt(
  sessionId: string,
  processId: string,
  reply: "y" | "n",
): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/interactive_reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ processId, reply }),
  });
  if (!res.ok) throw new Error("Failed to reply to interactive prompt");
}

export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/projects`);
  if (!res.ok) throw new Error("Failed to fetch projects");
  return res.json();
}

export async function createProject(data: ProjectCreateInput): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create project");
  return res.json();
}

export async function pickProjectFolder(): Promise<FolderPickResult> {
  const res = await fetch(`${API_BASE}/projects/pick-folder`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to pick folder");
  return res.json();
}

export async function updateProject(
  projectId: string,
  data: ProjectUpdateInput,
): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update project");
  return res.json();
}

export async function archiveProject(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/archive`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to archive project");
}

export async function createProjectPreview(
  projectId: string,
  filePath?: string | null,
): Promise<PreviewResult> {
  const body: Record<string, string> = { type: "static" };
  if (filePath) body.filePath = filePath;
  const res = await fetch(`${API_BASE}/projects/${projectId}/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "Failed to create preview";
    try {
      const bodyJson = await res.json();
      if (typeof bodyJson.detail === "string") detail = bodyJson.detail;
    } catch { /* keep fallback */ }
    throw new Error(detail);
  }
  return res.json();
}

export async function deleteProject(
  projectId: string,
  deleteFiles = false,
): Promise<ProjectDeleteResult> {
  const params = new URLSearchParams({ deleteFiles: String(deleteFiles) });
  const res = await fetch(`${API_BASE}/projects/${projectId}?${params.toString()}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    let detail = "Failed to delete project";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch { /* keep fallback */ }
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchSessions(projectId?: string): Promise<Session[]> {
  const params = projectId ? `?projectId=${encodeURIComponent(projectId)}` : "";
  const res = await fetch(`${API_BASE}/sessions${params}`);
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function createGroupSession(
  title: string,
  agentConfigIds: string[],
  projectId?: string,
): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title || "群聊", mode: "group", agentConfigIds, projectId }),
  });
  if (!res.ok) throw new Error("Failed to create group session");
  return res.json();
}

export async function createSession(
  title?: string,
  agentConfigId?: string,
  projectId?: string,
): Promise<Session> {
  const body: Record<string, string> = { title: title || "新对话" };
  if (agentConfigId) body.agentConfigId = agentConfigId;
  if (projectId) body.projectId = projectId;
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
  onOrchestratorPlanCompleted?: (plan: DraftOrchestratorPlan) => void;
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
  onProgress?: (progress: string) => void;
  onInteractivePrompt?: (prompt: {
    sessionId: string;
    agentId: string;
    agentName: string;
    messageId: string;
    processId: string;
    content: string;
    promptType: "confirm";
  }) => void;
  onTraceDelta?: (
    messageId: string,
    item: ExecutionTraceItem,
    meta: { agentName?: string; cliTool?: string; processId?: string },
  ) => void;
  onTraceCompleted?: (messageId: string, status: "completed" | "error", exitCode?: number | null) => void;
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
    onOrchestratorSummaryToken, onAgentToken, onProgress, onInteractivePrompt,
    onTraceDelta, onTraceCompleted, onOrchestratorPlanCompleted,
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

            if (data.type === "orchestrator.plan_completed") {
              if (onOrchestratorPlanCompleted) {
                onOrchestratorPlanCompleted(parseDraftPlan(data));
              }
              completed = true;
              onDone(data.messageId, data.ok === false && data.error ? data.error : undefined);
              return;
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
              if (data.messageId && onTraceCompleted) {
                onTraceCompleted(data.messageId, "error", data.exitCode ?? null);
              }
              onDone(undefined, data.error || "未知错误");
              return;
            }

            if (data.type === "agent.trace.delta") {
              if (onTraceDelta && data.messageId && data.item) {
                onTraceDelta(data.messageId, data.item, {
                  agentName: data.agentName,
                  cliTool: data.cliTool,
                  processId: data.processId,
                });
              }
              continue;
            }

            if (data.type === "agent.output") {
              const token = typeof data.token === "string" && data.token
                ? data.token
                : data.chunkType === "text" && typeof data.chunk === "string"
                  ? data.chunk
                  : "";
              if (token && data.agentId && data.callKey && onAgentToken) {
                onAgentToken(
                  data.agentId,
                  data.agentName || "",
                  token,
                  data.messageId,
                  data.role,
                  data.phase,
                  data.task,
                );
              } else if (token) {
                onToken(token);
              }
              if (data.chunkType !== "progress") continue;
            }

            if (data.type === "agent.output" && data.chunkType === "progress") {
              const hasStructuredTrace = data.metadata?.trace && typeof data.metadata.trace === "object";
              if (onTraceDelta && data.messageId && data.callKey && data.chunk && !hasStructuredTrace) {
                const trace = data.metadata?.trace && typeof data.metadata.trace === "object"
                  ? data.metadata.trace
                  : {};
                onTraceDelta(data.messageId, {
                  id: `trace-${Date.now()}-${Math.random().toString(16).slice(2)}`,
                  kind: trace.kind ?? "progress",
                  text: trace.text ?? data.chunk,
                  title: trace.title,
                  detail: trace.detail,
                  summary: trace.summary,
                  action: trace.action,
                  target: trace.target,
                  command: trace.command,
                  toolName: trace.toolName,
                  provider: trace.provider,
                  level: trace.level,
                  raw: trace.raw,
                  source: "cli",
                  chunkType: data.chunkType,
                  processId: data.processId ?? null,
                  timestamp: trace.timestamp ?? new Date().toISOString(),
                }, {
                  agentName: data.agentName,
                  processId: data.processId,
                });
              }
              if (onProgress && data.chunk) onProgress(data.chunk);
              continue;
            }

            if (data.type === "agent.process.started") {
              if (onTraceDelta && data.messageId && data.callKey) {
                onTraceDelta(data.messageId, {
                  id: `trace-${Date.now()}-${Math.random().toString(16).slice(2)}`,
                  kind: "process",
                  text: `正在启动 ${data.agentName || "CLI Agent"}`,
                  source: "system",
                  chunkType: "process",
                  processId: data.processId ?? null,
                  timestamp: new Date().toISOString(),
                }, {
                  agentName: data.agentName,
                  processId: data.processId,
                });
              }
              if (onProgress) onProgress(`正在启动 ${data.agentName || "CLI Agent"}...`);
              continue;
            }

            if (data.type === "agent.process.completed") {
              if (onProgress) onProgress(`已完成 ${data.agentName || "CLI Agent"}`);
              if (onTraceCompleted && data.messageId) {
                onTraceCompleted(
                  data.messageId,
                  data.exitCode === 0 || data.exitCode == null ? "completed" : "error",
                  data.exitCode ?? null,
                );
              }
              continue;
            }

            if (data.type === "interactive_prompt") {
              if (onInteractivePrompt) {
                onInteractivePrompt({
                  sessionId: data.sessionId ?? sessionId,
                  agentId: data.agentId ?? "",
                  agentName: data.agentName ?? "",
                  messageId: data.messageId ?? "",
                  processId: data.processId ?? "",
                  content: data.content ?? "",
                  promptType: "confirm",
                });
              }
              continue;
            }

            // token streaming
            if (data.agentId && data.token && data.callKey && onAgentToken) {
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

function parseDraftPlan(data: Record<string, unknown>): DraftOrchestratorPlan {
  const validation = data.validation as Record<string, unknown> | undefined;
  const visualization = data.visualization as Record<string, unknown> | undefined;
  return {
    ok: data.ok !== false,
    rawOutput: typeof data.rawOutput === "string" ? data.rawOutput : undefined,
    normalizedPlan: typeof data.normalizedPlan === "object" && data.normalizedPlan !== null
      ? data.normalizedPlan as Record<string, unknown>
      : undefined,
    validation: validation ? {
      ok: validation.ok !== false,
      errors: Array.isArray(validation.errors) ? validation.errors.map(String) : [],
      warnings: Array.isArray(validation.warnings) ? validation.warnings.map(String) : [],
    } : undefined,
    visualization: visualization && typeof visualization.mermaid === "string"
      ? { mermaid: visualization.mermaid }
      : undefined,
    error: typeof data.error === "string" ? data.error : undefined,
  };
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
