import type {
  Session, Message, AgentConfig, AgentConfigCreate, AgentConfigUpdate,
  RouteAgent, CollabTask, ChainStep, ChainConfigInput,
  DAGPhase, PhaseChangeEvent, AgentStartEvent, OrchestratorSummaryStartEvent,
  Artifact, ArtifactDiff, ArtifactEditRequest, ArtifactEditResult, ArtifactVersion,
  ArtifactScanResult,
  Project, ProjectCreateInput, ProjectUpdateInput, ProjectDeleteResult, FolderPickResult,
  PreviewResult, WorkspaceFile,
  ExecutionTraceItem,
  CodexLocalConfig, CodexLocalConfigUpdate,
  SkillDefinition,
  BuildOrchestratorInputRequest, BuildOrchestratorInputResult,
  GenerateOrchestratorPlanRequest, GenerateOrchestratorPlanResult,
  ParseOrchestratorOutputRequest, ParseOrchestratorOutputResult,
  OrchestratorExecution,
  RunRead, TaskRead, ApprovalCheckpoint, SystemHealthRead, CodeReference,
  StewardDecisionEvent,
} from "../types";
import { parseDagPhases, parseTasks } from "./orchestratorEvents";
import { chinaNowIso } from "../utils/time";

const API_BASE = "/api";

export async function fetchAgents(): Promise<AgentConfig[]> {
  const res = await fetch(`${API_BASE}/agents`);
  if (!res.ok) throw new Error("Failed to fetch agents");
  return res.json();
}

export async function seedDefaultAgents(): Promise<AgentConfig[]> {
  const res = await fetch(`${API_BASE}/agents/seed-defaults`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to seed default agents");
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

export async function readProjectFile(projectId: string, path: string): Promise<WorkspaceFile> {
  const params = new URLSearchParams({ path });
  const res = await fetch(`${API_BASE}/projects/${projectId}/files?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to read project file");
  return res.json();
}

export async function writeProjectFile(
  projectId: string,
  path: string,
  content: string,
): Promise<WorkspaceFile> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/files`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  if (!res.ok) throw new Error("Failed to write project file");
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

export async function fetchSessions(projectId?: string, includeArchived = false): Promise<Session[]> {
  const params = new URLSearchParams();
  if (projectId) params.set("projectId", projectId);
  if (includeArchived) params.set("includeArchived", "true");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${API_BASE}/sessions${suffix}`);
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

export async function pinSession(sessionId: string, isPinned: boolean): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ isPinned }),
  });
  if (!res.ok) throw new Error("Failed to update session pin");
  return res.json();
}

export async function archiveSession(sessionId: string, archived = true): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ archived }),
  });
  if (!res.ok) throw new Error("Failed to archive session");
  return res.json();
}

export async function muteSession(sessionId: string, isMuted: boolean): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ isMuted }),
  });
  if (!res.ok) throw new Error("Failed to update session mute");
  return res.json();
}

export async function markSessionRead(sessionId: string): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/read`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to mark session read");
  return res.json();
}

export async function forwardMessages(
  messageIds: string[],
  targetSessionIds: string[],
): Promise<{ messages: Message[] }> {
  const res = await fetch(`${API_BASE}/sessions/forward`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messageIds, targetSessionIds }),
  });
  if (!res.ok) throw new Error("Failed to forward messages");
  return res.json();
}

export async function fetchSessionMembers(sessionId: string): Promise<Array<{ agentConfigId: string; agentName: string }>> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/members`);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchMessages(sessionId: string): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}

export async function fetchRuns(sessionId: string): Promise<RunRead[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/runs`);
  if (!res.ok) throw new Error("Failed to fetch runs");
  return res.json();
}

export async function cancelRun(runId: string, reason?: string): Promise<RunRead> {
  const res = await fetch(`${API_BASE}/runs/${runId}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason ?? "" }),
  });
  if (!res.ok) throw new Error("Failed to cancel run");
  return res.json();
}

export async function fetchRunTasks(runId: string): Promise<TaskRead[]> {
  const res = await fetch(`${API_BASE}/runs/${runId}/tasks`);
  if (!res.ok) throw new Error("Failed to fetch run tasks");
  return res.json();
}

export async function fetchApprovals(sessionId: string): Promise<ApprovalCheckpoint[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/approvals`);
  if (!res.ok) throw new Error("Failed to fetch approvals");
  return res.json();
}

export async function approveCheckpoint(
  checkpointId: string,
  input: { artifactId?: string | null; artifactVersion?: number | null; comment?: string | null } = {},
): Promise<ApprovalCheckpoint> {
  const res = await fetch(`${API_BASE}/approvals/${checkpointId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error("Failed to approve checkpoint");
  return res.json();
}

export async function rejectCheckpoint(
  checkpointId: string,
  input: {
    reason: string;
    artifactId?: string | null;
    artifactVersion?: number | null;
    codeReference?: CodeReference | null;
  },
): Promise<ApprovalCheckpoint> {
  const res = await fetch(`${API_BASE}/approvals/${checkpointId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error("Failed to reject checkpoint");
  return res.json();
}

export async function fetchSystemHealth(input: {
  projectId?: string | null;
  sessionId?: string | null;
  agentId?: string | null;
} = {}): Promise<SystemHealthRead> {
  const params = new URLSearchParams();
  if (input.projectId) params.set("projectId", input.projectId);
  if (input.sessionId) params.set("sessionId", input.sessionId);
  if (input.agentId) params.set("agentId", input.agentId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${API_BASE}/system/health${suffix}`);
  if (!res.ok) throw new Error("Failed to fetch system health");
  return res.json();
}

export async function checkSystemHealth(input: {
  projectId?: string | null;
  sessionId?: string | null;
  agentId?: string | null;
} = {}): Promise<SystemHealthRead> {
  const res = await fetch(`${API_BASE}/system/health/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error("Failed to check system health");
  return res.json();
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onDone: (messageId?: string, error?: string) => void;
  onRoute?: (agents: RouteAgent[]) => void;
  onTaskStarted?: (
    tasks: CollabTask[], intent: string, dagPhases: DAGPhase[], planSummary: string,
  ) => void;
  onStewardDecision?: (decision: StewardDecisionEvent) => void;
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
  onArtifactScanStarted?: (messageId: string) => void;
  onArtifactCreated?: (artifact: Artifact) => void;
  onArtifactScanCompleted?: (
    messageId: string,
    summary: { createdCount: number; candidateCount: number; skippedCount: number },
  ) => void;
  onArtifactDetectionFailed?: (messageId: string, reason?: string) => void;
  onRunStarted?: (run: RunRead) => void;
  onRunStatusChanged?: (run: RunRead) => void;
  onTaskStatusChanged?: (task: TaskRead) => void;
  onApprovalCreated?: (approval: ApprovalCheckpoint) => void;
  onApprovalStatusChanged?: (approval: ApprovalCheckpoint) => void;
  onSessionTitleUpdated?: (session: Session) => void;
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
    onToken, onDone, onRoute, onTaskStarted, onStewardDecision, onChainStep, onPhaseChange,
    onTaskCompleted, onAgentStart, onOrchestratorSummaryStart,
    onOrchestratorSummaryToken, onAgentToken, onProgress, onInteractivePrompt,
    onTraceDelta, onTraceCompleted, onArtifactScanStarted, onArtifactCreated,
    onArtifactScanCompleted, onArtifactDetectionFailed,
    onRunStarted, onRunStatusChanged, onTaskStatusChanged,
    onApprovalCreated, onApprovalStatusChanged,
    onSessionTitleUpdated,
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

            if (data.type === "run.started" && onRunStarted) {
              const run = normalizeRun(data.run);
              if (run) onRunStarted(run);
              continue;
            }

            if (data.type === "run.status_changed" && onRunStatusChanged) {
              const run = normalizeRun(data.run);
              if (run) onRunStatusChanged(run);
              continue;
            }

            if (data.type === "task.status_changed" && onTaskStatusChanged) {
              const task = normalizeTask(data.task);
              if (task) onTaskStatusChanged(task);
              continue;
            }

            if (data.type === "approval.created" && onApprovalCreated) {
              const approval = normalizeApproval(data.approval);
              if (approval) onApprovalCreated(approval);
              continue;
            }

            if (data.type === "approval.status_changed" && onApprovalStatusChanged) {
              const approval = normalizeApproval(data.approval);
              if (approval) onApprovalStatusChanged(approval);
              continue;
            }

            if (data.type === "session.title_updated" && onSessionTitleUpdated) {
              const session = normalizeSession(data.session);
              if (session) onSessionTitleUpdated(session);
              continue;
            }

            // orchestrator.route
            if (data.type === "orchestrator.route" && onRoute) {
              onRoute(data.agents);
              continue;
            }

            if (data.type === "orchestrator.steward_decision") {
              const decision = normalizeStewardDecision(data.decision ?? data);
              if (decision && onStewardDecision) onStewardDecision(decision);
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

            if (data.type === "orchestrator.task_completed") {
              if (onTaskCompleted) onTaskCompleted(data.summary ?? "");
              if (!completed) {
                completed = true;
                onDone(undefined, undefined);
              }
              continue;
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
                  timestamp: trace.timestamp ?? chinaNowIso(),
                }, {
                  agentName: data.agentName,
                  processId: data.processId,
                });
              }
              if (onProgress && data.chunk) onProgress(data.chunk);
              continue;
            }

            if (data.type === "agent.process.started") {
              const agentName = data.agentName || "CLI Agent";
              const processText = processStartText(agentName, data);
              if (onTraceDelta && data.messageId && data.callKey) {
                onTraceDelta(data.messageId, {
                  id: `trace-${Date.now()}-${Math.random().toString(16).slice(2)}`,
                  kind: "process",
                  text: processText,
                  title: processText,
                  action: data.recovered ? "recover" : data.reused ? "reuse" : "start",
                  source: "system",
                  chunkType: "process",
                  processId: data.processId ?? null,
                  persistentProcess: Boolean(data.persistentProcess),
                  reused: Boolean(data.reused),
                  recovered: Boolean(data.recovered),
                  timestamp: chinaNowIso(),
                }, {
                  agentName: data.agentName,
                  processId: data.processId,
                });
              }
              if (onProgress) onProgress(`${processText}...`);
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

            if (data.type === "artifact.scan.started") {
              if (data.messageId && onArtifactScanStarted) onArtifactScanStarted(data.messageId);
              continue;
            }

            if (data.type === "artifact.created") {
              const artifact = normalizeArtifactEvent(data);
              if (artifact && onArtifactCreated) onArtifactCreated(artifact);
              continue;
            }

            if (data.type === "artifact.scan.completed") {
              if (data.messageId && onArtifactScanCompleted) {
                onArtifactScanCompleted(data.messageId, {
                  createdCount: Number(data.createdCount ?? 0),
                  candidateCount: Number(data.candidateCount ?? 0),
                  skippedCount: Number(data.skippedCount ?? 0),
                });
              }
              continue;
            }

            if (data.type === "artifact.detection_failed") {
              if (data.messageId && onArtifactDetectionFailed) {
                onArtifactDetectionFailed(data.messageId, typeof data.reason === "string" ? data.reason : undefined);
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
              if (!completed) {
                completed = true;
                onDone(data.messageId, data.error);
              }
              continue;
            }
          } catch { /* parse error */ }
        }
      }
    }
    if (!completed) onDone(undefined, "Stream ended unexpectedly");
  })().catch((error: unknown) => {
    if (error instanceof DOMException && error.name === "AbortError") {
      return;
    }
    if (error instanceof Error && error.name === "AbortError") {
      return;
    }
    onDone(undefined, error instanceof Error ? error.message : "Stream failed");
  });

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
  })().catch((error: unknown) => {
    if (error instanceof DOMException && error.name === "AbortError") {
      return;
    }
    if (error instanceof Error && error.name === "AbortError") {
      return;
    }
    callbacks.onDone(undefined, error instanceof Error ? error.message : "Stream failed");
  });

  return () => abortCtrl.abort();
}

function normalizeArtifactEvent(data: Record<string, unknown>): Artifact | null {
  const raw = data.artifact && typeof data.artifact === "object"
    ? data.artifact as Record<string, unknown>
    : data;
  const id = raw.id ?? raw.artifactId;
  if (typeof id !== "string") return null;
  const type = raw.type ?? raw.artifactType;
  if (type !== "code_diff" && type !== "web_preview" && type !== "document" && type !== "file_tree") {
    return null;
  }
  const sessionId = typeof raw.sessionId === "string" ? raw.sessionId : "";
  const messageId = typeof raw.messageId === "string" ? raw.messageId : "";
  if (!sessionId || !messageId) return null;
  return {
    id,
    sessionId,
    messageId,
    projectId: typeof raw.projectId === "string" ? raw.projectId : null,
    type,
    title: typeof raw.title === "string" ? raw.title : "产物",
    content: typeof raw.content === "string" ? raw.content : "",
    status: raw.status === "rendering" || raw.status === "error" ? raw.status : "ready",
    version: typeof raw.version === "number" ? raw.version : 1,
    parentArtifactId: typeof raw.parentArtifactId === "string" ? raw.parentArtifactId : null,
    filePath: typeof raw.filePath === "string" ? raw.filePath : null,
    previewId: typeof raw.previewId === "string" ? raw.previewId : null,
    source: typeof raw.source === "string" ? raw.source : null,
    createdAt: typeof raw.createdAt === "string" ? raw.createdAt : chinaNowIso(),
  };
}

function normalizeRun(raw: unknown): RunRead | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (typeof data.id !== "string" || typeof data.sessionId !== "string") return null;
  const status = normalizeRunStatus(data.status);
  if (!status) return null;
  return {
    id: data.id,
    sessionId: data.sessionId,
    projectId: typeof data.projectId === "string" ? data.projectId : null,
    mode: typeof data.mode === "string" ? data.mode : "single",
    status,
    currentMessageId: typeof data.currentMessageId === "string" ? data.currentMessageId : null,
    startedAt: typeof data.startedAt === "string" ? data.startedAt : chinaNowIso(),
    updatedAt: typeof data.updatedAt === "string" ? data.updatedAt : chinaNowIso(),
    completedAt: typeof data.completedAt === "string" ? data.completedAt : null,
    cancelReason: typeof data.cancelReason === "string" ? data.cancelReason : null,
    metadata: isRecord(data.metadata) ? data.metadata : null,
  };
}

function normalizeTask(raw: unknown): TaskRead | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (typeof data.id !== "string" || typeof data.runId !== "string" || typeof data.sessionId !== "string") return null;
  const status = normalizeTaskStatus(data.status);
  if (!status) return null;
  return {
    id: data.id,
    runId: data.runId,
    sessionId: data.sessionId,
    agentId: typeof data.agentId === "string" ? data.agentId : null,
    messageId: typeof data.messageId === "string" ? data.messageId : null,
    name: typeof data.name === "string" ? data.name : "primary",
    role: typeof data.role === "string" ? data.role : null,
    phase: typeof data.phase === "number" ? data.phase : null,
    status,
    dependsOn: Array.isArray(data.dependsOn) ? data.dependsOn.map(String) : [],
    startedAt: typeof data.startedAt === "string" ? data.startedAt : null,
    completedAt: typeof data.completedAt === "string" ? data.completedAt : null,
    metadata: isRecord(data.metadata) ? data.metadata : null,
  };
}

function normalizeApproval(raw: unknown): ApprovalCheckpoint | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (
    typeof data.id !== "string"
    || typeof data.runId !== "string"
    || typeof data.taskId !== "string"
    || typeof data.sessionId !== "string"
  ) return null;
  const status = normalizeApprovalStatus(data.status);
  if (!status) return null;
  return {
    id: data.id,
    runId: data.runId,
    taskId: data.taskId,
    sessionId: data.sessionId,
    messageId: typeof data.messageId === "string" ? data.messageId : null,
    artifactId: typeof data.artifactId === "string" ? data.artifactId : null,
    artifactVersion: typeof data.artifactVersion === "number" ? data.artifactVersion : null,
    title: typeof data.title === "string" ? data.title : "等待确认",
    summary: typeof data.summary === "string" ? data.summary : "",
    status,
    reason: typeof data.reason === "string" ? data.reason : null,
    createdAt: typeof data.createdAt === "string" ? data.createdAt : chinaNowIso(),
    decidedAt: typeof data.decidedAt === "string" ? data.decidedAt : null,
    metadata: isRecord(data.metadata) ? data.metadata : null,
  };
}

function normalizeSession(raw: unknown): Session | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (typeof data.id !== "string" || typeof data.title !== "string") return null;
  return {
    id: data.id,
    title: data.title,
    projectId: typeof data.projectId === "string" ? data.projectId : null,
    agentConfigId: typeof data.agentConfigId === "string" ? data.agentConfigId : null,
    mode: data.mode === "group" ? "group" : "single",
    isPinned: Boolean(data.isPinned),
    archivedAt: typeof data.archivedAt === "string" ? data.archivedAt : null,
    unreadCount: typeof data.unreadCount === "number" ? data.unreadCount : 0,
    lastReadAt: typeof data.lastReadAt === "string" ? data.lastReadAt : null,
    isMuted: Boolean(data.isMuted),
    createdAt: typeof data.createdAt === "string" ? data.createdAt : chinaNowIso(),
    updatedAt: typeof data.updatedAt === "string" ? data.updatedAt : chinaNowIso(),
  };
}

function normalizeStewardDecision(raw: unknown): StewardDecisionEvent | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const routeType = normalizeStewardRouteType(data.routeType ?? data.route_type);
  if (!routeType) return null;
  return {
    routeType,
    confidence: typeof data.confidence === "number" ? data.confidence : 0,
    reason: typeof data.reason === "string" ? data.reason : "",
    selectedAgents: normalizeRouteAgents(data.selectedAgents ?? data.selected_agents),
    taskBrief: typeof data.taskBrief === "string"
      ? data.taskBrief
      : typeof data.task_brief === "string" ? data.task_brief : "",
    requiresApproval: Boolean(data.requiresApproval ?? data.requires_approval),
    riskLevel: normalizeRiskLevel(data.riskLevel ?? data.risk_level),
    intent: typeof data.intent === "string" ? data.intent : "general_qa",
    requiredTags: Array.isArray(data.requiredTags)
      ? data.requiredTags.map(String)
      : Array.isArray(data.required_tags) ? data.required_tags.map(String) : [],
  };
}

function normalizeRouteAgents(raw: unknown): RouteAgent[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const data = item as Record<string, unknown>;
    if (typeof data.id !== "string" || typeof data.name !== "string") return [];
    return [{ id: data.id, name: data.name }];
  });
}

function normalizeRunStatus(value: unknown): RunRead["status"] | null {
  if (
    value === "queued" || value === "running" || value === "pausing"
    || value === "paused" || value === "cancelling" || value === "cancelled"
    || value === "completed" || value === "failed"
  ) return value;
  return null;
}

function normalizeTaskStatus(value: unknown): TaskRead["status"] | null {
  if (
    value === "pending" || value === "running" || value === "paused"
    || value === "completed" || value === "failed" || value === "cancelled"
    || value === "rejected"
  ) return value;
  return null;
}

function normalizeStewardRouteType(value: unknown): StewardDecisionEvent["routeType"] | null {
  if (
    value === "context_only" || value === "single_agent"
    || value === "mini_collab" || value === "draft_plan"
  ) return value;
  return null;
}

function normalizeRiskLevel(value: unknown): StewardDecisionEvent["riskLevel"] {
  if (value === "medium" || value === "high") return value;
  return "low";
}

function normalizeApprovalStatus(value: unknown): ApprovalCheckpoint["status"] | null {
  if (value === "pending_review" || value === "approved" || value === "rejected") return value;
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function processStartText(agentName: string, data: Record<string, unknown>) {
  if (data.recovered) return `恢复 ${agentName} 常驻进程`;
  if (data.reused) return `复用 ${agentName} 常驻进程`;
  if (data.persistentProcess) return `启动 ${agentName} 常驻进程`;
  if (data.engineSessionMode === "resume") return `恢复 ${agentName} 会话`;
  if (data.engineSessionMode === "start") return `创建 ${agentName} 会话`;
  return `正在启动 ${agentName}`;
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

export async function buildOrchestratorInput(
  data: BuildOrchestratorInputRequest,
): Promise<BuildOrchestratorInputResult> {
  const res = await fetch(`${API_BASE}/debug/orchestrator/build-input`, {
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

export async function parseOrchestratorOutput(
  data: ParseOrchestratorOutputRequest,
): Promise<ParseOrchestratorOutputResult> {
  const res = await fetch(`${API_BASE}/debug/orchestrator/parse-output`, {
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

export async function generateOrchestratorPlan(
  data: GenerateOrchestratorPlanRequest,
): Promise<GenerateOrchestratorPlanResult> {
  const res = await fetch(`${API_BASE}/debug/orchestrator/generate-plan`, {
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

export async function fetchOrchestratorExecution(executionId: string): Promise<OrchestratorExecution> {
  const res = await fetch(`${API_BASE}/orchestrator/executions/${encodeURIComponent(executionId)}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function cancelOrchestratorExecution(executionId: string): Promise<OrchestratorExecution> {
  const res = await fetch(`${API_BASE}/orchestrator/executions/${encodeURIComponent(executionId)}/cancel`, {
    method: "POST",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function saveArtifactContent(
  artifactId: string,
  content: string,
  title?: string | null,
): Promise<Artifact> {
  const body: Record<string, unknown> = { content, writeWorkspace: true };
  if (title) body.title = title;
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Failed to save artifact");
  return res.json();
}

export async function restoreArtifactVersion(
  artifactId: string,
  version: number,
): Promise<Artifact> {
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/restore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version, writeWorkspace: true }),
  });
  if (!res.ok) throw new Error("Failed to restore artifact version");
  return res.json();
}

export async function scanMessageArtifacts(
  messageId: string,
  force = true,
): Promise<ArtifactScanResult> {
  const res = await fetch(`${API_BASE}/messages/${messageId}/artifacts/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
  if (!res.ok) throw new Error("Failed to scan message artifacts");
  return res.json();
}
