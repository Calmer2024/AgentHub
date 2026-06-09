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
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import type { AgentConfig, AgentConfigCreate, SkillDefinition } from "../types";
import { checkAgentExecutable, fetchCodexLocalConfig, fetchSkills, updateCodexLocalConfig } from "../api/client";
import {
  CLI_PRESETS,
  isBlockedAgentEnvKey,
  type CliTool,
} from "./AgentCliPresets";
import { UiSelect, type UiSelectOption } from "./UiSelect";
import { AgentAvatar, AGENT_AVATAR_PRESETS } from "./AgentAvatar";
import { AGENT_TEMPLATE_PRESETS, type AgentTemplatePreset } from "./AgentTemplatePresets";

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
  const [cliTool, setCliTool] = useState<CliTool>(initial?.cliTool ?? "claude_code");
  const preset = CLI_PRESETS[cliTool];
  const [name, setName] = useState(initial?.name ?? preset.name);
  const [note, setNote] = useState(initial?.description ?? preset.description);
  const [systemPrompt, setSystemPrompt] = useState(initial?.systemPrompt ?? "");
  const [rules, setRules] = useState(initial?.rules ?? "");
  const [avatar, setAvatar] = useState(initial?.avatar || "preset:blue");
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
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [selectedTemplateName, setSelectedTemplateName] = useState<string | null>(null);

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

  const selectTool = (next: CliTool) => {
    const nextPreset = CLI_PRESETS[next];
    setCliTool(next);
    setName(nextPreset.name);
    setNote(nextPreset.description);
    setSystemPrompt("");
    setRules("");
    setExecutable(nextPreset.executable);
    setToolset([]);
    setContextPolicy("workspace_coding");
    setArgsText(nextPreset.initArgs.join(" "));
    setEnvText(formatEnv(nextPreset.envVars));
    setCodexConnection("proxy");
    setCodexBaseUrl("");
    setCodexModel("");
    setCodexApiKey("");
    setCodexProviderId("agenthub_proxy");
    setCodexProviderName("AgentHub Codex Proxy");
    setCodexUseChatgptAuth(true);
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
        executable: runtimeScope === "local" ? executable.trim() : null,
        initArgs: runtimeScope === "local" ? parseArgs(argsText) : [],
        envVars: runtimeScope === "local" ? parseEnv(envText, cliTool) : {},
        toolset,
        contextPolicy,
        avatar,
      });
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="agenthub-backdrop fixed inset-0 z-50 flex items-center justify-center px-3 py-4">
      <form
        onSubmit={handleSubmit}
        className="agenthub-modal flex max-h-[92dvh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border"
      >
        <div className="agenthub-header flex items-center justify-between gap-4 border-b px-5 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <AgentAvatar
              agent={{ name: name || "Agent", cliTool, status: "ready", avatar }}
              size="md"
            />
            <div className="min-w-0">
              <h2 className="agenthub-strong truncate text-base font-semibold">
                {initial ? "智能体设置" : runtimeScope === "local" ? "添加命令行智能体" : "添加云端智能体"}
              </h2>
              <p className="agenthub-muted truncate text-xs">
                {runtimeScope === "local" ? "身份 + 工具集 + 本机运行参数" : "身份 + 工具集 + 云端运行策略"}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="agenthub-icon-button flex h-9 w-9 items-center justify-center rounded-full"
            aria-label="关闭设置"
            title="关闭设置"
          >
            <X size={18} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="grid items-start gap-4 lg:grid-cols-2">
            {!initial && (
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

            <div className="lg:col-span-2">
            <ConfigSection icon={Settings2} title="基础信息" description="设置用户可见的智能体身份">
              <FieldLabel label="头像">
                <div className="flex flex-wrap items-center gap-2">
                  {AGENT_AVATAR_PRESETS.slice(0, 6).map((presetAvatar) => {
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
              </FieldLabel>
              <FieldLabel label="显示名称">
                <input value={name} onChange={(event) => setName(event.target.value)} required className={inputClass} />
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

            <div className="lg:col-span-2">
              {runtimeScope === "local" && (
              <ConfigSection icon={SlidersHorizontal} title="高级环境变量" description="仅用于非密钥类命令行覆盖，密钥会被过滤">
                <textarea
                  value={envText}
                  onChange={(event) => setEnvText(event.target.value)}
                  placeholder="KEY=VALUE"
                  rows={4}
                  className={`${inputClass} resize-none font-mono text-xs leading-5`}
                />
              </ConfigSection>
              )}
            </div>
          </div>
        </div>

        <div className="agenthub-header flex flex-col gap-3 border-t px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
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
              disabled={saving || !name.trim()}
              className="agenthub-primary-button inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              保存
            </button>
          </div>
        </div>
      </form>
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

function normalizeCodexBaseUrl(value: string, mode: string) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  if (mode !== "proxy" || /\/v1$/i.test(trimmed)) return trimmed;
  return `${trimmed}/v1`;
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
