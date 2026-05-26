export interface Session {
  id: string;
  title: string;
  agentName: string;
  createdAt: string;
  updatedAt: string;
}

export interface Message {
  id: string;
  sessionId: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
}

export interface AgentCapability {
  supportsStreaming: boolean;
  supportsFileInput: boolean;
  supportsToolCall: boolean;
  maxContextTokens: number;
  tags: string[];
}

export interface Agent {
  name: string;
  displayName: string;
  provider: string;
  isAvailable: boolean;
  unavailableReason?: string;
  capability: AgentCapability;
}

export interface Settings {
  anthropicApiKey: string | null;
  deepseekApiKey: string | null;
  geminiApiKey: string | null;
}

export interface SettingsUpdate {
  anthropicApiKey?: string;
  deepseekApiKey?: string;
  geminiApiKey?: string;
}
