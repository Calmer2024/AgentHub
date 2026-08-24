import {
  AlertCircle,
  ArrowLeft,
  BookOpenText,
  CheckCircle2,
  CircleDot,
  IdCard,
  KeyRound,
  LayoutTemplate,
  Loader2,
  Play,
  ScrollText,
  ServerCog,
  ShieldCheck,
  Terminal,
  Upload,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
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
import { AgentAvatar, CUSTOM_AGENT_DEFAULT_AVATAR } from "./AgentAvatar";
import { AGENT_TEMPLATE_PRESETS, type AgentTemplatePreset } from "./AgentTemplatePresets";

const CLI_TOOL_OPTIONS: UiSelectOption[] = [
  { value: "claude_code", label: "Claude Code" },
  { value: "codex", label: "Codex" },
  { value: "opencode", label: "OpenCode" },
  { value: "custom", label: "自定义" },
];

const CONTEXT_POLICY_OPTIONS: UiSelectOption[] = [
  { value: "workspace_coding", label: "工作区编码", description: "读取项目上下文并允许工作区编辑" },
  { value: "planning_only", label: "仅规划", description: "仅用于计划、拆解和调度" },
  { value: "review_only", label: "仅审查", description: "侧重审查、测试和验收" },
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
    apiKeyPlaceholder: "填写 Anthropic 或中转服务 API 密钥",
  },
  codex: {
    label: "Codex",
    defaultProviderType: "official",
    defaultProviderId: "OpenAI",
    defaultProviderName: "OpenAI",
    defaultBaseUrl: "https://api.openai.com/v1",
    defaultAuthEnvKey: "OPENAI_API_KEY",
    apiKeyLabel: "OpenAI / 中转密钥",
    apiKeyPlaceholder: "填写 OpenAI 或中转服务 API 密钥",
  },
  opencode: {
    label: "OpenCode",
    defaultProviderType: "official",
    defaultProviderId: "openai",
    defaultProviderName: "OpenAI",
    defaultBaseUrl: "https://api.openai.com/v1",
    defaultAuthEnvKey: "OPENAI_API_KEY",
    apiKeyLabel: "OpenCode 提供方密钥",
    apiKeyPlaceholder: "填写官方、兼容中转或自定义提供方 API 密钥",
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
  presentation = "page",
  onSave,
  onCancel,
}: {
  initial?: AgentConfig;
  runtimeScope?: "local" | "cloud";
  presentation?: "page" | "dialog";
  onSave: (data: AgentConfigCreate) => Promise<void>;
  onCancel: () => void;
}) {
  const defaultCliTool = initial?.cliTool ?? (runtimeScope === "cloud" ? "codex" : "claude_code");
  const [cliTool, setCliTool] = useState<CliTool>(defaultCliTool);
  const preset = CLI_PRESETS[cliTool];
  const [name, setName] = useState(initial?.name ?? (runtimeScope === "cloud" ? "自定义智能体" : preset.name));
  const [note, setNote] = useState(initial?.description ?? (runtimeScope === "cloud" ? "使用云端 CLI 的自定义智能体" : preset.description));
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
  const [formDirty, setFormDirty] = useState(false);
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
  const formGridClass = "grid items-start gap-0";
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
    // 编辑已有 Agent 时，切换 CLI 只应更换执行器相关配置；
    // 名称、描述、提示词、规则、工具集和上下文策略属于 Agent Profile，不能被重置。
    // 只有完全空白的新建本地 Agent 才使用 CLI 的默认资料。
    // 已编辑的 Agent，以及已经套用模板的新建 Agent，都必须保留 Profile。
    if (runtimeScope === "local" && !initial && !selectedTemplateName) {
      setName(nextPreset.name);
      setNote(nextPreset.description);
      setSystemPrompt("");
      setRules("");
      setAvatar(defaultAvatarForTool(next));
      setToolset([]);
      setContextPolicy("workspace_coding");
    } else {
      setName((current) => current.trim() || "自定义智能体");
      setNote((current) => current.trim() || `使用 ${nextPreset.name} CLI 的自定义智能体`);
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
  };

  const applyTemplate = (template: AgentTemplatePreset) => {
    const defaultPreset = CLI_PRESETS.claude_code;
    setSelectedTemplateName(template.name);
    setCliTool("claude_code");
    setName(template.name);
    setNote(template.description);
    setSystemPrompt(template.systemPrompt);
    setRules(template.rules);
    setToolset(template.toolset);
    setContextPolicy(template.contextPolicy);
    setAvatar(template.avatar);
    setExecutable(defaultPreset.executable);
    setArgsText(defaultPreset.initArgs.join(" "));
    setEnvText(formatEnv(defaultPreset.envVars));
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

  const handleSave = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setFormError(null);
    try {
      if (runtimeScope === "cloud" && cloudCredentialMeta && isCliCredentialTool(cliTool)) {
        if (!cloudApiKey.trim() && !cloudCredentialConfigured) {
          setFormError(`请先填写 ${cloudCredentialMeta.label} API 密钥`);
          setSaving(false);
          return;
        }
        if (/^https?:\/\//i.test(cloudApiKey.trim())) {
          setFormError("API 密钥不能填写网址，请填写供应商控制台生成的密钥");
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
      setFormDirty(false);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const autosaveSignature = JSON.stringify({
    name, note, systemPrompt, rules, avatar, toolset, contextPolicy, cliTool,
    executable, argsText, envText, codexConnection, codexBaseUrl, codexModel,
    codexApiKey, codexProviderId, codexProviderName, codexUseChatgptAuth,
    cloudProviderKey, cloudProviderType, cloudProviderId, cloudProviderName,
    cloudBaseUrl, cloudModel, cloudAuthEnvKey, cloudApiKey, cloudCodexReviewModel,
    cloudCodexReasoningEffort, cloudCodexWireApi, cloudCodexNetworkAccess,
    cloudCodexRequiresOpenaiAuth,
  });
  const initialAutosaveSignature = useRef(autosaveSignature);

  useEffect(() => {
    if (!initial || !formDirty || autosaveSignature === initialAutosaveSignature.current || !name.trim()) return;
    const timer = window.setTimeout(() => { void handleSave(); }, 700);
    return () => window.clearTimeout(timer);
    // The serialized signature intentionally owns the debounce boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autosaveSignature, formDirty]);

  const sectionLinks: { id: string; label: string; icon: LucideIcon }[] = [
    ...(!initial && !isBuiltinCloudEngine ? [{ id: "agent-template", label: "模板", icon: LayoutTemplate }] : []),
    { id: "agent-profile", label: "智能体", icon: IdCard },
    ...(!isBuiltinCloudEngine ? [
      { id: "agent-rules", label: "身份与规则", icon: BookOpenText },
      { id: "agent-capabilities", label: "能力配置", icon: Wrench },
    ] : []),
    ...(runtimeScope === "cloud" && cloudCredentialMeta ? [{ id: "agent-credentials", label: "CLI 凭据", icon: KeyRound }] : []),
    ...(runtimeScope === "local" ? [{ id: "agent-command", label: "启动命令", icon: Terminal }] : []),
    ...(runtimeScope === "local" && cliTool === "codex" ? [{ id: "agent-codex", label: "Codex 模型连接", icon: ServerCog }] : []),
    ...(runtimeScope === "local" ? [{ id: "agent-env", label: "高级环境变量", icon: ScrollText }] : []),
  ];
  const [activeSectionId, setActiveSectionId] = useState("agent-profile");

  return (
    <div className={`agenthub-agent-settings agenthub-agent-settings-${presentation} flex h-full min-h-0 w-full`}>
      <aside className="agenthub-agent-settings-nav flex w-56 shrink-0 flex-col px-4 py-5">
        <div className="mb-5">
          <button type="button" onClick={onCancel} className="agenthub-agent-settings-back flex min-h-10 w-full items-center gap-2 rounded-[10px] px-2 text-left text-sm" aria-label={presentation === "dialog" ? "关闭配置" : "返回"} title={presentation === "dialog" ? "关闭配置" : "返回"}>
            {presentation === "dialog" ? <X size={17} aria-hidden="true" /> : <ArrowLeft size={17} aria-hidden="true" />}
            <span>{presentation === "dialog" ? "关闭" : "返回"}</span>
          </button>
        </div>
        <nav className="space-y-1" aria-label="配置分区">
          {sectionLinks.map((item) => {
            const Icon = item.icon;
            return (
              <a
                key={item.id}
                href={`#${item.id}`}
                data-active={activeSectionId === item.id}
                onClick={(event) => {
                  event.preventDefault();
                  setActiveSectionId(item.id);
                  document.getElementById(item.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
                className="agenthub-agent-settings-link flex items-center gap-2.5 rounded-[10px] px-3 py-2.5 text-sm"
              >
                <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
                <span>{item.label}</span>
              </a>
            );
          })}
        </nav>
        {presentation === "page" && (
          <div className="agenthub-faint mt-auto px-3 pt-4 text-xs" aria-live="polite">
            {saving ? "正在同步" : formError ? "同步失败" : "提示：修改自动生效"}
          </div>
        )}
      </aside>
      <div className="agenthub-agent-settings-content flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
      <form
        id="agent-cli-form"
        onSubmit={(event) => { event.preventDefault(); void handleSave(); }}
        onChangeCapture={() => setFormDirty(true)}
        onClickCapture={(event) => {
          const target = event.target;
          if (target instanceof Element && target.closest(".agenthub-select-option")) setFormDirty(true);
        }}
        className="mx-auto w-full max-w-5xl px-10 py-6"
      >
          {formError && (
            <div className="agenthub-status-error mb-3 flex items-center gap-2 rounded-[10px] px-3 py-2 text-xs leading-5">
              <AlertCircle size={15} aria-hidden="true" />{formError}
            </div>
          )}
          <div data-testid="agent-cli-form-grid" className={formGridClass}>
            {!initial && !isBuiltinCloudEngine && (
              <div className="lg:col-span-2">
                <ConfigSection id="agent-template" title="模板" description="选择后会预填身份、规则和工具集">
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {AGENT_TEMPLATE_PRESETS.map((template) => {
                      const selected = selectedTemplateName === template.name;
                      return (
                        <button
                          key={template.name}
                          type="button"
                          onClick={() => applyTemplate(template)}
                          className={`agenthub-template-card agenthub-soft flex min-h-[82px] items-center gap-3 rounded-[12px] px-3 py-2.5 text-left transition ${
                            selected ? "agenthub-template-card-selected" : ""
                          }`}
                        >
                          <AgentAvatar agent={{ name: template.name, cliTool: "codex", status: "ready", avatar: template.avatar }} size="md" />
                          <span className="min-w-0">
                            <span className="agenthub-strong block text-sm font-medium">{template.name}</span>
                            <span className="agenthub-muted mt-1 line-clamp-2 text-xs leading-5">{template.description}</span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </ConfigSection>
              </div>
            )}

            <div className={isBuiltinCloudEngine ? "" : "lg:col-span-2"}>
            <ConfigSection id="agent-profile" title="智能体" description="设置在对话和好友列表中展示的信息">
              <div className="agenthub-agent-profile-editor">
                {isBuiltinCloudEngine ? (
                  <div className="agenthub-agent-profile-avatar">
                    <AgentAvatar
                      agent={{ name: name || "智能体", cliTool, status: "ready", avatar: "" }}
                      size="lg"
                    />
                  </div>
                ) : (
                  <label className="agenthub-agent-profile-avatar group/avatar cursor-pointer">
                    <AgentAvatar agent={{ name: name || "智能体", cliTool, status: "ready", avatar }} size="lg" className="agenthub-agent-profile-avatar-image" />
                    <span className="agenthub-agent-profile-upload absolute inset-0 hidden items-center justify-center rounded-full text-xs group-hover/avatar:flex">
                      <Upload size={14} aria-hidden="true" />
                    </span>
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
                )}
                <div className="min-w-0 flex-1 space-y-3">
              <FieldLabel label="名称">
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
                </div>
              </div>
            </ConfigSection>
            </div>

            {!isBuiltinCloudEngine && (
            <div className="lg:col-span-2">
                <ConfigSection id="agent-rules" title="身份与规则" description="系统提示词定义身份和业务边界，行为规则定义长期原则">
                <FieldLabel label="系统提示词">
                  <textarea
                    value={systemPrompt}
                    onChange={(event) => setSystemPrompt(event.target.value)}
                    rows={5}
                    placeholder="例如：你是家庭资产管理项目的系统架构师，只负责技术方案、模块边界、数据模型和接口契约。"
                    className={`${inputClass} min-h-[140px] resize-y leading-5`}
                  />
                </FieldLabel>
                <FieldLabel label="行为规则">
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
            <div className="lg:col-span-2">
            <ConfigSection id="agent-capabilities"
              title="能力配置"
              description={runtimeScope === "local" ? "工具集来自本机技能，CLI 负责实际执行" : "工具集由云端工作区加载，CLI 由云端运行时调度"}
            >
              <FieldLabel label="CLI 类型">
                <UiSelect
                  ariaLabel="CLI 类型"
                  value={cliTool}
                  options={CLI_TOOL_OPTIONS}
                  disabled={isBuiltinCloudEngine}
                  onValueChange={(next) => selectTool(next as CliTool)}
                />
              </FieldLabel>
              <FieldLabel label="工具集">
                {skills.length === 0 ? (
                  <div className="agenthub-soft rounded-2xl border px-3 py-3 text-xs leading-5">
                    {runtimeScope === "local" ? "未发现本机技能。" : "未发现可用技能。"}可以先留空，智能体会仅按系统提示词、行为规则和当前任务工作。
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
            </div>
            )}

            {runtimeScope === "cloud" && cloudCredentialMeta && (
              <ConfigSection id="agent-credentials"
                title="CLI 凭据"
                description={`${cloudCredentialMeta.label} 的 API 密钥、提供方和中转配置会保存到当前用户`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge
                    ready={cloudCredentialConfigured}
                    label={cloudCredentialConfigured ? "已配置" : "需要 API 密钥"}
                  />
                  {cloudCredentialLoading && <SmallBadge icon={Loader2} label="加载中" />}
                </div>
                {cloudCredentialStatus && (
                  <div className="agenthub-status-warning rounded-2xl border px-3 py-2 text-xs leading-5">
                    {cloudCredentialStatus}
                  </div>
                )}
                <div className="grid gap-3">
                  <FieldLabel label="提供方">
                    <UiSelect
                      ariaLabel={`${cloudCredentialMeta.label} 提供方`}
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
                          <span>找不到模型时可直接填写提供方文档中的模型标识。</span>
                        </div>
                      )}
                    </div>
                  </FieldLabel>
                  {codexCustomProvider && (
                    <div className="grid gap-3 rounded-2xl border border-[color:var(--ah-border)] p-3">
                      <div className="agenthub-muted text-xs font-medium">Codex config.toml 关键配置</div>
                      <div className="grid gap-3 lg:grid-cols-2">
                        <FieldLabel label="提供方标识">
                          <input
                            value={cloudProviderId}
                            onChange={(event) => setCloudProviderId(event.target.value)}
                            placeholder="OpenAI"
                            className={inputClass}
                          />
                        </FieldLabel>
                        <FieldLabel label="提供方名称">
                          <input
                            value={cloudProviderName}
                            onChange={(event) => setCloudProviderName(event.target.value)}
                            placeholder="OpenAI"
                            className={inputClass}
                          />
                        </FieldLabel>
                        <FieldLabel label="服务地址">
                          <input
                            value={cloudBaseUrl}
                            onChange={(event) => setCloudBaseUrl(event.target.value)}
                            placeholder="https://your-relay.example.com"
                            className={inputClass}
                          />
                        </FieldLabel>
                        <FieldLabel label="环境变量名">
                          <input
                            value={cloudAuthEnvKey}
                            onChange={(event) => setCloudAuthEnvKey(event.target.value)}
                            placeholder="OPENAI_API_KEY"
                            className={inputClass}
                          />
                        </FieldLabel>
                        <FieldLabel label="响应接口">
                          <UiSelect
                            ariaLabel="Codex 响应接口"
                            value={cloudCodexWireApi}
                            options={[{ value: "responses", label: "responses" }]}
                            onValueChange={setCloudCodexWireApi}
                          />
                        </FieldLabel>
                        <FieldLabel label="审查模型">
                          <input
                            value={cloudCodexReviewModel}
                            onChange={(event) => setCloudCodexReviewModel(event.target.value)}
                            placeholder={cloudModel || "gpt-5.5"}
                            className={inputClass}
                          />
                        </FieldLabel>
                        <FieldLabel label="推理强度">
                          <UiSelect
                            ariaLabel="Codex 推理强度"
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
                        <FieldLabel label="网络访问">
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
                          <span className="min-w-0 flex-1">需要 OpenAI 身份验证</span>
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
                    保存后密钥进入云端密钥库，运行时会按当前用户和项目注入对应 CLI，智能体配置不会保存明文密钥。
                  </span>
                </div>
              </ConfigSection>
            )}

            {runtimeScope === "local" && (
            <div className="lg:col-span-2">
            <ConfigSection id="agent-command" title="启动命令" description="AgentHub 会在项目工作区里启动这个命令行工具">
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
            </div>
            )}

            {runtimeScope === "local" && cliTool === "codex" && (
              <div className="lg:col-span-2">
                <ConfigSection id="agent-codex" title="Codex 模型连接" description="支持官方 OpenAI API 与 OpenAI 兼容中转服务">
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
                    <FieldLabel label="提供方名称">
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
                      保存后 AgentHub 会把凭据写入本机 Codex .env，并让 Codex 通过本机凭据读取器按需读取，不会存进智能体配置。
                    </span>
                  </div>
                </ConfigSection>
              </div>
            )}

            {runtimeScope === "local" && (
            <div className="lg:col-span-2">
              <ConfigSection id="agent-env" title="高级环境变量" description="仅用于非密钥类命令行覆盖，密钥会被过滤">
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
        </div>
        {presentation === "dialog" && (
          <footer className="flex shrink-0 items-center justify-end gap-2 px-6 py-4">
            <button type="button" onClick={onCancel} disabled={saving} className="agenthub-icon-button min-h-10 rounded-[10px] px-5 text-sm disabled:opacity-50">
              取消
            </button>
            <button type="submit" form="agent-cli-form" disabled={saving || !name.trim()} className="agenthub-primary-button min-h-10 rounded-[10px] px-5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50">
              {saving ? "正在添加" : "确定添加"}
            </button>
          </footer>
        )}
      </div>
    </div>
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

const inputClass = "agenthub-composer agenthub-textarea agenthub-focus-ring w-full rounded-[10px] px-3 py-2 text-sm leading-5 placeholder:text-[color:var(--ah-faint)]";

function ConfigSection({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="agenthub-config-section scroll-mt-4 space-y-4 py-6">
      <div>
          <h3 className="agenthub-strong text-base font-semibold leading-6">{title}</h3>
          <p className="agenthub-muted mt-0.5 text-xs leading-5">{description}</p>
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function FieldLabel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="agenthub-setting-field grid items-start gap-2">
      <span className="agenthub-muted text-sm font-medium leading-5">{label}</span>
      <span className="min-w-0">{children}</span>
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

