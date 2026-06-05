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
  timestamp: string;
}

export interface ExecutionTrace {
  status: "running" | "completed" | "error";
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
  createdAt: string;
  updatedAt: string;
}

export interface Project {
  id: string;
  name: string;
  workspacePath: string;
  status: "creating" | "ready" | "building" | "error" | "archived";
  fileCount: number;
  totalSizeBytes: number;
  createdAt: string;
}

export interface ProjectCreateInput {
  name: string;
  workspacePath?: string;
  folderToken?: string;
}

export interface ProjectUpdateInput {
  name?: string;
}

export interface ProjectDeleteResult {
  status: "deleted";
  filesDeleted: boolean;
  workspacePath: string;
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
  metadata?: (Record<string, unknown> & { executionTrace?: ExecutionTrace }) | null;
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
  agentType: "cli_wrapper";
  cliTool: "claude_code" | "codex" | "opencode" | "custom";
  executable: string | null;
  initArgs: string[];
  envVars: Record<string, string>;
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
  agentType?: "cli_wrapper";
  cliTool?: "claude_code" | "codex" | "opencode" | "custom";
  executable?: string | null;
  initArgs?: string[];
  envVars?: Record<string, string>;
}

export interface AgentConfigUpdate {
  name?: string;
  description?: string;
  systemPrompt?: string;
  agentType?: "cli_wrapper";
  cliTool?: "claude_code" | "codex" | "opencode" | "custom";
  executable?: string | null;
  initArgs?: string[];
  envVars?: Record<string, string>;
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
  createdAt: string;
}

export interface PreviewResult {
  previewId: string;
  previewUrl: string;
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

// === Orchestrator / Collaboration types ===

export interface RouteAgent {
  id: string;
  name: string;
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
