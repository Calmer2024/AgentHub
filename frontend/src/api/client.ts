import type {
  Session, SessionMember, Message, AgentConfig, AgentConfigCreate, AgentConfigUpdate,
  RouteAgent, CollabTask, ChainStep, ChainConfigInput,
  DAGPhase, PhaseChangeEvent, AgentStartEvent, OrchestratorSummaryStartEvent,
  Artifact, ArtifactDiff, ArtifactEditRequest, ArtifactEditResult, ArtifactVersion,
  ArtifactScanResult,
  Project, ProjectCreateInput, ProjectUpdateInput, ProjectDeleteResult, FolderPickResult,
  PreviewResult, WorkspaceFile,
  BuildList, BuildLogs, BuildQueuedResult, ProjectPreviewResult,
  PreviewSession, Deployment, DeploymentLogs,
  ExecutionTraceItem,
  CurrentUser, Team, TeamMember, TeamRole, CloudWorkspace, WorkspaceSnapshot, AuditLog,
  Sandbox, RuntimeImage, RunnerNode, QuotaSummary, SecretCreateInput, SecretRef, RuntimeLogs,
  CodexLocalConfig, CodexLocalConfigUpdate,
  SkillDefinition,
  BuildOrchestratorInputRequest, BuildOrchestratorInputResult,
  GenerateOrchestratorPlanRequest, GenerateOrchestratorPlanResult,
  ParseOrchestratorOutputRequest, ParseOrchestratorOutputResult,
  OrchestratorExecution,
  RunRead, TaskRead, ApprovalCheckpoint, SystemHealthRead, CodeReference,
  StewardDecisionEvent,
  Comment, Attachment, ArtifactReference, Notification, MobileSessionSummary,
  RenderedArtifact, AgentTemplateSession, GitSyncJob,
  RuntimeCapabilities, AuthProvider, AuthSession,
  CliCredentialConfig, CliCredentialTool, CliCredentialUpdateInput, CliModelList,
} from "../types";
import { parseDagPhases, parseTasks } from "./orchestratorEvents";
import { chinaNowIso } from "../utils/time";

type ApiAuthProvider = () => Record<string, string>;

interface ApiClientConfig {
  apiBaseUrl?: string;
  cloudAuthProvider?: ApiAuthProvider | null;
}

const AUTH_SESSION_STORAGE_KEY = "agenthub.authSession";

let activeApiBase = normalizeApiBase(import.meta.env.VITE_AGENTHUB_API_BASE);
let activeCloudAuthProvider: ApiAuthProvider | null = null;
let activeAuthSession: AuthSession | null = readStoredAuthSession();

const API_BASE = {
  toString: () => activeApiBase,
};

const DEV_CLOUD_USER_HEADERS: Record<string, string> = {
  "X-AgentHub-User-Email": "demo@agenthub.local",
  "X-AgentHub-User-Name": "AgentHub Demo",
};

export function configureApiClient(config: ApiClientConfig = {}): void {
  if (typeof config.apiBaseUrl === "string") {
    activeApiBase = normalizeApiBase(config.apiBaseUrl);
  }
  if ("cloudAuthProvider" in config) {
    activeCloudAuthProvider = config.cloudAuthProvider ?? null;
  }
}

export function createApiClient(config: ApiClientConfig = {}) {
  configureApiClient(config);
  return {
    fetchCapabilities,
    fetchCurrentUser,
    fetchProjects,
    fetchTeams,
  };
}

export function createDevCloudAuthProvider(): ApiAuthProvider {
  return () => ({ ...DEV_CLOUD_USER_HEADERS });
}

export function resetApiClientForTests(): void {
  activeApiBase = "/api";
  activeCloudAuthProvider = null;
  activeAuthSession = null;
}

export function getStoredAuthSession(): AuthSession | null {
  return activeAuthSession;
}

function setAuthSession(session: AuthSession): void {
  activeAuthSession = session;
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session));
}

function clearAuthSession(): void {
  activeAuthSession = null;
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
}

function readStoredAuthSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY);
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as Partial<AuthSession>;
    if (typeof data.accessToken !== "string" || typeof data.refreshToken !== "string") return null;
    if (!data.user || typeof data.user !== "object") return null;
    return {
      accessToken: data.accessToken,
      refreshToken: data.refreshToken,
      tokenType: "bearer",
      expiresAt: typeof data.expiresAt === "string" ? data.expiresAt : "",
      user: data.user as CurrentUser,
    };
  } catch {
    return null;
  }
}

function normalizeApiBase(value?: string): string {
  const trimmed = value?.trim().replace(/\/+$/, "");
  if (!trimmed) return "/api";
  if (trimmed === "/api" || trimmed.endsWith("/api")) return trimmed;
  if (trimmed.startsWith("/")) return `${trimmed}/api`;
  return `${trimmed}/api`;
}

function cloudHeaders(extra: Record<string, string> = {}): Record<string, string> {
  if (activeAuthSession?.accessToken) {
    return { ...extra, Authorization: `Bearer ${activeAuthSession.accessToken}` };
  }
  return { ...extra, ...(activeCloudAuthProvider?.() ?? {}) };
}

function optionalCloudHeaders(extra: Record<string, string> = {}): RequestInit | undefined {
  const headers = cloudHeaders(extra);
  return Object.keys(headers).length > 0 ? { headers } : undefined;
}

function cloudJsonHeaders(): Record<string, string> {
  return cloudHeaders({ "Content-Type": "application/json" });
}

async function readApiError(res: Response, fallback: string) {
  try {
    const data = await res.json();
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail;
      const message = formatApiDetail(detail);
      if (message) return message;
    }
  } catch { /* keep fallback */ }
  return fallback;
}

function formatApiDetail(detail: unknown): string | null {
  if (typeof detail === "string") return translateApiMessage(detail);
  if (!Array.isArray(detail)) return null;
  const messages = detail.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const data = item as Record<string, unknown>;
    const msg = typeof data.msg === "string" ? data.msg : "";
    const loc = Array.isArray(data.loc) ? data.loc.map(String) : [];
    const field = loc[loc.length - 1] ?? "";
    const translated = translateValidationMessage(field, msg);
    return translated ? [translated] : [];
  });
  return messages.length > 0 ? Array.from(new Set(messages)).join("；") : null;
}

function translateValidationMessage(field: string, message: string): string {
  const source = message.toLowerCase();
  if (field === "username") {
    if (source.includes("3-32") || source.includes("too_short") || source.includes("too_long")) return "用户名需要 3-32 个字符";
    if (source.includes("invalid") || source.includes("characters")) return "用户名只能包含字母、数字、下划线或连字符";
    return "用户名格式不正确";
  }
  if (field === "email") return "请输入有效邮箱";
  if (field === "password") {
    if (source.includes("at least 8") || source.includes("too_short")) return "密码至少 8 位";
    return "密码格式不正确";
  }
  if (message) return translateApiMessage(message);
  return "";
}

function translateApiMessage(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("username already registered")) return "用户名已被注册";
  if (lower.includes("email already registered")) return "邮箱已被注册";
  if (lower.includes("invalid username or password")) return "用户名或密码错误";
  if (lower.includes("identifier required") || lower.includes("identifier is required")) return "请输入用户名或邮箱";
  if (lower.includes("password required")) return "请输入密码";
  if (lower.includes("username length must be 3-32")) return "用户名需要 3-32 个字符";
  if (lower.includes("username contains invalid characters")) return "用户名只能包含字母、数字、下划线或连字符";
  if (lower.includes("username must start")) return "用户名必须以字母或数字开头";
  if (lower.includes("password length must be at least 8")) return "密码至少 8 位";
  if (lower.includes("email must be valid")) return "请输入有效邮箱";
  return message;
}

export async function fetchAgents(): Promise<AgentConfig[]> {
  const res = await fetch(`${API_BASE}/agents`, optionalCloudHeaders());
  if (!res.ok) throw new Error(await readApiError(res, "Agent 加载失败"));
  return res.json();
}

export async function seedDefaultAgents(): Promise<AgentConfig[]> {
  const res = await fetch(`${API_BASE}/agents/seed-defaults`, { method: "POST", headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "默认 Agent 初始化失败"));
  return res.json();
}

export async function configureBuiltinAgentsCodex(): Promise<AgentConfig[]> {
  const res = await fetch(`${API_BASE}/agents/configure-builtins-codex`, { method: "POST", headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "内置 Agent 配置失败"));
  return res.json();
}

export async function fetchSkills(): Promise<SkillDefinition[]> {
  const res = await fetch(`${API_BASE}/skills`);
  if (!res.ok) throw new Error("Failed to fetch skills");
  return res.json();
}

export async function fetchCapabilities(): Promise<RuntimeCapabilities> {
  const res = await fetch(`${API_BASE}/capabilities`);
  if (!res.ok) throw new Error(await readApiError(res, "能力矩阵加载失败"));
  return res.json();
}

export async function fetchAuthProviders(): Promise<AuthProvider[]> {
  const res = await fetch(`${API_BASE}/auth/providers`);
  if (!res.ok) throw new Error(await readApiError(res, "登录方式加载失败"));
  const data = await res.json() as { items?: AuthProvider[] };
  return Array.isArray(data.items) ? data.items : [];
}

export async function loginWithEmail(input: {
  email?: string;
  username?: string;
  identifier?: string;
  password?: string;
  displayName?: string;
}): Promise<AuthSession> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      identifier: input.identifier,
      email: input.email,
      username: input.username,
      password: input.password,
      displayName: input.displayName,
    }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "登录失败"));
  const session = await res.json() as AuthSession;
  setAuthSession(session);
  return session;
}

export async function registerWithPassword(input: {
  username: string;
  email: string;
  password: string;
  displayName?: string;
}): Promise<AuthSession> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      username: input.username,
      email: input.email,
      password: input.password,
      displayName: input.displayName,
    }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "注册失败"));
  const session = await res.json() as AuthSession;
  setAuthSession(session);
  return session;
}

export async function refreshAuthSession(): Promise<AuthSession> {
  const refreshToken = activeAuthSession?.refreshToken;
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: refreshToken ? { "Content-Type": "application/json" } : undefined,
    credentials: "include",
    body: refreshToken ? JSON.stringify({ refreshToken }) : undefined,
  });
  if (!res.ok) {
    clearAuthSession();
    throw new Error(await readApiError(res, "登录已过期"));
  }
  const session = await res.json() as AuthSession;
  setAuthSession(session);
  return session;
}

export async function logoutCurrentUser(): Promise<void> {
  const refreshToken = activeAuthSession?.refreshToken;
  const res = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    credentials: "include",
    body: JSON.stringify({ refreshToken }),
  });
  clearAuthSession();
  if (!res.ok && res.status !== 204) throw new Error(await readApiError(res, "退出登录失败"));
}

export async function createAgent(data: AgentConfigCreate): Promise<AgentConfig> {
  const res = await fetch(`${API_BASE}/agents`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await readApiError(res, "创建 Agent 失败"));
  return res.json();
}

export async function updateAgent(id: string, data: AgentConfigUpdate): Promise<AgentConfig> {
  const res = await fetch(`${API_BASE}/agents/${id}`, {
    method: "PATCH",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await readApiError(res, "更新 Agent 失败"));
  return res.json();
}

export async function deleteAgent(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/agents/${id}`, { method: "DELETE", headers: cloudHeaders() });
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

export async function fetchCurrentUser(): Promise<CurrentUser> {
  const res = await fetch(`${API_BASE}/auth/me`, { headers: cloudHeaders(), credentials: "include" });
  if (res.status === 401) {
    try {
      await refreshAuthSession();
    } catch {
      throw new Error(await readApiError(res, "请先登录后继续"));
    }
    const retry = await fetch(`${API_BASE}/auth/me`, { headers: cloudHeaders(), credentials: "include" });
    if (!retry.ok) throw new Error(await readApiError(retry, "请先登录后继续"));
    return retry.json();
  }
  if (!res.ok) {
    if (res.status === 401) clearAuthSession();
    throw new Error(await readApiError(res, "请先登录后继续"));
  }
  return res.json();
}

export async function updateCurrentUserProfile(input: {
  displayName?: string;
  avatarUrl?: string | null;
}): Promise<CurrentUser> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    method: "PUT",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "资料保存失败"));
  const user = await res.json() as CurrentUser;
  if (activeAuthSession) {
    setAuthSession({ ...activeAuthSession, user });
  }
  return user;
}

export async function fetchTeams(): Promise<Team[]> {
  const res = await fetch(`${API_BASE}/teams`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch teams"));
  const data = await res.json() as { items?: Team[] };
  return Array.isArray(data.items) ? data.items : [];
}

export async function createTeam(name: string): Promise<Team> {
  const res = await fetch(`${API_BASE}/teams`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to create team"));
  return res.json();
}

export async function addTeamMember(
  teamId: string,
  email: string,
  role: TeamRole,
): Promise<TeamMember> {
  const res = await fetch(`${API_BASE}/teams/${teamId}/members`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ email, role }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to add team member"));
  return res.json();
}

export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/projects`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to fetch projects");
  return res.json();
}

export async function createProject(data: ProjectCreateInput): Promise<Project> {
  const headers = data.workspaceMode === "cloud" || data.teamId
    ? cloudJsonHeaders()
    : { "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE}/projects`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to create project"));
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
    headers: cloudJsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update project");
  return res.json();
}

export async function archiveProject(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/archive`, {
    method: "POST",
    headers: cloudHeaders(),
  });
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
    headers: cloudJsonHeaders(),
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

export async function startProjectBuild(
  projectId: string,
  input: { command?: string | null; installCommand?: string | null; artifactPath?: string | null } = {},
): Promise<BuildQueuedResult> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/builds`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to start project build"));
  return res.json();
}

export async function fetchProjectBuilds(projectId: string): Promise<BuildList> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/builds`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch project builds"));
  return res.json();
}

export async function fetchProjectBuildLogs(projectId: string, buildId: string): Promise<BuildLogs> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/builds/${buildId}/logs`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch project build logs"));
  return res.json();
}

export async function createProjectBuildPreview(
  projectId: string,
  input: { source: "workspace" | "build"; path?: string | null; buildId?: string | null },
): Promise<ProjectPreviewResult> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/previews`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to create project preview"));
  return res.json();
}

export async function createArtifactPreview(
  artifactId: string,
  input: {
    source?: "static" | "build" | "dev_server";
    artifactVersionId?: string | null;
    ttlSeconds?: number;
    visibility?: "public" | "team" | "private";
  } = {},
): Promise<PreviewSession> {
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/previews`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({
      source: input.source ?? "static",
      artifactVersionId: input.artifactVersionId ?? undefined,
      ttlSeconds: input.ttlSeconds,
      visibility: input.visibility ?? "team",
    }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to create cloud preview"));
  return res.json();
}

export async function fetchPreview(previewId: string): Promise<PreviewSession> {
  const res = await fetch(`${API_BASE}/previews/${previewId}`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch cloud preview"));
  return res.json();
}

export async function revokePreview(previewId: string, reason?: string): Promise<PreviewSession> {
  const res = await fetch(`${API_BASE}/previews/${previewId}/revoke`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to revoke cloud preview"));
  return res.json();
}

export async function createDeployment(input: {
  artifactId: string;
  artifactVersionId?: string | null;
  target?: "static_hosting" | "third_party";
  visibility?: "public" | "team" | "private";
}): Promise<Deployment> {
  const res = await fetch(`${API_BASE}/deployments`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({
      artifactId: input.artifactId,
      artifactVersionId: input.artifactVersionId ?? input.artifactId,
      target: input.target ?? "static_hosting",
      visibility: input.visibility ?? "team",
    }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to create deployment"));
  return res.json();
}

export async function fetchDeployment(deploymentId: string): Promise<Deployment> {
  const res = await fetch(`${API_BASE}/deployments/${deploymentId}`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch deployment"));
  return res.json();
}

export async function fetchDeploymentLogs(deploymentId: string): Promise<DeploymentLogs> {
  const res = await fetch(`${API_BASE}/deployments/${deploymentId}/logs`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch deployment logs"));
  return res.json();
}

export async function retryDeployment(deploymentId: string, fromStage?: string): Promise<Deployment> {
  const res = await fetch(`${API_BASE}/deployments/${deploymentId}/retry`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ fromStage }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to retry deployment"));
  return res.json();
}

export async function rollbackDeployment(
  deploymentId: string,
  targetDeploymentId: string,
): Promise<Deployment> {
  const res = await fetch(`${API_BASE}/deployments/${deploymentId}/rollback`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ targetDeploymentId }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to rollback deployment"));
  return res.json();
}

export async function createComment(
  projectId: string,
  input: { targetType: "message" | "artifact" | "deployment"; targetId: string; body: string },
): Promise<Comment> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/comments`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to create comment"));
  return res.json();
}

export async function listComments(
  projectId: string,
  input: { targetType?: string; targetId?: string } = {},
): Promise<Comment[]> {
  const params = new URLSearchParams();
  if (input.targetType) params.set("targetType", input.targetType);
  if (input.targetId) params.set("targetId", input.targetId);
  const query = params.toString();
  const res = await fetch(`${API_BASE}/projects/${projectId}/comments${query ? `?${query}` : ""}`, {
    headers: cloudHeaders(),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to list comments"));
  const data = await res.json() as { items?: Comment[] };
  return Array.isArray(data.items) ? data.items : [];
}

export async function uploadAttachment(input: {
  projectId: string;
  sessionId?: string | null;
  file: File;
}): Promise<Attachment> {
  const form = new FormData();
  form.set("projectId", input.projectId);
  if (input.sessionId) form.set("sessionId", input.sessionId);
  form.set("file", input.file);
  const res = await fetch(`${API_BASE}/attachments`, {
    method: "POST",
    headers: cloudHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to upload attachment"));
  return res.json();
}

export async function forwardMessageWithArtifacts(
  messageId: string,
  input: { targetSessionIds: string[]; includeArtifacts?: boolean },
): Promise<{ messages: Message[]; artifactReferences: ArtifactReference[] }> {
  const res = await fetch(`${API_BASE}/messages/${messageId}/forward`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({
      targetSessionIds: input.targetSessionIds,
      includeArtifacts: Boolean(input.includeArtifacts),
    }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to forward message"));
  return res.json();
}

export async function fetchNotifications(): Promise<Notification[]> {
  const res = await fetch(`${API_BASE}/notifications`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch notifications"));
  const data = await res.json() as { items?: Notification[] };
  return Array.isArray(data.items) ? data.items : [];
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/notifications/${notificationId}/read`, {
    method: "POST",
    headers: cloudHeaders(),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to mark notification read"));
}

export async function fetchMobileSessions(): Promise<MobileSessionSummary[]> {
  const res = await fetch(`${API_BASE}/mobile/sessions`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch mobile sessions"));
  return res.json();
}

export async function decideMobileApproval(
  approvalId: string,
  input: { decision: "approve" | "reject"; comment?: string | null },
): Promise<ApprovalCheckpoint> {
  const res = await fetch(`${API_BASE}/mobile/approvals/${approvalId}/decision`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to decide approval"));
  return res.json();
}

export async function renderArtifact(
  artifactId: string,
  format: "html" | "pdf" | "image" = "html",
): Promise<RenderedArtifact> {
  const params = new URLSearchParams({ format });
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/render?${params.toString()}`, {
    headers: cloudHeaders(),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to render artifact"));
  return res.json();
}

export async function createAgentTemplateSession(seedPrompt: string): Promise<AgentTemplateSession> {
  const res = await fetch(`${API_BASE}/agent-template-sessions`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ seedPrompt }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to create agent template session"));
  return res.json();
}

export async function finalizeAgentTemplateSession(
  sessionId: string,
  input: { name: string; engine: AgentConfig["cliTool"] },
): Promise<AgentConfig> {
  const res = await fetch(`${API_BASE}/agent-template-sessions/${sessionId}/finalize`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to finalize agent template"));
  return res.json();
}

export async function createGitSyncJob(
  projectId: string,
  input: { remote: string; branch: string; mode: "pull" | "push" },
): Promise<GitSyncJob> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/git/sync`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to run git sync"));
  return res.json();
}

export function projectSourceExportUrl(projectId: string): string {
  return `${API_BASE}/projects/${projectId}/exports/source`;
}

export function projectBuildExportUrl(projectId: string, buildId: string): string {
  return `${API_BASE}/projects/${projectId}/exports/builds/${buildId}`;
}

export async function readProjectFile(projectId: string, path: string): Promise<WorkspaceFile> {
  const params = new URLSearchParams({ path });
  const res = await fetch(`${API_BASE}/projects/${projectId}/files?${params.toString()}`, { headers: cloudHeaders() });
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
    headers: cloudJsonHeaders(),
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
    headers: cloudHeaders(),
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

export async function fetchWorkspace(workspaceId: string): Promise<CloudWorkspace> {
  const res = await fetch(`${API_BASE}/workspaces/${workspaceId}`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch workspace"));
  return res.json();
}

export async function createWorkspaceSnapshot(
  workspaceId: string,
  label?: string,
): Promise<WorkspaceSnapshot> {
  const res = await fetch(`${API_BASE}/workspaces/${workspaceId}/snapshots`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ label: label || undefined }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to create workspace snapshot"));
  return res.json();
}

export async function restoreWorkspaceSnapshot(
  workspaceId: string,
  snapshotId: string,
  strategy: "replace" | "branch" = "replace",
): Promise<{ restoreId: string }> {
  const res = await fetch(`${API_BASE}/workspaces/${workspaceId}/snapshots/${snapshotId}/restore`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ strategy }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to restore workspace snapshot"));
  return res.json();
}

export async function importWorkspaceZip(
  workspaceId: string,
  file: File,
): Promise<{ importId: string; status: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/workspaces/${workspaceId}/imports/zip`, {
    method: "POST",
    headers: cloudHeaders(),
    body: formData,
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to import workspace zip"));
  return res.json();
}

export async function importWorkspaceGithub(
  workspaceId: string,
  input: { repoUrl: string; branch?: string | null },
): Promise<{ importId: string; status: string }> {
  const res = await fetch(`${API_BASE}/workspaces/${workspaceId}/imports/github`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to import GitHub repo"));
  return res.json();
}

export async function createSandbox(input: {
  workspaceId: string;
  image?: string;
  ttlSeconds?: number | null;
}): Promise<Sandbox> {
  const res = await fetch(`${API_BASE}/sandboxes`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to create sandbox"));
  return res.json();
}

export async function fetchSandbox(sandboxId: string): Promise<Sandbox> {
  const res = await fetch(`${API_BASE}/sandboxes/${sandboxId}`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch sandbox"));
  return res.json();
}

export async function stopSandbox(sandboxId: string, reason?: string): Promise<{ id: string; status: string }> {
  const res = await fetch(`${API_BASE}/sandboxes/${sandboxId}/stop`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ reason: reason ?? "" }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to stop sandbox"));
  return res.json();
}

export async function fetchRuntimeImages(): Promise<RuntimeImage[]> {
  const res = await fetch(`${API_BASE}/runtime/images`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch runtime images"));
  const data = await res.json() as { items?: RuntimeImage[] };
  return Array.isArray(data.items) ? data.items : [];
}

export async function fetchRunnerNodes(): Promise<RunnerNode[]> {
  const res = await fetch(`${API_BASE}/runtime/runner-nodes`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch runner nodes"));
  const data = await res.json() as { items?: RunnerNode[] };
  return Array.isArray(data.items) ? data.items : [];
}

export async function fetchQuotaSummary(): Promise<QuotaSummary> {
  const res = await fetch(`${API_BASE}/quotas/me`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch quota"));
  return res.json();
}

export async function createSecret(input: SecretCreateInput): Promise<SecretRef> {
  const res = await fetch(`${API_BASE}/secrets`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to save secret"));
  return res.json();
}

export async function fetchCliCredentials(): Promise<CliCredentialConfig[]> {
  const res = await fetch(`${API_BASE}/cli-credentials`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "CLI 凭据加载失败"));
  const data = await res.json() as { items?: CliCredentialConfig[] };
  return Array.isArray(data.items) ? data.items : [];
}

export async function fetchCliCredentialModels(
  cliTool: CliCredentialTool,
  providerId: string,
): Promise<CliModelList> {
  const params = new URLSearchParams({ providerId });
  const res = await fetch(`${API_BASE}/cli-credentials/${cliTool}/models?${params.toString()}`, {
    headers: cloudHeaders(),
  });
  if (!res.ok) throw new Error("加载模型列表失败");
  return await res.json() as CliModelList;
}

export async function saveCliCredential(
  cliTool: CliCredentialTool,
  input: CliCredentialUpdateInput,
): Promise<CliCredentialConfig> {
  const res = await fetch(`${API_BASE}/cli-credentials/${cliTool}`, {
    method: "PUT",
    headers: cloudJsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readApiError(res, "CLI 凭据保存失败"));
  return res.json();
}

export async function fetchAuditLogs(input: {
  projectId?: string | null;
  teamId?: string | null;
}): Promise<AuditLog[]> {
  const params = new URLSearchParams();
  if (input.projectId) params.set("projectId", input.projectId);
  if (input.teamId) params.set("teamId", input.teamId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${API_BASE}/audit-logs${suffix}`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch audit logs"));
  const data = await res.json() as { items?: AuditLog[] };
  return Array.isArray(data.items) ? data.items : [];
}

export async function fetchSessions(projectId?: string, includeArchived = false): Promise<Session[]> {
  const params = new URLSearchParams();
  if (projectId) params.set("projectId", projectId);
  if (includeArchived) params.set("includeArchived", "true");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${API_BASE}/sessions${suffix}`, { headers: cloudHeaders() });
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
    headers: cloudJsonHeaders(),
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
    headers: cloudJsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, { method: "DELETE", headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to delete session"));
}

export async function renameSession(sessionId: string, title: string): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH", headers: cloudJsonHeaders(),
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to rename session"));
  return res.json();
}

export async function pinSession(sessionId: string, isPinned: boolean): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ isPinned }),
  });
  if (!res.ok) throw new Error("Failed to update session pin");
  return res.json();
}

export async function archiveSession(sessionId: string, archived = true): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ archived }),
  });
  if (!res.ok) throw new Error("Failed to archive session");
  return res.json();
}

export async function muteSession(sessionId: string, isMuted: boolean): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ isMuted }),
  });
  if (!res.ok) throw new Error("Failed to update session mute");
  return res.json();
}

export async function markSessionRead(sessionId: string): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/read`, { method: "POST", headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to mark session read");
  return res.json();
}

export async function forwardMessages(
  messageIds: string[],
  targetSessionIds: string[],
): Promise<{ messages: Message[] }> {
  const res = await fetch(`${API_BASE}/sessions/forward`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ messageIds, targetSessionIds }),
  });
  if (!res.ok) throw new Error("Failed to forward messages");
  return res.json();
}

export async function fetchSessionMembers(sessionId: string): Promise<SessionMember[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/members`, { headers: cloudHeaders() });
  if (!res.ok) return [];
  return res.json();
}

export async function addGroupMember(sessionId: string, agentConfigId: string): Promise<SessionMember[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/members`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ agentConfigId }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to add group member"));
  return res.json();
}

export async function removeGroupMember(sessionId: string, agentConfigId: string): Promise<SessionMember[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/members/${encodeURIComponent(agentConfigId)}`, {
    method: "DELETE",
    headers: cloudHeaders(),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to remove group member"));
  return res.json();
}

export async function fetchMessages(sessionId: string): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}

export async function fetchRuns(sessionId: string): Promise<RunRead[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/runs`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to fetch runs");
  return res.json();
}

export async function cancelRun(runId: string, reason?: string): Promise<RunRead> {
  const res = await fetch(`${API_BASE}/runs/${runId}/cancel`, {
    method: "POST",
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ reason: reason ?? "" }),
  });
  if (!res.ok) throw new Error("Failed to cancel run");
  return res.json();
}

export async function fetchRunLogs(runId: string): Promise<RuntimeLogs> {
  const res = await fetch(`${API_BASE}/runs/${runId}/logs`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to fetch run logs"));
  return res.json();
}

export async function fetchRunTasks(runId: string): Promise<TaskRead[]> {
  const res = await fetch(`${API_BASE}/runs/${runId}/tasks`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to fetch run tasks");
  return res.json();
}

export async function fetchApprovals(sessionId: string): Promise<ApprovalCheckpoint[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/approvals`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to fetch approvals");
  return res.json();
}

export async function approveCheckpoint(
  checkpointId: string,
  input: { artifactId?: string | null; artifactVersion?: number | null; comment?: string | null } = {},
): Promise<ApprovalCheckpoint> {
  const res = await fetch(`${API_BASE}/approvals/${checkpointId}/approve`, {
    method: "POST",
    headers: cloudJsonHeaders(),
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
    headers: cloudJsonHeaders(),
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
  attachmentIds?: string[],
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
    if (attachmentIds && attachmentIds.length > 0) body.attachmentIds = attachmentIds;
    if (chainConfig) {
      body.chainConfig = {
        chainName: chainConfig.chainName,
        agentOrder: chainConfig.agentOrder,
      };
    }
    const response = await fetch(url, {
      method: "POST",
      headers: cloudJsonHeaders(),
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
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Failed to reply to message");
  return res.json();
}

export async function pinMessage(messageId: string): Promise<{ isPinned: boolean }> {
  const res = await fetch(`${API_BASE}/messages/${messageId}/pin`, { method: "POST", headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to pin message");
  return res.json();
}

export async function unpinMessage(messageId: string): Promise<{ isPinned: boolean }> {
  const res = await fetch(`${API_BASE}/messages/${messageId}/pin`, { method: "DELETE", headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to unpin message");
  return res.json();
}

export async function searchMessages(
  sessionId: string,
  query: string,
  limit = 20,
): Promise<Message[]> {
  const params = new URLSearchParams({ session_id: sessionId, q: query, limit: String(limit) });
  const res = await fetch(`${API_BASE}/messages/search?${params.toString()}`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to search messages");
  return res.json();
}

export async function fetchMessage(messageId: string): Promise<Message> {
  const res = await fetch(`${API_BASE}/messages/${messageId}`, { headers: cloudHeaders() });
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
      headers: cloudHeaders(),
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
    previewKind: typeof raw.previewKind === "string" ? raw.previewKind : undefined,
    previewLabel: typeof raw.previewLabel === "string" ? raw.previewLabel : null,
    mediaType: typeof raw.mediaType === "string" ? raw.mediaType : null,
    fileExtension: typeof raw.fileExtension === "string" ? raw.fileExtension : null,
    canInlinePreview: typeof raw.canInlinePreview === "boolean" ? raw.canInlinePreview : undefined,
    isBinary: typeof raw.isBinary === "boolean" ? raw.isBinary : undefined,
    rawUrl: typeof raw.rawUrl === "string" ? raw.rawUrl : null,
    downloadUrl: typeof raw.downloadUrl === "string" ? raw.downloadUrl : null,
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
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/artifacts`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to fetch artifacts");
  return res.json();
}

export async function fetchArtifactVersions(artifactId: string): Promise<ArtifactVersion[]> {
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/versions`, { headers: cloudHeaders() });
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
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/diff?${params.toString()}`, { headers: cloudHeaders() });
  if (!res.ok) throw new Error("Failed to fetch artifact diff");
  return res.json();
}

export async function editArtifact(
  artifactId: string,
  data: ArtifactEditRequest,
): Promise<ArtifactEditResult> {
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/edit`, {
    method: "POST",
    headers: cloudJsonHeaders(),
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
    headers: cloudJsonHeaders(),
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
    headers: cloudJsonHeaders(),
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
    headers: cloudJsonHeaders(),
    body: JSON.stringify({ force }),
  });
  if (!res.ok) throw new Error("Failed to scan message artifacts");
  return res.json();
}
