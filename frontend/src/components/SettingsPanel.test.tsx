import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SettingsPanel } from "./SettingsPanel";
import type { Provider } from "../types";

const mockProviders: Provider[] = [
  { name: "openai", displayName: "GPT-4o", provider: "openai", isAvailable: false,
    models: ["gpt-4o", "gpt-4o-mini"], defaultModel: "gpt-4o",
    capability: { supportsStreaming: true, supportsFileInput: false, supportsToolCall: false, maxContextTokens: 128000, tags: [] } },
  { name: "deepseek", displayName: "DeepSeek V3", provider: "deepseek", isAvailable: true,
    models: ["deepseek-v4-flash"], defaultModel: "deepseek-v4-flash",
    capability: { supportsStreaming: true, supportsFileInput: false, supportsToolCall: false, maxContextTokens: 128000, tags: [] } },
];

vi.mock("../api/client", () => ({
  fetchSettings: vi.fn().mockResolvedValue({
    anthropicApiKey: null, deepseekApiKey: "sk-****", geminiApiKey: null,
    openaiApiKey: null, minimaxApiKey: null, glmApiKey: null,
    openaiModel: "gpt-4o", claudeModel: "claude-3-5-sonnet-20241022",
    deepseekModel: "deepseek-v4-flash", geminiModel: "gemini-3.5-flash",
    minimaxModel: "MiniMax-M2.7", glmModel: "glm-5.1",
  }),
  updateSettings: vi.fn().mockResolvedValue({}),
}));

describe("SettingsPanel", () => {
  it("显示供应商卡片", async () => {
    render(<SettingsPanel providers={mockProviders} onSaved={vi.fn()} />);
    expect(await screen.findByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Anthropic Claude")).toBeInTheDocument();
  });
});
