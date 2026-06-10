import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AgentCliForm } from "./AgentCliForm";
import type { AgentConfig } from "../types";

const apiMocks = vi.hoisted(() => ({
  fetchSkills: vi.fn().mockResolvedValue([]),
  fetchCliCredentials: vi.fn().mockResolvedValue([
    {
      cliTool: "codex",
      scope: "user",
      ownerId: "u1",
      providerType: "official",
      providerId: "openai",
      providerName: "OpenAI",
      baseUrl: "https://api.openai.com/v1",
      model: null,
      authEnvKey: "OPENAI_API_KEY",
      configured: false,
      secretNames: ["OPENAI_API_KEY"],
      updatedAt: null,
    },
  ]),
  fetchCliCredentialModels: vi.fn().mockResolvedValue({
    cliTool: "opencode",
    providerId: "deepseek",
    source: "models.dev",
    items: [
      {
        id: "deepseek-v4-pro",
        name: "DeepSeek V4 Pro",
        label: "DeepSeek V4 Pro",
        providerId: "deepseek",
        reasoning: true,
        toolCall: true,
        context: 1048576,
        output: 1048576,
        lastUpdated: "2026-04-24",
      },
    ],
  }),
  saveCliCredential: vi.fn().mockResolvedValue({
    cliTool: "codex",
    scope: "user",
    ownerId: "u1",
    providerType: "official",
    providerId: "openai",
    providerName: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    model: null,
    authEnvKey: "OPENAI_API_KEY",
    configured: true,
    secretNames: ["OPENAI_API_KEY"],
    updatedAt: "",
  }),
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

vi.mock("../api/client", () => apiMocks);

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
    apiMocks.fetchSkills.mockResolvedValue([]);
    apiMocks.fetchCliCredentials.mockResolvedValue([
      {
        cliTool: "codex",
        scope: "user",
        ownerId: "u1",
        providerType: "official",
        providerId: "openai",
        providerName: "OpenAI",
        baseUrl: "https://api.openai.com/v1",
        model: null,
        authEnvKey: "OPENAI_API_KEY",
        configured: false,
        secretNames: ["OPENAI_API_KEY"],
        updatedAt: null,
      },
    ]);
    apiMocks.saveCliCredential.mockResolvedValue({
      cliTool: "codex",
      scope: "user",
      ownerId: "u1",
      providerType: "official",
      providerId: "openai",
      providerName: "OpenAI",
      baseUrl: "https://api.openai.com/v1",
      model: null,
      authEnvKey: "OPENAI_API_KEY",
      configured: true,
      secretNames: ["OPENAI_API_KEY"],
      updatedAt: "",
    });
    apiMocks.fetchCliCredentialModels.mockResolvedValue({
      cliTool: "opencode",
      providerId: "deepseek",
      source: "models.dev",
      items: [
        {
          id: "deepseek-v4-pro",
          name: "DeepSeek V4 Pro",
          label: "DeepSeek V4 Pro",
          providerId: "deepseek",
          reasoning: true,
          toolCall: true,
          context: 1048576,
          output: 1048576,
          lastUpdated: "2026-04-24",
        },
      ],
    });
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

  it("切换到自定义 CLI 时默认使用自定义头像", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<AgentCliForm onSave={onSave} onCancel={vi.fn()} />);

    fireEvent.click(screen.getByLabelText("命令行类型"));
    fireEvent.click(screen.getByRole("option", { name: "自定义" }));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      cliTool: "custom",
      name: "Custom CLI",
      avatar: "preset:custom",
    }));
  });

  it("云端内置 Engine 在智能体设置里保存 CLI 凭据", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const codexEngine: AgentConfig = {
      ...existingAgent,
      id: "codex-engine",
      name: "Codex",
      description: "云端 Codex",
      cliTool: "codex",
      executable: null,
      avatar: "",
    };
    render(<AgentCliForm initial={codexEngine} runtimeScope="cloud" onSave={onSave} onCancel={vi.fn()} />);

    await screen.findByText("Engine 凭据");
    expect(screen.getByTestId("agent-cli-form-grid")).toHaveClass("grid");
    expect(screen.getByTestId("agent-cli-form-grid")).not.toHaveClass("lg:grid-cols-2");
    expect(screen.getAllByRole("heading", { level: 3 }).map((item) => item.textContent)).toEqual(["基础信息", "Engine 凭据"]);
    expect(screen.queryByText("身份与规则")).not.toBeInTheDocument();
    expect(screen.queryByText("能力配置")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("codex-api-key"), { target: { value: "codex-key" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(apiMocks.saveCliCredential).toHaveBeenCalledWith("codex", expect.objectContaining({
      scope: "user",
      providerType: "official",
      providerId: "OpenAI",
      providerName: "OpenAI",
      baseUrl: "https://api.openai.com/v1",
      authEnvKey: "OPENAI_API_KEY",
      apiKey: "codex-key",
    })));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: "Codex",
      cliTool: "codex",
      executable: "codex",
      initArgs: expect.arrayContaining(["exec", "--json", "-"]),
      envVars: {},
      avatar: "",
    }));
  });

  it("云端内置 Engine 即使显示名变化也保持上下排列", async () => {
    const codexEngine: AgentConfig = {
      ...existingAgent,
      id: "codex-engine",
      name: "Codex Engine",
      description: "云端 Codex",
      cliTool: "codex",
      executable: null,
      avatar: "",
    };
    render(<AgentCliForm initial={codexEngine} runtimeScope="cloud" onSave={vi.fn()} onCancel={vi.fn()} />);

    await screen.findByText("Engine 凭据");
    expect(screen.getByTestId("agent-cli-form-grid")).not.toHaveClass("lg:grid-cols-2");
    expect(screen.getAllByRole("heading", { level: 3 }).map((item) => item.textContent)).toEqual(["基础信息", "Engine 凭据"]);
  });

  it("云端 Codex 不再展示固定中转预设，统一走自定义 OpenAI 兼容中转", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const codexEngine: AgentConfig = {
      ...existingAgent,
      id: "codex-engine",
      name: "Codex",
      description: "云端 Codex",
      cliTool: "codex",
      executable: null,
      avatar: "",
    };
    render(<AgentCliForm initial={codexEngine} runtimeScope="cloud" onSave={onSave} onCancel={vi.fn()} />);

    await screen.findByText("Engine 凭据");
    fireEvent.click(screen.getByLabelText("Codex Provider"));
    expect(screen.queryByRole("option", { name: "聪明 AI 中转" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("option", { name: "自定义 OpenAI 兼容中转" }));
    fireEvent.change(screen.getByLabelText("Base URL"), { target: { value: "https://relay.example.com/v1" } });
    fireEvent.change(screen.getByLabelText("模型"), { target: { value: "relay-codex" } });
    fireEvent.change(screen.getByLabelText("codex-api-key"), { target: { value: "relay-key" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(apiMocks.saveCliCredential).toHaveBeenCalledWith("codex", expect.objectContaining({
      scope: "user",
      providerType: "proxy",
      providerId: "OpenAI",
      providerName: "OpenAI",
      baseUrl: "https://relay.example.com/v1",
      model: "relay-codex",
      authEnvKey: "OPENAI_API_KEY",
      apiKey: "relay-key",
      config: expect.objectContaining({
        wireApi: "responses",
        modelReasoningEffort: "xhigh",
        networkAccess: "enabled",
      }),
    })));
  });

  it("云端 Codex 自定义中转保存 config.toml 关键配置", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const codexEngine: AgentConfig = {
      ...existingAgent,
      id: "codex-engine",
      name: "Codex",
      description: "云端 Codex",
      cliTool: "codex",
      executable: null,
      avatar: "",
    };
    render(<AgentCliForm initial={codexEngine} runtimeScope="cloud" onSave={onSave} onCancel={vi.fn()} />);

    await screen.findByText("Engine 凭据");
    fireEvent.click(screen.getByLabelText("Codex Provider"));
    fireEvent.click(screen.getByRole("option", { name: "自定义 OpenAI 兼容中转" }));
    fireEvent.change(screen.getByLabelText("codex-api-key"), { target: { value: "custom-relay-key" } });
    fireEvent.change(screen.getByLabelText("Base URL"), { target: { value: "https://relay.example.com/v1" } });
    fireEvent.change(screen.getByLabelText("模型"), { target: { value: "relay-codex" } });
    fireEvent.change(screen.getByLabelText("review_model"), { target: { value: "relay-codex-review" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(apiMocks.saveCliCredential).toHaveBeenCalledWith("codex", expect.objectContaining({
      providerType: "proxy",
      providerId: "OpenAI",
      providerName: "OpenAI",
      baseUrl: "https://relay.example.com/v1",
      model: "relay-codex",
      authEnvKey: "OPENAI_API_KEY",
      apiKey: "custom-relay-key",
      config: expect.objectContaining({
        wireApi: "responses",
        reviewModel: "relay-codex-review",
        modelReasoningEffort: "xhigh",
        networkAccess: "enabled",
        disableResponseStorage: true,
      }),
    })));
  });

  it("云端 OpenCode 只通过厂商、模型和 API Key 生成真实 Provider 配置", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const openCodeEngine: AgentConfig = {
      ...existingAgent,
      id: "opencode-engine",
      name: "OpenCode",
      description: "云端 OpenCode",
      cliTool: "opencode",
      executable: null,
      avatar: "",
    };
    render(<AgentCliForm initial={openCodeEngine} runtimeScope="cloud" onSave={onSave} onCancel={vi.fn()} />);

    await screen.findByText("Engine 凭据");
    fireEvent.click(screen.getByLabelText("OpenCode Provider"));
    fireEvent.click(screen.getByRole("option", { name: "DeepSeek" }));
    await screen.findByText("模型目录：models.dev");
    fireEvent.click(screen.getByLabelText("OpenCode 模型"));
    fireEvent.click(screen.getByRole("option", { name: /DeepSeek V4 Pro/ }));
    fireEvent.change(screen.getByLabelText("opencode-api-key"), { target: { value: "deepseek-key" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(apiMocks.saveCliCredential).toHaveBeenCalledWith("opencode", expect.objectContaining({
      scope: "user",
      providerType: "proxy",
      providerId: "deepseek",
      providerName: "DeepSeek",
      baseUrl: "https://api.deepseek.com/v1",
      model: "deepseek-v4-pro",
      authEnvKey: "DEEPSEEK_API_KEY",
      apiKey: "deepseek-key",
    })));
    expect(apiMocks.fetchCliCredentialModels).toHaveBeenCalledWith("opencode", "deepseek");
  });

  it("云端 Engine 凭据阻止把 URL 当 API Key 保存", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const claudeEngine: AgentConfig = {
      ...existingAgent,
      id: "claude-engine",
      name: "Claude Code",
      description: "云端 Claude Code",
      cliTool: "claude_code",
      executable: null,
      avatar: "",
    };
    render(<AgentCliForm initial={claudeEngine} runtimeScope="cloud" onSave={onSave} onCancel={vi.fn()} />);

    await screen.findByText("Engine 凭据");
    fireEvent.change(screen.getByLabelText("claude_code-api-key"), {
      target: { value: "https://api.deepseek.com/anthropic" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(await screen.findByText("API Key 不能填写 URL，请填写供应商控制台生成的密钥")).toBeInTheDocument();
    expect(apiMocks.saveCliCredential).not.toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });
});
