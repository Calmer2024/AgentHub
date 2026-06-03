export interface ReplyReference {
  id: string;
  role?: "user" | "assistant" | "system";
  content: string;
  agentName?: string | null;
  sourceName?: string | null;
  createdAt?: string;
}

export interface Session {
  id: string;
  title: string;
  agentConfigId: string | null;
  mode: string;
  createdAt: string;
  updatedAt: string;
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
  metadata?: Record<string, unknown> | null;
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
  provider: string;
  model: string;
  temperature: number;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AgentConfigCreate {
  name: string;
  description?: string;
  systemPrompt?: string;
  provider?: string;
  model?: string;
  temperature?: number;
}

export interface AgentConfigUpdate {
  name?: string;
  description?: string;
  systemPrompt?: string;
  provider?: string;
  model?: string;
  temperature?: number;
}

export interface Provider {
  name: string;
  displayName: string;
  provider: string;
  isAvailable: boolean;
  unavailableReason?: string;
  models: string[];
  defaultModel: string;
  capability: {
    supportsStreaming: boolean;
    supportsFileInput: boolean;
    supportsToolCall: boolean;
    maxContextTokens: number;
    tags: string[];
  };
}

export interface Settings {
  anthropicApiKey: string | null;
  deepseekApiKey: string | null;
  geminiApiKey: string | null;
  openaiApiKey: string | null;
  minimaxApiKey: string | null;
  glmApiKey: string | null;
  openaiModel: string;
  claudeModel: string;
  deepseekModel: string;
  geminiModel: string;
  minimaxModel: string;
  glmModel: string;
  orchestratorProvider: string;
  orchestratorModel: string;
}

export interface Artifact {
  id: string;
  sessionId: string;
  messageId: string;
  type: "code_diff" | "web_preview" | "document";
  title: string;
  content: string;
  status: "rendering" | "ready" | "error";
  version: number;
  parentArtifactId?: string | null;
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
