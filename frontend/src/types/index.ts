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
  agentName: string | null;
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
}

export interface Artifact {
  id: string;
  sessionId: string;
  messageId: string;
  type: "code_diff" | "web_preview" | "document";
  title: string;
  content: string;
  status: "rendering" | "ready" | "error";
  createdAt: string;
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
}
