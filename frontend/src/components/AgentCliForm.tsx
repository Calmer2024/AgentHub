import {
  AlertCircle,
  CheckCircle2,
  CircleDot,
  KeyRound,
  Loader2,
  Network,
  Play,
  Save,
  ServerCog,
  Settings2,
  ShieldCheck,
  Sparkles,
  SlidersHorizontal,
  Terminal,
  Upload,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import type {
  AgentConfig,
  AgentConfigCreate,
  CliCredentialConfig,
  CliModelOption,
  CliCredentialProviderType,
  CliCredentialTool,
  SkillDefinition,
} from "../types";
import {
  checkAgentExecutable,
  fetchCliCredentials,
  fetchCliCredentialModels,
  fetchCodexLocalConfig,
  fetchSkills,
  saveCliCredential,
  updateCodexLocalConfig,
} from "../api/client";
import {
  CLI_PRESETS,
  isBlockedAgentEnvKey,
  type CliTool,
} from "./AgentCliPresets";
import { UiSelect, type UiSelectOption } from "./UiSelect";
import { AgentAvatar, AGENT_AVATAR_PRESETS, CUSTOM_AGENT_DEFAULT_AVATAR } from "./AgentAvatar";
import { AGENT_TEMPLATE_PRESETS, type AgentTemplatePreset } from "./AgentTemplatePresets";
import { GlobalModal } from "./GlobalModal";

const CLI_TOOL_OPTIONS: UiSelectOption[] = [
  { value: "claude_code", label: "Claude Code" },
  { value: "codex", label: "Codex" },
  { value: "opencode", label: "OpenCode" },
  { value: "custom", label: "自定义" },
];

const CONTEXT_POLICY_OPTIONS: UiSelectOption[] = [
  { value: "workspace_coding", label: "Workspace Coding", description: "读取项目上下文并允许工作区编辑" },
  { value: "planning_only", label: "Planning Only", description: "仅用于计划、拆解和调度" },
  { value: "review_only", label: "Review Only", description: "侧重审查、测试和验收" },
];

const CODEX_CONNECTION_OPTIONS: UiSelectOption[] = [
  { value: "proxy", label: "OpenAI 兼容中转 API" },
  { value: "official", label: "官方 OpenAI API" },
];

const CLOUD_CLI_CREDENTIAL_META: Record<CliCredentialTool, {
  label: string;
  defaultProviderType: CliCredentialProviderType;
  defaultProviderId: string;
  defaultProviderName: string;
  defaultBaseUrl: string;
  defaultAuthEnvKey: string;
  apiKeyLabel: string;
  apiKeyPlaceholder: string;
}> = {
  claude_code: {
    label: "Claude Code",
    defaultProviderType: "official",
    defaultProviderId: "anthropic",
    defaultProviderName: "Anthropic",
    defaultBaseUrl: "",
    defaultAuthEnvKey: "ANTHROPIC_API_KEY",
    apiKeyLabel: "Anthropic / 中转密钥",
    apiKeyPlaceholder: "填写 Anthropic 或中转服务 API Key",
  },
  codex: {
    label: "Codex",
    defaultProviderType: "official",
    defaultProviderId: "OpenAI",
    defaultProviderName: "OpenAI",
    defaultBaseUrl: "https://api.openai.com/v1",
    defaultAuthEnvKey: "OPENAI_API_KEY",
    apiKeyLabel: "OpenAI / 中转密钥",
    apiKeyPlaceholder: "填写 OpenAI 或中转服务 API Key",
  },
  opencode: {
    label: "OpenCode",
    defaultProviderType: "official",
    defaultProviderId: "openai",
    defaultProviderName: "OpenAI",
    defaultBaseUrl: "https://api.openai.com/v1",
    defaultAuthEnvKey: "OPENAI_API_KEY",
    apiKeyLabel: "OpenCode Provider 密钥",
    apiKeyPlaceholder: "填写官方、兼容中转或自定义 Provider API Key",
  },
};

type CloudCliProviderPreset = {
  value: string;
  label: string;
  providerType: CliCredentialProviderType;
  providerId: string;
  providerName: string;
  baseUrl: string;
  authEnvKey: string;
  defaultModel: string;
};

const CLOUD_CLI_PROVIDER_PRESETS: Record<CliCredentialTool, CloudCliProviderPreset[]> = {
  claude_code: [
    {
      value: "anthropic",
      label: "Anthropic 官方",
      providerType: "official",
      providerId: "anthropic",
      providerName: "Anthropic",
      baseUrl: "",
      authEnvKey: "ANTHROPIC_API_KEY",
      defaultModel: "claude-sonnet-4-5",
    },
    {
      value: "deepseek_anthropic",
      label: "DeepSeek Anthropic",
      providerType: "cc_switch",
      providerId: "deepseek",
      providerName: "DeepSeek",
      baseUrl: "https://api.deepseek.com/anthropic",
      authEnvKey: "ANTHROPIC_AUTH_TOKEN",
      defaultModel: "deepseek-v4-pro",
    },
  ],
  codex: [
    {
      value: "openai",
      label: "OpenAI 官方",
      providerType: "official",
      providerId: "OpenAI",
      providerName: "OpenAI",
      baseUrl: "https://api.openai.com/v1",
      authEnvKey: "OPENAI_API_KEY",
      defaultModel: "gpt-5.5",
    },
    {
      value: "custom_codex",
      label: "自定义 OpenAI 兼容中转",
      providerType: "proxy",
      providerId: "OpenAI",
      providerName: "OpenAI",
      baseUrl: "",
      authEnvKey: "OPENAI_API_KEY",
      defaultModel: "",
    },
  ],
  opencode: [
    {
      value: "openai",
      label: "OpenAI",
      providerType: "official",
      providerId: "openai",
      providerName: "OpenAI",
      baseUrl: "https://api.openai.com/v1",
      authEnvKey: "OPENAI_API_KEY",
      defaultModel: "gpt-5.5",
    },
    {
      value: "deepseek",
      label: "DeepSeek",
      providerType: "proxy",
      providerId: "deepseek",
      providerName: "DeepSeek",
      baseUrl: "https://api.deepseek.com/v1",
      authEnvKey: "DEEPSEEK_API_KEY",
      defaultModel: "deepseek-chat",
    },
    {
      value: "openrouter",
      label: "OpenRouter",
      providerType: "proxy",
      providerId: "openrouter",
      providerName: "OpenRouter",
      baseUrl: "https://openrouter.ai/api/v1",
      authEnvKey: "OPENROUTER_API_KEY",
      defaultModel: "openai/gpt-5.5",
    },
    {
      value: "qwen",
      label: "通义千问",
      providerType: "proxy",
      providerId: "qwen",
      providerName: "DashScope",
      baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      authEnvKey: "DASHSCOPE_API_KEY",
      defaultModel: "qwen-plus",
    },
  ],
};

export function AgentCliForm({
  initial,
  runtimeScope = "local",
  onSave,
  onCancel,
}: {
  initial?: AgentConfig;
  runtimeScope?: "local" | "cloud";
  onSave: (data: AgentConfigCreate) => Promise<void>;
  onCancel: () => void;
}) {
  const defaultCliTool = initial?.cliTool ?? (runtimeScope === "cloud" ? "codex" : "claude_code");
  const [cliTool, setCliTool] = useState<CliTool>(defaultCliTool);
  const preset = CLI_PRESETS[cliTool];
  const [name, setName] = useState(initial?.name ?? (runtimeScope === "cloud" ? "自定义 Agent" : preset.name));
  const [note, setNote] = useState(initial?.description ?? (runtimeScope === "cloud" ? "使用云端 Engine 的自定义智能体" : preset.description));
  const [systemPrompt, setSystemPrompt] = useState(initial?.systemPrompt ?? "");
  const [rules, setRules] = useState(initial?.rules ?? "");
  const [avatar, setAvatar] = useState(
    initial?.avatar || (runtimeScope === "cloud" && !initial ? CUSTOM_AGENT_DEFAULT_AVATAR : defaultAvatarForTool(defaultCliTool)),
  );
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  const [toolset, setToolset] = useState<string[]>(initial?.toolset ?? []);
  const [contextPolicy, setContextPolicy] = useState(initial?.contextPolicy ?? "workspace_coding");
  const [executable, setExecutable] = useState(initial?.executable ?? preset.executable);
  const [argsText, setArgsText] = useState((initial?.initArgs ?? preset.initArgs).join(" "));
  const initialEnv: Record<string, string> = initial?.envVars ?? preset.envVars;
  const [envText, setEnvText] = useState(formatEnv(initialEnv));
  const [codexConnection, setCodexConnection] = useState<"official" | "proxy">("proxy");
  const [codexBaseUrl, setCodexBaseUrl] = useState("");
  const [codexModel, setCodexModel] = useState("");
  const [codexApiKey, setCodexApiKey] = useState("");
  const [codexProviderId, setCodexProviderId] = useState("agenthub_proxy");
  const [codexProviderName, setCodexProviderName] = useState("AgentHub Codex Proxy");
  const [codexUseChatgptAuth, setCodexUseChatgptAuth] = useState(true);
  const [codexStatus, setCodexStatus] = useState<string | null>(null);
  const [codexReady, setCodexReady] = useState<boolean | null>(null);
  const [codexApiKeySet, setCodexApiKeySet] = useState(false);
  const [cloudCredentials, setCloudCredentials] = useState<CliCredentialConfig[]>([]);
  const [cloudCredentialLoading, setCloudCredentialLoading] = useState(false);
  const [cloudCredentialStatus, setCloudCredentialStatus] = useState<string | null>(null);
  const [cloudProviderKey, setCloudProviderKey] = useState("");
  const [cloudProviderType, setCloudProviderType] = useState<CliCredentialProviderType>("official");
  const [cloudProviderId, setCloudProviderId] = useState("");
  const [cloudProviderName, setCloudProviderName] = useState("");
  const [cloudBaseUrl, setCloudBaseUrl] = useState("");
  const [cloudModel, setCloudModel] = useState("");
  const [cloudAuthEnvKey, setCloudAuthEnvKey] = useState("");
  const [cloudApiKey, setCloudApiKey] = useState("");
  const [cloudCredentialConfigured, setCloudCredentialConfigured] = useState(false);
  const [cloudCodexReviewModel, setCloudCodexReviewModel] = useState("");
  const [cloudCodexReasoningEffort, setCloudCodexReasoningEffort] = useState("xhigh");
  const [cloudCodexWireApi, setCloudCodexWireApi] = useState("responses");
  const [cloudCodexNetworkAccess, setCloudCodexNetworkAccess] = useState("enabled");
  const [cloudCodexRequiresOpenaiAuth, setCloudCodexRequiresOpenaiAuth] = useState(true);
  const [cloudModelOptions, setCloudModelOptions] = useState<CliModelOption[]>([]);
  const [cloudModelSource, setCloudModelSource] = useState<string | null>(null);
  const [cloudModelLoading, setCloudModelLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [selectedTemplateName, setSelectedTemplateName] = useState<string | null>(null);
  const isBuiltinCloudEngine = runtimeScope === "cloud" && Boolean(
    initial
    && isCliCredentialTool(cliTool)
    && isNativeCloudEngine(initial),
  );
  const cloudCredentialMeta = isCliCredentialTool(cliTool) ? CLOUD_CLI_CREDENTIAL_META[cliTool] : null;
  const cloudProviderPresets = isCliCredentialTool(cliTool) ? CLOUD_CLI_PROVIDER_PRESETS[cliTool] : [];
  const cloudProviderOptions: UiSelectOption[] = cloudProviderPresets.map((provider) => ({
    value: provider.value,
    label: provider.label,
  }));
  const codexCustomProvider = cliTool === "codex" && cloudProviderKey === "custom_codex";
  const formGridClass = isBuiltinCloudEngine
    ? "grid items-start gap-4"
    : "grid items-start gap-4 lg:grid-cols-2";
  const cloudModelSelectOptions: UiSelectOption[] = cloudModelOptions.map((model) => ({
    value: model.id,
    label: model.label,
    description: [
      model.lastUpdated ? `更新 ${model.lastUpdated}` : "",
      model.reasoning ? "reasoning" : "",
      model.toolCall ? "tools" : "",
    ].filter(Boolean).join(" · "),
  }));

  useEffect(() => {
    let cancelled = false;
    fetchSkills()
      .then((items) => { if (!cancelled) setSkills(items); })
      .catch(() => { if (!cancelled) setSkills([]); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (runtimeScope !== "local" || cliTool !== "codex") return;
    let cancelled = false;
    fetchCodexLocalConfig()
      .then((config) => {
        if (cancelled) return;
        if (config.connection === "official" || config.connection === "proxy") {
          setCodexConnection(config.connection);
        }
        setCodexBaseUrl(config.baseUrl || "");
        setCodexModel(config.model || "");
        setCodexProviderId(config.providerId || "agenthub_proxy");
        setCodexProviderName(config.providerName || "AgentHub Codex Proxy");
        setCodexUseChatgptAuth(config.authMode === "openai_auth");
        setCodexStatus(config.message);
        setCodexReady(config.ready);
        setCodexApiKeySet(config.apiKeySet);
      })
      .catch(() => {
        if (!cancelled) setCodexStatus("未能读取本机 Codex 配置");
      });
    return () => { cancelled = true; };
  }, [cliTool, runtimeScope]);

  useEffect(() => {
    if (runtimeScope !== "cloud") return;
    let cancelled = false;
    setCloudCredentialLoading(true);
    fetchCliCredentials()
      .then((items) => {
        if (cancelled) return;
        setCloudCredentials(items);
        setCloudCredentialStatus(null);
      })
      .catch((error) => {
        if (cancelled) return;
        setCloudCredentialStatus(error instanceof Error ? error.message : "云端 CLI 凭据加载失败");
      })
      .finally(() => {
        if (!cancelled) setCloudCredentialLoading(false);
      });
    return () => { cancelled = true; };
  }, [runtimeScope]);

  useEffect(() => {
    if (runtimeScope !== "cloud" || !cloudCredentialMeta || !isCliCredentialTool(cliTool)) return;
    const credential = cloudCredentials.find((item) => item.cliTool === cliTool) ?? null;
    const preset = findCloudProviderPreset(cliTool, credential) ?? CLOUD_CLI_PROVIDER_PRESETS[cliTool][0];
    const customCodexPreset = cliTool === "codex" && preset.value === "custom_codex";
    setCloudProviderKey(preset.value);
    setCloudProviderType(preset.providerType);
    setCloudProviderId(customCodexPreset ? credential?.providerId ?? preset.providerId : preset.providerId);
    setCloudProviderName(customCodexPreset ? credential?.providerName ?? preset.providerName : preset.providerName);
    setCloudBaseUrl(customCodexPreset ? credential?.baseUrl ?? preset.baseUrl : preset.baseUrl);
    setCloudModel(credential?.model ?? preset.defaultModel);
    setCloudAuthEnvKey(customCodexPreset ? credential?.authEnvKey ?? preset.authEnvKey : preset.authEnvKey);
    setCloudCodexReviewModel(readStringConfig(credential, "reviewModel"));
    setCloudCodexReasoningEffort(readStringConfig(credential, "modelReasoningEffort") || "xhigh");
    setCloudCodexWireApi(readStringConfig(credential, "wireApi") || "responses");
    setCloudCodexNetworkAccess(readStringConfig(credential, "networkAccess") || "enabled");
    setCloudCodexRequiresOpenaiAuth(readBoolConfig(credential, "requiresOpenaiAuth", true));
    setCloudApiKey("");
    setCloudCredentialConfigured(Boolean(credential?.configured));
  }, [cliTool, cloudCredentialMeta, cloudCredentials, runtimeScope]);

  useEffect(() => {
    if (runtimeScope !== "cloud" || cliTool !== "opencode" || !cloudProviderId) {
      setCloudModelOptions([]);
      setCloudModelSource(null);
      return;
    }
    let cancelled = false;
    setCloudModelLoading(true);
    fetchCliCredentialModels("opencode", cloudProviderId)
      .then((result) => {
        if (cancelled) return;
        setCloudModelOptions(result.items);
        setCloudModelSource(result.source);
        if (result.items[0]) {
          setCloudModel((current) => current.trim() ? current : result.items[0].id);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setCloudModelOptions([]);
        setCloudModelSource("manual");
      })
      .finally(() => {
        if (!cancelled) setCloudModelLoading(false);
      });
    return () => { cancelled = true; };
  }, [cliTool, cloudProviderId, runtimeScope]);

  const selectTool = (next: CliTool) => {
    const nextPreset = CLI_PRESETS[next];
    setCliTool(next);
    if (runtimeScope === "local") {
      setName(nextPreset.name);
      setNote(nextPreset.description);
      setSystemPrompt("");
      setRules("");
      setAvatar(defaultAvatarForTool(next));
      setToolset([]);
      setContextPolicy("workspace_coding");
    } else {
      setName((current) => current.trim() || "自定义 Agent");
      setNote((current) => current.trim() || `使用 ${nextPreset.name} Engine 的自定义智能体`);
      setAvatar((current) => current || CUSTOM_AGENT_DEFAULT_AVATAR);
    }
    setExecutable(nextPreset.executable);
    setArgsText(nextPreset.initArgs.join(" "));
    setEnvText(formatEnv(nextPreset.envVars));
    setCodexConnection("proxy");
    setCodexBaseUrl("");
    setCodexModel("");
    setCodexApiKey("");
    setCodexProviderId("agenthub_proxy");
    setCodexProviderName("AgentHub Codex Proxy");
    setCodexUseChatgptAuth(true);
    if (isCliCredentialTool(next)) {
      const preset = CLOUD_CLI_PROVIDER_PRESETS[next][0];
      setCloudProviderKey(preset.value);
      setCloudProviderType(preset.providerType);
      setCloudProviderId(preset.providerId);
      setCloudProviderName(preset.providerName);
      setCloudBaseUrl(preset.baseUrl);
      setCloudModel(preset.defaultModel);
      setCloudAuthEnvKey(preset.authEnvKey);
      setCloudApiKey("");
      setCloudCredentialConfigured(false);
    }
    setCheckResult(null);
    setFormError(null);
    setSelectedTemplateName(null);
  };

  const applyTemplate = (template: AgentTemplatePreset) => {
    const codexPreset = CLI_PRESETS.codex;
    setSelectedTemplateName(template.name);
    setCliTool("codex");
    setName(template.name);
    setNote(template.description);
    setSystemPrompt(template.systemPrompt);
    setRules(template.rules);
    setToolset(template.toolset);
    setContextPolicy(template.contextPolicy);
    setAvatar(template.avatar);
    setExecutable(codexPreset.executable);
    setArgsText(codexPreset.initArgs.join(" "));
    setEnvText(formatEnv(codexPreset.envVars));
    setCheckResult(null);
    setFormError(null);
  };

  const updateCodexConnection = (value: "official" | "proxy") => {
    setCodexConnection(value);
    if (value === "official") {
      setCodexProviderId("openai");
      setCodexProviderName("OpenAI");
      setCodexBaseUrl((current) => current || "https://api.openai.com/v1");
    } else {
      setCodexProviderId("agenthub_proxy");
      setCodexProviderName("AgentHub Codex Proxy");
    }
  };

  const updateCloudProvider = (value: string) => {
    if (!isCliCredentialTool(cliTool)) return;
    const preset = CLOUD_CLI_PROVIDER_PRESETS[cliTool].find((item) => item.value === value)
      ?? CLOUD_CLI_PROVIDER_PRESETS[cliTool][0];
    setCloudProviderKey(preset.value);
    setCloudProviderType(preset.providerType);
    setCloudProviderId(preset.providerId);
    setCloudProviderName(preset.providerName);
    setCloudBaseUrl(preset.baseUrl);
    setCloudModel(preset.defaultModel);
    setCloudAuthEnvKey(preset.authEnvKey);
    setCloudApiKey("");
    setCloudCredentialConfigured(false);
    setCloudCodexReviewModel("");
    setCloudCodexReasoningEffort("xhigh");
    setCloudCodexWireApi("responses");
    setCloudCodexNetworkAccess("enabled");
    setCloudCodexRequiresOpenaiAuth(true);
    setCloudModelOptions([]);
    setCloudModelSource(null);
    setFormError(null);
  };

  const handleCheck = async () => {
    if (runtimeScope !== "local" || !executable.trim()) return;
    setChecking(true);
    try {
      const result = await checkAgentExecutable(executable.trim());
      setCheckResult(result.found ? `已找到: ${result.version || result.path || executable}` : "未找到 executable");
    } catch {
      setCheckResult("检测失败");
    } finally {
      setChecking(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setFormError(null);
    try {
      if (runtimeScope === "cloud" && cloudCredentialMeta && isCliCredentialTool(cliTool)) {
        if (!cloudApiKey.trim() && !cloudCredentialConfigured) {
          setFormError(`请先填写 ${cloudCredentialMeta.label} API Key`);
          setSaving(false);
          return;
        }
        if (/^https?:\/\//i.test(cloudApiKey.trim())) {
          setFormError("API Key 不能填写 URL，请填写供应商控制台生成的密钥");
          setSaving(false);
          return;
        }
        const savedCredential = await saveCliCredential(cliTool, {
          scope: "user",
          providerType: cloudProviderType,
          providerId: cloudProviderId.trim() || null,
          providerName: cloudProviderName.trim() || null,
          baseUrl: cloudBaseUrl.trim() || null,
          model: cloudModel.trim() || null,
          authEnvKey: cloudAuthEnvKey.trim() || cloudCredentialMeta.defaultAuthEnvKey,
          apiKey: cloudApiKey.trim() || null,
          config: cliTool === "codex" ? {
            wireApi: cloudCodexWireApi.trim() || "responses",
            reviewModel: cloudCodexReviewModel.trim() || cloudModel.trim() || null,
            modelReasoningEffort: cloudCodexReasoningEffort.trim() || "xhigh",
            networkAccess: cloudCodexNetworkAccess.trim() || "enabled",
            disableResponseStorage: true,
            requiresOpenaiAuth: cloudCodexRequiresOpenaiAuth,
          } : {},
        });
        setCloudCredentials((current) => [
          ...current.filter((item) => item.cliTool !== savedCredential.cliTool),
          savedCredential,
        ]);
        setCloudCredentialConfigured(savedCredential.configured);
        setCloudApiKey("");
      }
      if (runtimeScope === "local" && cliTool === "codex") {
        const updated = await updateCodexLocalConfig({
          connection: codexConnection,
          baseUrl: normalizeCodexBaseUrl(codexBaseUrl, codexConnection) || (
            codexConnection === "official" ? "https://api.openai.com/v1" : ""
          ),
          model: codexModel.trim(),
          apiKey: codexApiKey.trim(),
          providerId: codexProviderId.trim(),
          providerName: codexProviderName.trim(),
          useChatgptAuth: codexConnection === "official" && codexUseChatgptAuth,
        });
        setCodexStatus(updated.message);
        setCodexReady(updated.ready);
        setCodexApiKeySet(updated.apiKeySet);
        setCodexApiKey("");
      }
      await onSave({
        name: name.trim(),
        description: note.trim(),
        systemPrompt: systemPrompt.trim(),
        rules: rules.trim(),
        agentType: "cli_wrapper",
        cliTool,
        executable: runtimeScope === "local" ? executable.trim() : CLI_PRESETS[cliTool].executable,
        initArgs: runtimeScope === "local" ? parseArgs(argsText) : [...CLI_PRESETS[cliTool].initArgs],
        envVars: runtimeScope === "local" ? parseEnv(envText, cliTool) : {},
        toolset,
        contextPolicy,
        avatar: isBuiltinCloudEngine ? "" : avatar,
      });
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <GlobalModal
      title={initial ? "智能体设置" : runtimeScope === "local" ? "添加命令行智能体" : "添加云端智能体"}
      subtitle={isBuiltinCloudEngine ? "配置当前用户的云端 CLI 凭据" : runtimeScope === "local" ? "身份 + 工具集 + 本机运行参数" : "身份 + 工具集 + 云端运行策略"}
      icon={(
        <AgentAvatar
          agent={{ name: name || "Agent", cliTool, status: "ready", avatar }}
          size="md"
        />
      )}
      zIndexClass="z-[1200]"
      onClose={onCancel}
      footer={(
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {formError ? (
            <div className="flex items-center gap-2 text-xs leading-5 text-[color:var(--ah-danger)]">
              <AlertCircle size={15} />
              {formError}
            </div>
          ) : (
            <div className="agenthub-faint text-xs">
              {runtimeScope === "local" ? "更改会在下次启动 CLI 进程时生效" : "更改会在下次云端运行时调度时生效"}
            </div>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="agenthub-icon-button rounded-full px-4 py-2 text-sm"
            >
              取消
            </button>
            <button
              type="submit"
              form="agent-cli-form"
              disabled={saving || !name.trim()}
              className="agenthub-primary-button inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              保存
            </button>
          </div>
        </div>
      )}
    >
      <form id="agent-cli-form" onSubmit={handleSubmit} className="w-full">
          <div data-testid="agent-cli-form-grid" className={formGridClass}>
            {!initial && !isBuiltinCloudEngine && (
              <div className="lg:col-span-2">
                <ConfigSection icon={Sparkles} title="模板" description="选择后会预填身份、规则和工具集">
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {AGENT_TEMPLATE_PRESETS.map((template) => {
                      const selected = selectedTemplateName === template.name;
                      return (
                        <button
                          key={template.name}
                          type="button"
                          onClick={() => applyTemplate(template)}
                          className={`agenthub-soft flex min-h-[76px] flex-col items-start justify-between rounded-2xl border px-3 py-2.5 text-left transition hover:border-[color:var(--ah-border-hover)] hover:bg-[color:var(--ah-card-soft)] ${
                            selected ? "ring-2 ring-[color:var(--ah-accent-strong)] ring-offset-2 ring-offset-[color:var(--ah-card)]" : ""
                          }`}
                        >
                          <span className="agenthub-strong text-sm font-medium">{template.name}</span>
                          <span className="agenthub-muted mt-1 line-clamp-2 text-xs leading-5">{template.description}</span>
                        </button>
                      );
                    })}
                  </div>
                </ConfigSection>
              </div>
            )}

            <div className={isBuiltinCloudEngine ? "" : "lg:col-span-2"}>
            <ConfigSection icon={Settings2} title="基础信息" description="设置用户可见的智能体身份">
              <FieldLabel label="头像">
                {isBuiltinCloudEngine ? (
                  <div className="agenthub-soft flex items-center gap-2 rounded-2xl border px-3 py-2 text-xs">
                    <AgentAvatar
                      agent={{ name: name || "Agent", cliTool, status: "ready", avatar: "" }}
                      size="sm"
                    />
                    <span className="agenthub-muted">内置 Engine 使用厂商图标</span>
                  </div>
                ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {AGENT_AVATAR_PRESETS.map((presetAvatar) => {
                    const Icon = presetAvatar.icon;
                    const selected = avatar === presetAvatar.id;
                    return (
                      <button
                        key={presetAvatar.id}
                        type="button"
                        onClick={() => setAvatar(presetAvatar.id)}
                        className={`flex h-10 w-10 items-center justify-center rounded-full border transition ${
                          selected ? "ring-2 ring-[color:var(--ah-accent-strong)] ring-offset-2 ring-offset-[color:var(--ah-card)]" : "hover:-translate-y-0.5"
                        } ${presetAvatar.className}`}
                        title={presetAvatar.label}
                        aria-label={`选择${presetAvatar.label}头像`}
                      >
                        <Icon size={18} strokeWidth={1.9} />
                      </button>
                    );
                  })}
                  {avatar.startsWith("data:image/") && (
                    <span
                      className="agenthub-icon-button flex h-10 w-10 items-center justify-center overflow-hidden rounded-full border"
                      title="当前上传头像"
                      aria-label="当前上传头像"
                    >
                      <img src={avatar} alt="" className="h-full w-full object-cover" />
                    </span>
                  )}
                  <label className="agenthub-icon-button inline-flex h-10 cursor-pointer items-center gap-1.5 rounded-full border px-3 text-xs">
                    <Upload size={14} />
                    上传
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/gif"
                      className="sr-only"
                      onChange={(event) => {
                        const file = event.currentTarget.files?.[0] ?? null;
                        event.currentTarget.value = "";
                        if (!file) return;
                        void readAvatarFile(file)
                          .then(setAvatar)
                          .catch((error) => setFormError(error instanceof Error ? error.message : "头像读取失败"));
                      }}
                    />
                  </label>
                </div>
                )}
              </FieldLabel>
              <FieldLabel label="显示名称">
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                  disabled={isBuiltinCloudEngine}
                  className={inputClass}
                />
              </FieldLabel>
              <FieldLabel label="备注">
                <input
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="例如：偏前端、偏审查、偏架构"
                  className={inputClass}
                />
              </FieldLabel>
            </ConfigSection>
            </div>

            {!isBuiltinCloudEngine && (
            <div className="lg:col-span-2">
              <ConfigSection icon={ShieldCheck} title="身份与规则" description="System Prompt 定义身份/业务边界，Rules 定义长期行为原则">
                <FieldLabel label="System Prompt">
                  <textarea
                    value={systemPrompt}
                    onChange={(event) => setSystemPrompt(event.target.value)}
                    rows={5}
                    placeholder="例如：你是家庭资产管理项目的系统架构师，只负责技术方案、模块边界、数据模型和接口契约。"
                    className={`${inputClass} min-h-[140px] resize-y leading-5`}
                  />
                </FieldLabel>
                <FieldLabel label="Rules">
                  <textarea
                    value={rules}
                    onChange={(event) => setRules(event.target.value)}
                    rows={5}
                    placeholder="例如：所有文档使用中文；回答先给结论再给风险；正式产物写入项目 docs/；不要扩大用户确认过的范围。"
                    className={`${inputClass} min-h-[140px] resize-y leading-5`}
                  />
                </FieldLabel>
              </ConfigSection>
            </div>
            )}

            {!isBuiltinCloudEngine && (
            <ConfigSection
              icon={Sparkles}
              title="能力配置"
              description={runtimeScope === "local" ? "工具集来自本机 Skill，Engine 负责真实执行" : "工具集由云端工作区加载，Engine 由云端运行时调度"}
            >
              <FieldLabel label={runtimeScope === "local" ? "命令行类型" : "Engine"}>
                <UiSelect
                  ariaLabel={runtimeScope === "local" ? "命令行类型" : "Engine"}
                  value={cliTool}
                  options={CLI_TOOL_OPTIONS}
                  disabled={isBuiltinCloudEngine}
                  onValueChange={(next) => selectTool(next as CliTool)}
                />
              </FieldLabel>
              <FieldLabel label="工具集">
                {skills.length === 0 ? (
                  <div className="agenthub-soft rounded-2xl border px-3 py-3 text-xs leading-5">
                    {runtimeScope === "local" ? "未发现本机 Skill。" : "未发现可用 Skill。"}可以先留空，Agent 会仅按 System Prompt、Rules 和当前任务工作。
                  </div>
                ) : (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {skills.map((skill) => (
                      <label key={skill.id} className="agenthub-soft flex min-w-0 items-center gap-2 rounded-xl border px-3 py-2 text-xs transition hover:border-[color:var(--ah-border-strong)] hover:bg-[color:var(--ah-card-soft)]">
                        <input
                          type="checkbox"
                          checked={toolset.includes(skill.id)}
                          onChange={() => setToolset((current) => toggleTool(current, skill.id))}
                          className="h-4 w-4 shrink-0 accent-[color:var(--ah-accent-strong)]"
                        />
                        <span className="min-w-0 flex-1 truncate" title={skill.path ? `${skill.description}\n${skill.path}` : skill.description}>
                          {skill.name}
                        </span>
                        <span className="shrink-0 rounded bg-emerald-400/10 px-1.5 py-0.5 text-[10px] text-emerald-700 dark:text-emerald-200">
                          {runtimeScope === "local" ? "本机" : "云端"}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </FieldLabel>
              <FieldLabel label="上下文策略">
                <UiSelect
                  ariaLabel="上下文策略"
                  value={contextPolicy}
                  options={CONTEXT_POLICY_OPTIONS}
                  onValueChange={setContextPolicy}
                />
              </FieldLabel>
            </ConfigSection>
            )}

            {runtimeScope === "cloud" && cloudCredentialMeta && (
              <ConfigSection
                icon={KeyRound}
                title="Engine 凭据"
                description={`${cloudCredentialMeta.label} 的 API Key、Provider 和中转配置会作为当前用户配置保存`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge
                    ready={cloudCredentialConfigured}
                    label={cloudCredentialConfigured ? "已配置" : "需要 API Key"}
                  />
                  {cloudCredentialLoading && <SmallBadge icon={Loader2} label="加载中" />}
                </div>
                {cloudCredentialStatus && (
                  <div className="agenthub-status-warning rounded-2xl border px-3 py-2 text-xs leading-5">
                    {cloudCredentialStatus}
                  </div>
                )}
                <div className="grid gap-3">
                  <FieldLabel label="Provider">
                    <UiSelect
                      ariaLabel={`${cloudCredentialMeta.label} Provider`}
                      value={cloudProviderKey}
                      options={cloudProviderOptions}
                      onValueChange={updateCloudProvider}
                    />
                  </FieldLabel>
                  <FieldLabel label="模型">
                    <div className="space-y-2">
                      {cliTool === "opencode" && cloudModelSelectOptions.length > 0 && (
                        <UiSelect
                          ariaLabel="OpenCode 模型"
                          value={cloudModel}
                          options={cloudModelSelectOptions}
                          onValueChange={setCloudModel}
                        />
                      )}
                      <input
                        value={cloudModel}
                        onChange={(event) => setCloudModel(event.target.value)}
                        placeholder={cloudProviderPresets.find((item) => item.value === cloudProviderKey)?.defaultModel ?? "gpt-5.5"}
                        className={inputClass}
                      />
                      {cliTool === "opencode" && (
                        <div className="agenthub-faint flex flex-wrap items-center gap-2 text-[11px]">
                          {cloudModelLoading && <span>模型目录同步中</span>}
                          {cloudModelSource && <span>模型目录：{cloudModelSource}</span>}
                          <span>找不到模型时可直接填写 Provider 文档中的 model id。</span>
                        </div>
                      )}
                    </div>
                  </FieldLabel>
                  {codexCustomProvider && (
                    <div className="grid gap-3 rounded-2xl border border-[color:var(--ah-border)] p-3">
                      <div className="agenthub-muted text-xs font-medium">Codex config.toml 关键配置</div>
                      <div className="grid gap-3 lg:grid-cols-2">
                        <FieldLabel label="Provider ID">
                          <input
                            value={cloudProviderId}
                            onChange={(event) => setCloudProviderId(event.target.value)}
                            placeholder="OpenAI"
                            className={inputClass}
                          />
                        </FieldLabel>
                        <FieldLabel label="Provider 名称">
                          <input
                            value={cloudProviderName}
                            onChange={(event) => setCloudProviderName(event.target.value)}
                            placeholder="OpenAI"
                            className={inputClass}
                          />
                        </FieldLabel>
                        <FieldLabel label="Base URL">
                          <input
                            value={cloudBaseUrl}
                            onChange={(event) => setCloudBaseUrl(event.target.value)}
                            placeholder="https://your-relay.example.com"
                            className={inputClass}
                          />
                        </FieldLabel>
                        <FieldLabel label="Env Key">
                          <input
                            value={cloudAuthEnvKey}
                            onChange={(event) => setCloudAuthEnvKey(event.target.value)}
                            placeholder="OPENAI_API_KEY"
                            className={inputClass}
                          />
                        </FieldLabel>
                        <FieldLabel label="wire_api">
                          <UiSelect
                            ariaLabel="Codex wire_api"
                            value={cloudCodexWireApi}
                            options={[{ value: "responses", label: "responses" }]}
                            onValueChange={setCloudCodexWireApi}
                          />
                        </FieldLabel>
                        <FieldLabel label="review_model">
                          <input
                            value={cloudCodexReviewModel}
                            onChange={(event) => setCloudCodexReviewModel(event.target.value)}
                            placeholder={cloudModel || "gpt-5.5"}
                            className={inputClass}
                          />
                        </FieldLabel>
                        <FieldLabel label="reasoning effort">
                          <UiSelect
                            ariaLabel="Codex reasoning effort"
                            value={cloudCodexReasoningEffort}
                            options={[
                              { value: "xhigh", label: "xhigh" },
                              { value: "high", label: "high" },
                              { value: "medium", label: "medium" },
                              { value: "low", label: "low" },
                              { value: "minimal", label: "minimal" },
                            ]}
                            onValueChange={setCloudCodexReasoningEffort}
                          />
                        </FieldLabel>
                        <FieldLabel label="network_access">
                          <UiSelect
                            ariaLabel="Codex network access"
                            value={cloudCodexNetworkAccess}
                            options={[
                              { value: "enabled", label: "enabled" },
                              { value: "disabled", label: "disabled" },
                            ]}
                            onValueChange={setCloudCodexNetworkAccess}
                          />
                        </FieldLabel>
                        <label className="agenthub-soft flex min-w-0 items-center gap-2 rounded-xl border px-3 py-2 text-xs">
                          <input
                            type="checkbox"
                            checked={cloudCodexRequiresOpenaiAuth}
                            onChange={(event) => setCloudCodexRequiresOpenaiAuth(event.target.checked)}
                            className="h-4 w-4 shrink-0 accent-[color:var(--ah-accent-strong)]"
                            aria-label="Codex requires_openai_auth"
                          />
                          <span className="min-w-0 flex-1">requires_openai_auth</span>
                        </label>
                      </div>
                    </div>
                  )}
                  <FieldLabel label={cloudCredentialMeta.apiKeyLabel}>
                    <div className="relative">
                      <KeyRound size={15} className="agenthub-faint pointer-events-none absolute left-3 top-1/2 -translate-y-1/2" />
                      <input
                        value={cloudApiKey}
                        onChange={(event) => setCloudApiKey(event.target.value)}
                        placeholder={cloudCredentialConfigured ? "已保存，留空则沿用" : cloudCredentialMeta.apiKeyPlaceholder}
                        type="password"
                        aria-label={`${cliTool}-api-key`}
                        className={`${inputClass} pl-9`}
                      />
                    </div>
                  </FieldLabel>
                </div>
                <div className="agenthub-status-info flex items-start gap-2 rounded-2xl border px-3 py-2 text-xs leading-5">
                  <ServerCog size={15} className="mt-0.5 shrink-0" />
                  <span>
                    保存后密钥进入云端 Secret，运行时会按当前用户和项目注入对应 CLI；AgentConfig 不保存明文密钥。
                  </span>
                </div>
              </ConfigSection>
            )}

            {runtimeScope === "local" && (
            <ConfigSection icon={Terminal} title="启动命令" description="AgentHub 会在项目工作区里启动这个命令行工具">
              <FieldLabel label="可执行命令">
                <div className="flex gap-2">
                  <input
                    value={executable}
                    onChange={(event) => { setExecutable(event.target.value); setCheckResult(null); }}
                    placeholder="claude / codex / opencode"
                    className={inputClass}
                  />
                  <button
                    type="button"
                    onClick={handleCheck}
                    disabled={checking || !executable.trim()}
                    className="agenthub-icon-button inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full px-3 text-sm disabled:opacity-50"
                  >
                    {checking ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
                    检测
                  </button>
                </div>
              </FieldLabel>
              {checkResult && (
                <StatusLine ok={checkResult.startsWith("已找到")} text={checkResult} />
              )}
              <FieldLabel label="启动参数">
                <textarea
                  value={argsText}
                  onChange={(event) => setArgsText(event.target.value)}
                  rows={3}
                  placeholder="-p --output-format stream-json"
                  className={`${inputClass} min-h-[96px] resize-none leading-5`}
                />
              </FieldLabel>
            </ConfigSection>
            )}

            {runtimeScope === "local" && cliTool === "codex" && (
              <div className="lg:col-span-2">
                <ConfigSection icon={Network} title="Codex 模型连接" description="支持官方 OpenAI API 与 OpenAI 兼容中转服务">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge ready={Boolean(codexReady)} label={codexReady ? "连接可用" : "需要配置"} />
                    {codexApiKeySet && <SmallBadge icon={ShieldCheck} label="密钥已保存" />}
                  </div>
                  {codexStatus && (
                    <div className="agenthub-soft rounded-2xl border px-3 py-2 text-xs leading-5">
                      {codexStatus}
                    </div>
                  )}
                  <div className="grid gap-3 lg:grid-cols-2">
                    <FieldLabel label="连接模式">
                      <UiSelect
                        ariaLabel="连接模式"
                        value={codexConnection}
                        options={CODEX_CONNECTION_OPTIONS}
                        onValueChange={(next) => updateCodexConnection(next as "official" | "proxy")}
                      />
                    </FieldLabel>
                    <FieldLabel label="模型">
                      <input
                        value={codexModel}
                        onChange={(event) => setCodexModel(event.target.value)}
                        placeholder="gpt-5.5"
                        className={inputClass}
                      />
                    </FieldLabel>
                    <FieldLabel label="服务地址">
                      <input
                        value={codexBaseUrl}
                        onChange={(event) => setCodexBaseUrl(event.target.value)}
                        placeholder={codexConnection === "official" ? "https://api.openai.com/v1" : "https://sub2.example.com/v1"}
                        className={inputClass}
                      />
                    </FieldLabel>
                    <FieldLabel label={codexConnection === "proxy" ? "中转服务密钥" : "OpenAI 密钥"}>
                      <div className="relative">
                        <KeyRound size={15} className="agenthub-faint pointer-events-none absolute left-3 top-1/2 -translate-y-1/2" />
                        <input
                          value={codexApiKey}
                          onChange={(event) => setCodexApiKey(event.target.value)}
                          placeholder={codexApiKeySet ? "已保存，留空则沿用" : "在这里填写，AgentHub 会写入本机 .codex/.env"}
                          type="password"
                          className={`${inputClass} pl-9`}
                        />
                      </div>
                    </FieldLabel>
                    <FieldLabel label="提供方标识">
                      <input value={codexProviderId} onChange={(event) => setCodexProviderId(event.target.value)} className={inputClass} />
                    </FieldLabel>
                    <FieldLabel label="Provider 名称">
                      <input value={codexProviderName} onChange={(event) => setCodexProviderName(event.target.value)} className={inputClass} />
                    </FieldLabel>
                  </div>
                  {codexConnection === "official" && (
                    <label className="agenthub-soft flex items-center gap-2 rounded-2xl border px-3 py-2 text-xs">
                      <input
                        type="checkbox"
                        checked={codexUseChatgptAuth}
                        onChange={(event) => setCodexUseChatgptAuth(event.target.checked)}
                        className="h-4 w-4 accent-[color:var(--ah-accent-strong)]"
                      />
                      使用本机 Codex 登录态
                    </label>
                  )}
                  <div className="agenthub-status-info flex items-start gap-2 rounded-2xl border px-3 py-2 text-xs leading-5">
                    <ServerCog size={15} className="mt-0.5 shrink-0" />
                    <span>
                      保存后 AgentHub 会把凭据写入本机 Codex .env，并让 Codex 通过本机凭据读取器按需读取；不会存进 Agent 配置。
                    </span>
                  </div>
                </ConfigSection>
              </div>
            )}

            {runtimeScope === "local" && (
            <div className="lg:col-span-2">
              <ConfigSection icon={SlidersHorizontal} title="高级环境变量" description="仅用于非密钥类命令行覆盖，密钥会被过滤">
                <textarea
                  value={envText}
                  onChange={(event) => setEnvText(event.target.value)}
                  placeholder="KEY=VALUE"
                  rows={4}
                  className={`${inputClass} resize-none font-mono text-xs leading-5`}
                />
              </ConfigSection>
            </div>
            )}
          </div>
      </form>
    </GlobalModal>
  );
}

const parseArgs = (value: string) => value.split(/\s+/).map((item) => item.trim()).filter(Boolean);

function toggleTool(current: string[], skillId: string) {
  if (current.includes(skillId)) return current.filter((id) => id !== skillId);
  return [...current, skillId];
}

function readAvatarFile(file: File): Promise<string> {
  if (!file.type.startsWith("image/")) {
    return Promise.reject(new Error("请选择图片文件"));
  }
  if (file.size > 512 * 1024) {
    return Promise.reject(new Error("头像图片不能超过 512KB"));
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") resolve(reader.result);
      else reject(new Error("头像读取失败"));
    };
    reader.onerror = () => reject(new Error("头像读取失败"));
    reader.readAsDataURL(file);
  });
}

function parseEnv(value: string, cliTool: CliTool): Record<string, string> {
  const env: Record<string, string> = {};
  for (const line of value.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || !trimmed.includes("=")) continue;
    const index = trimmed.indexOf("=");
    const key = trimmed.slice(0, index).trim();
    if (isBlockedAgentEnvKey(key, cliTool)) continue;
    env[key] = trimmed.slice(index + 1).trim();
  }
  return env;
}

function formatEnv(env: Record<string, string>): string {
  return Object.entries(env).map(([key, value]) => `${key}=${value}`).join("\n");
}

function defaultAvatarForTool(cliTool: CliTool) {
  return cliTool === "custom" ? CUSTOM_AGENT_DEFAULT_AVATAR : "";
}

function readStringConfig(credential: CliCredentialConfig | null, key: string) {
  const value = credential?.config?.[key];
  return typeof value === "string" ? value : "";
}

function readBoolConfig(credential: CliCredentialConfig | null, key: string, fallback: boolean) {
  const value = credential?.config?.[key];
  return typeof value === "boolean" ? value : fallback;
}

function findCloudProviderPreset(
  cliTool: CliCredentialTool,
  credential: CliCredentialConfig | null,
): CloudCliProviderPreset | null {
  const presets = CLOUD_CLI_PROVIDER_PRESETS[cliTool];
  if (!credential) return presets[0] ?? null;
  const baseUrl = credential.baseUrl ?? "";
  const exact = presets.find((preset) => (
    preset.providerId === credential.providerId
    && preset.providerName === credential.providerName
    && preset.baseUrl === baseUrl
  ));
  if (exact) return exact;
  if (cliTool === "codex" && credential.providerType === "proxy") {
    return presets.find((preset) => preset.value === "custom_codex") ?? presets[0] ?? null;
  }
  return presets.find((preset) => (
    preset.providerId === credential.providerId
    && preset.authEnvKey === credential.authEnvKey
  )) ?? presets[0] ?? null;
}

function normalizeCodexBaseUrl(value: string, mode: string) {
  void mode;
  const trimmed = value.trim().replace(/\/+$/, "");
  return trimmed;
}

function isCliCredentialTool(cliTool: CliTool): cliTool is CliCredentialTool {
  return cliTool === "claude_code" || cliTool === "codex" || cliTool === "opencode";
}

function isNativeDefaultAgent(agent: AgentConfig) {
  return (
    (agent.cliTool === "claude_code" && agent.name === "Claude Code")
    || (agent.cliTool === "codex" && agent.name === "Codex")
    || (agent.cliTool === "opencode" && agent.name === "OpenCode")
  );
}

function isNativeCloudEngine(agent: AgentConfig) {
  if (!isCliCredentialTool(agent.cliTool)) return false;
  if (isNativeDefaultAgent(agent)) return true;
  if (agent.executable === null || agent.executable === "") return true;
  return agent.avatar === "" && CLI_PRESETS[agent.cliTool].executable === agent.executable;
}

const inputClass = "agenthub-composer agenthub-textarea agenthub-focus-ring w-full rounded-2xl border px-3 py-2 text-sm placeholder:text-[color:var(--ah-faint)]";

function ConfigSection({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="agenthub-card space-y-3 rounded-3xl border p-4">
      <div className="flex items-start gap-3">
        <div className="agenthub-soft flex h-8 w-8 shrink-0 items-center justify-center rounded-full border">
          <Icon size={17} />
        </div>
        <div>
          <h3 className="agenthub-strong text-sm font-semibold">{title}</h3>
          <p className="agenthub-muted mt-0.5 text-xs leading-5">{description}</p>
        </div>
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function FieldLabel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="agenthub-muted text-xs font-medium">{label}</span>
      {children}
    </label>
  );
}

function StatusBadge({ ready, label }: { ready: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
      ready ? "agenthub-status-success" : "agenthub-status-warning"
    }`}>
      {ready ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
      {label}
    </span>
  );
}

function SmallBadge({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <span className="agenthub-status inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs">
      <Icon size={14} />
      {label}
    </span>
  );
}

function StatusLine({ ok, text }: { ok: boolean; text: string }) {
  return (
    <div className={`flex items-center gap-2 text-xs ${ok ? "text-[color:var(--ah-success)]" : "text-[color:var(--ah-warning)]"}`}>
      {ok ? <CheckCircle2 size={14} /> : <CircleDot size={14} />}
      {text}
    </div>
  );
}

