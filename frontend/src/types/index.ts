export interface ReplyReference {
  id: string;
  role?: "user" | "assistant" | "system";
  content: string;
  agentName?: string | null;
  sourceName?: string | null;
  createdAt?: string;
}

export interface CodeReference {
  artifactId?: string | null;
  projectId?: string | null;
  filePath?: string | null;
  title?: string | null;
  language?: string | null;
  startLine?: number | null;
  endLine?: number | null;
  content: string;
}

export interface ExecutionTraceItem {
  id: string;
  kind: "process" | "progress" | "tool" | "command" | "file" | "artifact" | "prompt" | "error" | "info";
  text: string;
  title?: string | null;
  detail?: string | null;
  summary?: string | null;
  action?: string | null;
  target?: string | null;
  command?: string | null;
  toolName?: string | null;
  provider?: string | null;
  level?: "info" | "success" | "warning" | "error" | string | null;
  status?: string | null;
  exitCode?: number | null;
  output?: string | null;
  stderr?: string | null;
  raw?: string | null;
  source?: "system" | "cli" | "adapter";
  chunkType?: string | null;
  processId?: string | null;
  persistentProcess?: boolean | null;
  reused?: boolean | null;
  recovered?: boolean | null;
  engineSessionMode?: string | null;
  engineSessionId?: string | null;
  pid?: number | null;
  timestamp: string;
}

export interface ExecutionTrace {
  status: "running" | "completed" | "error" | "cancelled";
  agentName?: string | null;
  cliTool?: string | null;
  workspacePath?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  processId?: string | null;
  exitCode?: number | null;
  items: ExecutionTraceItem[];
}

export interface Session {
  id: string;
  title: string;
  projectId: string | null;
  agentConfigId: string | null;
  mode: string;
  isPinned?: boolean;
  archivedAt?: string | null;
  unreadCount?: number;
  lastReadAt?: string | null;
  isMuted?: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface SessionMember {
  agentConfigId: string;
  agentName: string;
  joinedAt: string;
}

export interface Project {
  id: string;
  name: string;
  workspacePath?: string | null;
  workspaceMode: "local" | "cloud";
  workspaceId?: string | null;
  teamId?: string | null;
  status: "creating" | "ready" | "building" | "error" | "archived";
  fileCount: number;
  totalSizeBytes: number;
  createdAt: string;
}

export interface ProjectCreateInput {
  name: string;
  workspacePath?: string;
  folderToken?: string;
  workspaceMode?: "local" | "cloud";
  teamId?: string | null;
  template?: string | null;
}

export interface ProjectUpdateInput {
  name?: string;
}

export interface ProjectDeleteResult {
  status: "deleted";
  filesDeleted: boolean;
  workspacePath?: string | null;
}

export interface FolderPickResult {
  workspacePath: string;
  folderName: string;
  folderToken: string;
}

export interface Message {
  id: string;
  sessionId: string;
  role: "user" | "assistant" | "system";
  content: string;
  contentType?: string;
  agentName: string | null;
  sourceType?: "user" | "agent" | "orchestrator" | "assistant" | "system";
  sourceId?: string | null;
  sourceName?: string | null;
  metadata?: (Record<string, unknown> & {
    executionTrace?: ExecutionTrace;
    orchestratorPlan?: OrchestratorPlanMetadata;
    orchestratorPlanError?: string;
    orchestratorExecution?: OrchestratorExecution;
  }) | null;
  agentRole?: string | null;
  phase?: number | null;
  taskName?: string | null;
  isCollaborating?: boolean;
  parentMessageId?: string | null;
  isPinned?: boolean;
  highlight?: string | null;
  createdAt: string;
}

export interface AgentConfig {
  id: string;
  name: string;
  description: string;
  systemPrompt: string;
  rules: string;
  agentType: "cli_wrapper";
  cliTool: "claude_code" | "codex" | "opencode" | "custom";
  executable: string | null;
  initArgs: string[];
  envVars: Record<string, string>;
  toolset: string[];
  primarySkill: string;
  auxiliarySkills: string[];
  contextPolicy: string;
  avatar: string;
  status: "ready" | "not_found" | "running" | "error";
  version?: string | null;
  executablePath?: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AgentConfigCreate {
  name: string;
  description?: string;
  systemPrompt?: string;
  rules?: string;
  agentType?: "cli_wrapper";
  cliTool?: "claude_code" | "codex" | "opencode" | "custom";
  executable?: string | null;
  initArgs?: string[];
  envVars?: Record<string, string>;
  toolset?: string[];
  primarySkill?: string;
  auxiliarySkills?: string[];
  contextPolicy?: string;
  avatar?: string;
}

export interface AgentConfigUpdate {
  name?: string;
  description?: string;
  systemPrompt?: string;
  rules?: string;
  agentType?: "cli_wrapper";
  cliTool?: "claude_code" | "codex" | "opencode" | "custom";
  executable?: string | null;
  initArgs?: string[];
  envVars?: Record<string, string>;
  toolset?: string[];
  primarySkill?: string;
  auxiliarySkills?: string[];
  contextPolicy?: string;
  avatar?: string;
}

export interface SkillDefinition {
  id: string;
  name: string;
  description: string;
  tags: string[];
  source?: "builtin" | "filesystem" | string;
  path?: string | null;
}

export interface CodexLocalConfig {
  codexHome: string;
  configExists: boolean;
  envExists: boolean;
  connection: "official" | "proxy" | "inherit" | "auto" | string;
  providerId: string;
  providerName: string;
  baseUrl: string;
  model: string;
  wireApi: string;
  authMode: string;
  envKey: string;
  apiKeySet: boolean;
  apiKeySource: string;
  hasChatgptAuth: boolean;
  needsApiKey: boolean;
  repairApplied: boolean;
  ready: boolean;
  message: string;
}

export interface CodexLocalConfigUpdate {
  connection: "official" | "proxy";
  baseUrl: string;
  model?: string;
  apiKey?: string;
  providerId?: string;
  providerName?: string;
  useChatgptAuth?: boolean;
}

export interface Artifact {
  id: string;
  sessionId: string;
  messageId: string;
  projectId?: string | null;
  type: "code_diff" | "web_preview" | "document" | "file_tree";
  title: string;
  content: string;
  status: "rendering" | "ready" | "error";
  version: number;
  parentArtifactId?: string | null;
  filePath?: string | null;
  previewId?: string | null;
  source?: string | null;
  previewKind?: "html" | "markdown" | "pdf" | "image" | "presentation" | "word" | "spreadsheet" | "text" | "diff" | "file_tree" | string;
  previewLabel?: string | null;
  mediaType?: string | null;
  fileExtension?: string | null;
  canInlinePreview?: boolean;
  isBinary?: boolean;
  rawUrl?: string | null;
  downloadUrl?: string | null;
  createdAt: string;
}

export interface PreviewResult {
  previewId: string;
  previewUrl: string;
}

export type BuildStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface BuildRun {
  id: string;
  projectId: string;
  status: BuildStatus | string;
  command: string;
  installCommand?: string | null;
  artifactPath?: string | null;
  exitCode?: number | null;
  errorSummary?: string | null;
  createdAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
}

export interface BuildList {
  items: BuildRun[];
}

export interface BuildQueuedResult {
  buildId: string;
  status: BuildStatus | string;
}

export interface BuildLogChunk {
  sequence: number;
  stream: "stdout" | "stderr" | string;
  text: string;
  createdAt: string;
}

export interface BuildLogs {
  chunks: BuildLogChunk[];
}

export interface ProjectPreviewResult {
  previewId: string;
  url: string;
  source: "workspace" | "build" | string;
}

export type PreviewSource = "static" | "build" | "dev_server";
export type DeliveryVisibility = "public" | "team" | "private";

export interface PreviewSession {
  id: string;
  artifactId: string;
  artifactVersionId?: string | null;
  projectId: string;
  source: PreviewSource | string;
  status: "ready" | "revoked" | "expired" | string;
  url: string;
  visibility: DeliveryVisibility | string;
  expiresAt: string;
  createdAt: string;
  revokedAt?: string | null;
}

export interface DeploymentLogChunk {
  sequence: number;
  stream: "system" | "stdout" | "stderr" | string;
  text: string;
  createdAt: string;
}

export interface DeploymentLogs {
  deploymentId: string;
  chunks: DeploymentLogChunk[];
}

export interface Deployment {
  id: string;
  projectId: string;
  artifactId: string;
  artifactVersionId: string;
  target: "static_hosting" | "third_party" | string;
  status: "queued" | "building" | "published" | "failed" | "rolled_back" | string;
  stage: string;
  url?: string | null;
  visibility: DeliveryVisibility | string;
  errorSummary?: string | null;
  createdBy?: string | null;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string | null;
}

export interface Comment {
  id: string;
  projectId: string;
  targetType: "message" | "artifact" | "deployment" | string;
  targetId: string;
  authorUserId: string;
  body: string;
  createdAt: string;
  updatedAt: string;
}

export interface Attachment {
  id: string;
  projectId: string;
  sessionId?: string | null;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  storageUri: string;
  createdAt: string;
}

export interface ArtifactReference {
  id: string;
  sourceType: string;
  sourceId: string;
  artifactId: string;
  artifactVersionId?: string | null;
  relation: string;
  createdAt: string;
}

export interface Notification {
  id: string;
  type: string;
  resourceType: string;
  resourceId: string;
  title: string;
  body?: string | null;
  readAt?: string | null;
  createdAt: string;
}

export interface MobileSessionSummary {
  id: string;
  projectId?: string | null;
  title: string;
  unreadCount: number;
  latestMessageAt?: string | null;
  pendingApprovalCount: number;
}

export interface RenderedArtifact {
  artifactId: string;
  format: "html" | "pdf" | "image" | string;
  renderId: string;
  content: string;
  fileName: string;
  previewKind?: string;
  mediaType?: string | null;
  rawUrl?: string | null;
  downloadUrl?: string | null;
}

export interface AgentTemplateSession {
  id: string;
  status: string;
  draft: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface GitSyncJob {
  id: string;
  projectId: string;
  mode: "pull" | "push" | string;
  remote: string;
  branch: string;
  status: "completed" | "failed" | string;
  commitSha?: string | null;
  errorSummary?: string | null;
  logs: string[];
  createdAt: string;
}

export type ProductEdition = "local" | "saas";
export type AppSurface = "desktop" | "mobile";

export type FeatureKey =
  | "localWorkspace"
  | "localCliRuntime"
  | "localPreview"
  | "localBuildExport"
  | "cloudWorkspace"
  | "teamSpaces"
  | "cloudPreview"
  | "deployment"
  | "auditLogs"
  | "notifications"
  | "mobileApprovals";

export type RuntimeFeatureFlags = Record<FeatureKey, boolean>;

export interface RuntimeCapabilities {
  edition: ProductEdition;
  surface: AppSurface;
  authRequired: boolean;
  apiBaseUrl: string;
  features: RuntimeFeatureFlags;
  limits: {
    maxUploadBytes?: number;
  };
}

export interface ShellContextValue {
  capabilities: RuntimeCapabilities;
  edition: ProductEdition;
  surface: AppSurface;
}

export type TeamRole = "owner" | "admin" | "member" | "viewer";

export interface CurrentUser {
  id: string;
  email: string;
  username?: string | null;
  displayName: string;
  avatarUrl?: string | null;
  status?: string;
  lastLoginAt?: string | null;
  teams?: Team[];
  defaultSpace?: {
    kind: "personal" | "team";
    id: string;
    name: string;
  };
  createdAt: string;
}

export interface AuthProvider {
  id: string;
  label: string;
  type: "email" | "password" | "external" | "dev_header";
  enabled: boolean;
  devOnly: boolean;
}

export interface AuthSession {
  accessToken: string;
  refreshToken: string;
  tokenType: "bearer";
  expiresAt: string;
  user: CurrentUser;
}

export type CliCredentialTool = "claude_code" | "codex" | "opencode";
export type CliCredentialProviderType = "official" | "proxy" | "cc_switch" | "custom";

export interface CliCredentialConfig {
  cliTool: CliCredentialTool;
  scope: "user" | "team" | "project" | string;
  ownerId: string;
  providerType: CliCredentialProviderType | string;
  providerId: string;
  providerName: string;
  baseUrl?: string | null;
  model?: string | null;
  authEnvKey: string;
  configured: boolean;
  secretNames: string[];
  config?: Record<string, unknown>;
  updatedAt?: string | null;
}

export interface CliCredentialUpdateInput {
  scope?: "user" | "team" | "project";
  ownerId?: string | null;
  providerType?: CliCredentialProviderType;
  providerId?: string | null;
  providerName?: string | null;
  baseUrl?: string | null;
  model?: string | null;
  authEnvKey?: string | null;
  apiKey?: string | null;
  config?: Record<string, unknown>;
}

export interface CliModelOption {
  id: string;
  name: string;
  label: string;
  providerId: string;
  reasoning: boolean;
  toolCall: boolean;
  context?: number | null;
  output?: number | null;
  lastUpdated?: string | null;
}

export interface CliModelList {
  cliTool: CliCredentialTool;
  providerId: string;
  source: string;
  items: CliModelOption[];
}

export interface Team {
  id: string;
  name: string;
  role: TeamRole;
  memberCount: number;
  createdAt: string;
}

export interface TeamMember {
  id: string;
  teamId: string;
  userId: string;
  email: string;
  displayName: string;
  role: TeamRole;
  createdAt: string;
}

export interface WorkspaceSnapshot {
  id: string;
  workspaceId: string;
  label?: string | null;
  storageUri: string;
  createdBy?: string | null;
  createdAt: string;
}

export interface WorkspaceImport {
  id: string;
  workspaceId: string;
  source: "zip" | "github";
  status: string;
  detail: string;
  metadata: Record<string, unknown>;
  createdBy?: string | null;
  createdAt: string;
  completedAt?: string | null;
}

export interface WorkspaceRestore {
  id: string;
  workspaceId: string;
  snapshotId: string;
  strategy: "replace" | "branch";
  status: string;
  createdAt: string;
  completedAt?: string | null;
}

export interface CloudWorkspace {
  id: string;
  projectId: string;
  provider: string;
  status: string;
  storageUri: string;
  snapshots: WorkspaceSnapshot[];
  imports: WorkspaceImport[];
  restores: WorkspaceRestore[];
  createdAt: string;
  updatedAt: string;
}

export type RuntimeMode = "local" | "cloud";

export interface Sandbox {
  id: string;
  workspaceId: string;
  status: "creating" | "provisioning" | "ready" | "running" | "syncing" | "stopping" | "stopped" | "disposed" | "failed" | string;
  image: string;
  runnerNodeId?: string | null;
  provider?: string | null;
  externalId?: string | null;
  region?: string | null;
  resourceLimits: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
  stoppedAt?: string | null;
  disposedAt?: string | null;
}

export interface RuntimeImage {
  id: string;
  label: string;
  image: string;
  provider: string;
  default: boolean;
  tools: string[];
  createdAt?: string | null;
}

export interface RunnerNode {
  id: string;
  provider: string;
  region?: string | null;
  status: string;
  capacity: Record<string, unknown>;
  lastHeartbeatAt?: string | null;
  createdAt: string;
}

export interface QuotaSummary {
  subjectType: string;
  subjectId: string;
  concurrentRunsLimit: number;
  concurrentRunsUsed: number;
  runtimeSecondsLimit: number;
  memoryMbLimit: number;
  diskMbLimit: number;
  network: string;
}

export interface SecretCreateInput {
  name: string;
  value: string;
  scope?: "user" | "team" | "project";
  ownerId?: string | null;
}

export interface SecretRef {
  id: string;
  name: string;
  scope: string;
  ownerId: string;
  createdAt: string;
}

export interface RuntimeLogChunk {
  sequence: number;
  stream: "stdout" | "stderr" | "system" | string;
  text: string;
  createdAt: string;
}

export interface RuntimeLogs {
  runId: string;
  chunks: RuntimeLogChunk[];
}

export interface AuditLog {
  id: string;
  actorUserId?: string | null;
  teamId?: string | null;
  projectId?: string | null;
  action: string;
  resourceType: string;
  resourceId: string;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface ArtifactVersion {
  id: string;
  version: number;
  content: string;
  createdAt: string;
}

export interface ArtifactDiff {
  fromVersion: number;
  toVersion: number;
  diff: string;
  oldContent: string;
  newContent: string;
}

export interface ArtifactEditRequest {
  selection: string;
  instruction: string;
  editType?: "replace" | "insert_after" | "insert_before" | "delete";
  apply?: boolean;
  proposedContent?: string;
}

export interface ArtifactEditResult {
  newVersion: number | null;
  diff: ArtifactDiff;
  artifact: Artifact | null;
  proposedContent: string;
  strategy: string;
}

export interface WorkspaceFile {
  path: string;
  content: string;
  size: number;
}

export interface ArtifactCandidate {
  artifactType: Artifact["type"];
  title: string;
  source: string;
  confidence: number;
  reason: string;
  contentPreview: string;
}

export interface ArtifactScanResult {
  created: Artifact[];
  candidates: ArtifactCandidate[];
  skipped: Array<{
    reason: string;
    artifactId?: string | null;
    title?: string | null;
    detail?: string | null;
  }>;
}

export type RunStatus = "queued" | "running" | "pausing" | "paused" | "cancelling" | "cancelled" | "completed" | "failed";
export type TaskStatus = "pending" | "running" | "paused" | "completed" | "failed" | "cancelled" | "rejected";

export interface RunRead {
  id: string;
  sessionId: string;
  projectId?: string | null;
  mode: "single" | "group" | "orchestrated" | string;
  status: RunStatus;
  currentMessageId?: string | null;
  startedAt: string;
  updatedAt: string;
  completedAt?: string | null;
  cancelReason?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface TaskRead {
  id: string;
  runId: string;
  sessionId: string;
  agentId?: string | null;
  messageId?: string | null;
  name: string;
  role?: string | null;
  phase?: number | null;
  status: TaskStatus;
  dependsOn: string[];
  startedAt?: string | null;
  completedAt?: string | null;
  metadata?: Record<string, unknown> | null;
}

export type ApprovalStatus = "pending_review" | "approved" | "rejected";

export interface ApprovalCheckpoint {
  id: string;
  runId: string;
  taskId: string;
  sessionId: string;
  messageId?: string | null;
  artifactId?: string | null;
  artifactVersion?: number | null;
  title: string;
  summary: string;
  status: ApprovalStatus;
  reason?: string | null;
  createdAt: string;
  decidedAt?: string | null;
  metadata?: Record<string, unknown> | null;
}

export type HealthStatus = "ok" | "warning" | "error" | "missing";
export type HealthSeverity = "info" | "warning" | "blocking";

export interface SystemHealthItem {
  key: string;
  label: string;
  status: HealthStatus;
  severity: HealthSeverity;
  detail: string;
  action?: {
    label: string;
    target: "agent_panel" | "project_settings" | "docs" | "retry";
  } | null;
  metadata?: Record<string, string | number | boolean | null> | null;
}

export interface SystemHealthRead {
  overall: "ok" | "warning" | "error";
  checkedAt: string;
  projectId?: string | null;
  sessionId?: string | null;
  blockingReasons: string[];
  items: SystemHealthItem[];
}

// === Orchestrator / Collaboration types ===

export interface RouteAgent {
  id: string;
  name: string;
}

export type StewardRouteType = "context_only" | "single_agent" | "mini_collab" | "draft_plan";

export interface StewardDecisionEvent {
  routeType: StewardRouteType;
  confidence: number;
  reason: string;
  selectedAgents: RouteAgent[];
  taskBrief: string;
  requiresApproval: boolean;
  riskLevel: "low" | "medium" | "high";
  intent: string;
  requiredTags: string[];
}

export interface CollabTask {
  name: string;
  role: string;
  agent: string;
  agentId?: string;
  status: "pending" | "running" | "completed" | "error";
  dependsOn?: string[];
  phase?: number;
  summary?: string;
}

export interface DAGPhase {
  phase: number;
  mode: "serial" | "parallel";
  status: "pending" | "running" | "completed" | "error";
  tasks: CollabTask[];
}

export interface ChainStep {
  step: number;
  agent: string;
  role: string;
  total: number;
  status: "running" | "completed" | "interrupted";
}

export interface DraftOrchestratorPlan {
  ok: boolean;
  rawOutput?: string;
  normalizedPlan?: Record<string, unknown>;
  validation?: {
    ok: boolean;
    errors: string[];
    warnings: string[];
  };
  visualization?: {
    mermaid: string;
  };
  error?: string;
}

export interface PhaseChangeEvent {
  phase: number;
  status: "pending" | "running" | "completed" | "error";
  agents: string[];
  tasks: string[];
}

export interface AgentStartEvent {
  agentId: string;
  agentName: string;
  messageId: string;
  role?: string;
  phase?: number;
  task?: string;
  callKey?: string;
}

export interface InteractivePrompt {
  sessionId: string;
  agentId: string;
  agentName: string;
  messageId: string;
  processId: string;
  content: string;
  promptType: "confirm";
}

export interface OrchestratorSummaryStartEvent {
  messageId: string;
  sourceType: "orchestrator";
  sourceId?: string;
  sourceName: string;
  contentType: "orchestrator_summary";
  metadata?: Record<string, unknown>;
}

export interface ChainConfigInput {
  chainName?: string;
  agentOrder?: string[];
}

export interface OrchestratorPlanMetadata {
  ok: boolean;
  normalizedPlan: OrchestratorPlan;
  validation: OrchestratorValidation;
  visualization: {
    mermaid: string;
  };
}

export interface SettingsUpdate {
  anthropicApiKey?: string;
  deepseekApiKey?: string;
  geminiApiKey?: string;
  openaiApiKey?: string;
  minimaxApiKey?: string;
  glmApiKey?: string;
  openaiModel?: string;
  claudeModel?: string;
  deepseekModel?: string;
  geminiModel?: string;
  minimaxModel?: string;
  glmModel?: string;
  orchestratorProvider?: string;
  orchestratorModel?: string;
}

// === Orchestrator Manual Bridge Debug types ===

export interface OrchestratorDebugAgent {
  id: string;
  name: string;
  description: string;
  provider: string;
  model: string;
  toolset?: string[];
  primarySkill?: string;
  auxiliarySkills?: string[];
}

export interface OrchestratorAgentProfile {
  id: string;
  name: string;
  engine: string;
  toolset: string[];
  primarySkill: string;
  auxiliarySkills: string[];
}

export interface OrchestratorPlanTask {
  task_id: string;
  title: string;
  goal: string;
  required_skills: string[];
  assigned_agent_id: string | null;
  assigned_agent_name: string | null;
  assignment_reason: string;
  depends_on: string[];
  expected_outputs: string[];
  acceptance_criteria: string[];
  needs_approval: boolean;
  is_blocking: boolean;
}

export interface OrchestratorPlanPhase {
  phase: number;
  mode: "serial" | "parallel";
  tasks: string[];
  reason: string;
}

export interface OrchestratorPlan {
  plan_id: string;
  status: string;
  execution_policy: string | {
    mode?: string;
    requires_approval_before_execution?: boolean;
  };
  tasks: OrchestratorPlanTask[];
  execution_strategy: {
    summary?: string;
    phases?: OrchestratorPlanPhase[];
    parallelizable_groups?: string[][];
    critical_path?: string[];
  };
}

export interface OrchestratorValidation {
  ok: boolean;
  errors: string[];
  warnings: string[];
}

export interface BuildOrchestratorInputRequest {
  content: string;
  agentIds?: string[];
  useMockAgents?: boolean;
}

export interface BuildOrchestratorInputResult {
  input: {
    content: string;
    agentCount: number;
  };
  orchestratorAgent: OrchestratorAgentProfile;
  candidateAgents: OrchestratorDebugAgent[];
  prompt: string;
  outputSchema: Record<string, unknown>;
}

export interface ParseOrchestratorOutputRequest {
  rawOutput: string;
  candidateAgents: OrchestratorDebugAgent[];
}

export interface ParseOrchestratorOutputResult {
  rawOutput: string;
  normalizedPlan: OrchestratorPlan;
  validation: OrchestratorValidation;
  visualization: {
    mermaid: string;
  };
}

export interface GenerateOrchestratorPlanRequest extends BuildOrchestratorInputRequest {
  provider?: string;
  model?: string;
}

export interface GenerateOrchestratorPlanResult
  extends BuildOrchestratorInputResult, ParseOrchestratorOutputResult {
  llm: {
    provider: string;
    model: string;
  };
}

export interface OrchestratorExecutionTask {
  taskId: string;
  title: string;
  goal: string;
  status: "pending" | "running" | "completed" | "failed" | "error" | "cancelled" | string;
  startedAt?: string | null;
  completedAt?: string | null;
  updatedAt?: string | null;
  summary?: string | null;
  runnerType?: "mock" | "cli" | string;
  visibleMessageId?: string | null;
  assignedAgentId?: string | null;
  assignedAgentName?: string | null;
  dependsOn: string[];
  requiredSkills: string[];
  needsApproval: boolean;
  isBlocking: boolean;
  expectedOutputs: string[];
  acceptanceCriteria: string[];
}

export interface OrchestratorExecutionEvent {
  type: string;
  status: string;
  timestamp: string;
  message: string;
  phase?: number;
  taskId?: string;
  taskIds?: string[];
  remainingTaskIds?: string[];
}

export interface OrchestratorExecution {
  executionId: string;
  sessionId: string;
  planId: string;
  runId?: string | null;
  status: "pending" | "running" | "completed" | "failed" | "error" | "cancelling" | "cancelled" | string;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  tasks: OrchestratorExecutionTask[];
  events: OrchestratorExecutionEvent[];
  validation: OrchestratorValidation;
  plan?: OrchestratorPlan;
}
