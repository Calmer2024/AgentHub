import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AgentCliForm } from "./AgentCliForm";
import type { AgentConfig } from "../types";

vi.mock("../api/client", () => ({
  fetchSkills: vi.fn().mockResolvedValue([]),
  fetchCodexLocalConfig: vi.fn().mockResolvedValue({
    connection: "proxy",
    baseUrl: "",
    model: "",
    providerId: "agenthub_proxy",
    providerName: "AgentHub Codex Proxy",
    authMode: "api_key",
    message: "ready",
    ready: true,
    apiKeySet: false,
  }),
  updateCodexLocalConfig: vi.fn().mockResolvedValue({
    message: "ready",
    ready: true,
    apiKeySet: false,
  }),
  checkAgentExecutable: vi.fn(),
}));

const existingAgent: AgentConfig = {
  id: "agent-1",
  name: "已有 Agent",
  description: "",
  systemPrompt: "",
  rules: "",
  agentType: "cli_wrapper",
  cliTool: "custom",
  executable: "echo",
  initArgs: [],
  envVars: {},
  toolset: [],
  primarySkill: "general_coding",
  auxiliarySkills: [],
  contextPolicy: "workspace_coding",
  avatar: "preset:blue",
  status: "ready",
  isActive: true,
  createdAt: "",
  updatedAt: "",
};

describe("AgentCliForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("添加 Agent 时可从内置模板预填并保存", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<AgentCliForm onSave={onSave} onCancel={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /前端工程师/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: "前端工程师",
      cliTool: "codex",
      executable: "codex",
      toolset: ["react_typescript", "state_management", "responsive_ui"],
      contextPolicy: "workspace_coding",
      avatar: "preset:blue",
    }));
    expect(onSave.mock.calls[0][0].systemPrompt).toContain("内置模板「前端工程师」");
  });

  it("编辑已有 Agent 时不展示模板区", () => {
    render(<AgentCliForm initial={existingAgent} onSave={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /产品经理/ })).not.toBeInTheDocument();
  });
});
