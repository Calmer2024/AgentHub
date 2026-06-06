import {
  AlertCircle,
  Bot,
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

export function AgentCliForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: AgentConfig;
  onSave: (data: AgentConfigCreate) => Promise<void>;
  onCancel: () => void;
}) {
  const [cliTool, setCliTool] = useState<CliTool>(initial?.cliTool ?? "claude_code");
  const preset = CLI_PRESETS[cliTool];
  const [name, setName] = useState(initial?.name ?? preset.name);
  const [note, setNote] = useState(initial?.description ?? preset.description);
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  const [primarySkill, setPrimarySkill] = useState(initial?.primarySkill ?? "general_coding");
  const [auxiliarySkills, setAuxiliarySkills] = useState<string[]>(initial?.auxiliarySkills ?? ["workspace_editing"]);
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

  useEffect(() => {
    let cancelled = false;
    fetchSkills()
      .then((items) => { if (!cancelled) setSkills(items); })
      .catch(() => { if (!cancelled) setSkills([]); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (cliTool !== "codex") return;
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
  }, [cliTool]);

  const selectTool = (next: CliTool) => {
    const nextPreset = CLI_PRESETS[next];
    setCliTool(next);
    setName(nextPreset.name);
    setExecutable(nextPreset.executable);
    setPrimarySkill("general_coding");
    setAuxiliarySkills(["workspace_editing"]);
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
    if (!executable.trim()) return;
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
      if (cliTool === "codex") {
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
        systemPrompt: "",
        agentType: "cli_wrapper",
        cliTool,
        executable: executable.trim(),
        initArgs: parseArgs(argsText),
        envVars: parseEnv(envText, cliTool),
        primarySkill,
        auxiliarySkills: auxiliarySkills.filter((skillId) => skillId !== primarySkill),
        contextPolicy,
      });
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-3 py-4 backdrop-blur-sm">
      <form
        onSubmit={handleSubmit}
        className="flex max-h-[92dvh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-white/10 bg-[#1f2024] text-[#ececf1] shadow-2xl"
      >
        <div className="flex items-center justify-between gap-4 border-b border-white/10 px-5 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#3a6ff7]/15 text-[#9bb7ff]">
              <Bot size={20} />
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold text-white">
                {initial ? "Agent Profile 设置" : "添加 Agent Profile"}
              </h2>
              <p className="truncate text-xs text-[#8f8f98]">Engine + Skills + 运行参数</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-[#a8abb2] hover:bg-white/[0.08] hover:text-white"
            aria-label="关闭设置"
            title="关闭设置"
          >
            <X size={18} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
            <ConfigSection icon={Settings2} title="基础信息" description="设置用户可见的 Agent 身份">
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

            <ConfigSection icon={Sparkles} title="能力配置" description="Agent = Engine + Skills">
              <FieldLabel label="CLI 类型">
                <select value={cliTool} onChange={(event) => selectTool(event.target.value as CliTool)} className={inputClass}>
                  <option value="claude_code">Claude Code</option>
                  <option value="codex">Codex</option>
                  <option value="opencode">OpenCode</option>
                  <option value="custom">自定义</option>
                </select>
              </FieldLabel>
              <FieldLabel label="主 Skill">
                <select value={primarySkill} onChange={(event) => setPrimarySkill(event.target.value)} className={inputClass}>
                  {skillOptions(skills).map((skill) => (
                    <option key={skill.id} value={skill.id}>{skill.name}</option>
                  ))}
                </select>
              </FieldLabel>
              <FieldLabel label="辅助 Skills">
                <div className="grid gap-2 sm:grid-cols-2">
                  {skillOptions(skills).filter((skill) => skill.id !== primarySkill).map((skill) => (
                    <label key={skill.id} className="flex min-w-0 items-center gap-2 rounded-lg border border-white/10 bg-[#25262a] px-3 py-2 text-xs text-[#d8d8df]">
                      <input
                        type="checkbox"
                        checked={auxiliarySkills.includes(skill.id)}
                        onChange={() => setAuxiliarySkills((current) => toggleSkill(current, skill.id))}
                        className="h-4 w-4 shrink-0 accent-[#3a6ff7]"
                      />
                      <span className="min-w-0 flex-1 truncate" title={skill.path ? `${skill.description}\n${skill.path}` : skill.description}>
                        {skill.name}
                      </span>
                      {skill.source === "filesystem" && (
                        <span className="shrink-0 rounded bg-emerald-400/10 px-1.5 py-0.5 text-[10px] text-emerald-200">
                          本机
                        </span>
                      )}
                    </label>
                  ))}
                </div>
              </FieldLabel>
              <FieldLabel label="上下文策略">
                <select value={contextPolicy} onChange={(event) => setContextPolicy(event.target.value)} className={inputClass}>
                  <option value="workspace_coding">Workspace Coding</option>
                  <option value="planning_only">Planning Only</option>
                  <option value="review_only">Review Only</option>
                </select>
              </FieldLabel>
            </ConfigSection>

            <ConfigSection icon={Terminal} title="启动命令" description="AgentHub 会在项目工作区里启动这个 CLI">
              <FieldLabel label="Executable">
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
                    className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg border border-white/10 px-3 text-sm text-[#d8d8df] hover:bg-white/[0.08] disabled:opacity-50"
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

            {cliTool === "codex" && (
              <div className="lg:col-span-2">
                <ConfigSection icon={Network} title="Codex 模型连接" description="支持官方 OpenAI API 与 OpenAI 兼容中转 API">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge ready={Boolean(codexReady)} label={codexReady ? "连接可用" : "需要配置"} />
                    {codexApiKeySet && <SmallBadge icon={ShieldCheck} label="API Key 已保存" />}
                  </div>
                  {codexStatus && (
                    <div className="rounded-lg border border-white/10 bg-black/15 px-3 py-2 text-xs leading-5 text-[#b7bbc4]">
                      {codexStatus}
                    </div>
                  )}
                  <div className="grid gap-3 lg:grid-cols-2">
                    <FieldLabel label="连接模式">
                      <select
                        value={codexConnection}
                        onChange={(event) => updateCodexConnection(event.target.value as "official" | "proxy")}
                        className={inputClass}
                      >
                        <option value="proxy">OpenAI 兼容中转 API</option>
                        <option value="official">官方 OpenAI API</option>
                      </select>
                    </FieldLabel>
                    <FieldLabel label="模型">
                      <input
                        value={codexModel}
                        onChange={(event) => setCodexModel(event.target.value)}
                        placeholder="gpt-5.5"
                        className={inputClass}
                      />
                    </FieldLabel>
                    <FieldLabel label="Base URL">
                      <input
                        value={codexBaseUrl}
                        onChange={(event) => setCodexBaseUrl(event.target.value)}
                        placeholder={codexConnection === "official" ? "https://api.openai.com/v1" : "https://sub2.example.com/v1"}
                        className={inputClass}
                      />
                    </FieldLabel>
                    <FieldLabel label={codexConnection === "proxy" ? "中转 API Key" : "OpenAI API Key"}>
                      <div className="relative">
                        <KeyRound size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#74747d]" />
                        <input
                          value={codexApiKey}
                          onChange={(event) => setCodexApiKey(event.target.value)}
                          placeholder={codexApiKeySet ? "已保存，留空则沿用" : "在这里填写，AgentHub 会写入本机 .codex/.env"}
                          type="password"
                          className={`${inputClass} pl-9`}
                        />
                      </div>
                    </FieldLabel>
                    <FieldLabel label="Provider ID">
                      <input value={codexProviderId} onChange={(event) => setCodexProviderId(event.target.value)} className={inputClass} />
                    </FieldLabel>
                    <FieldLabel label="Provider 名称">
                      <input value={codexProviderName} onChange={(event) => setCodexProviderName(event.target.value)} className={inputClass} />
                    </FieldLabel>
                  </div>
                  {codexConnection === "official" && (
                    <label className="flex items-center gap-2 rounded-lg border border-white/10 bg-[#25262a] px-3 py-2 text-xs text-[#d8d8df]">
                      <input
                        type="checkbox"
                        checked={codexUseChatgptAuth}
                        onChange={(event) => setCodexUseChatgptAuth(event.target.checked)}
                        className="h-4 w-4 accent-[#3a6ff7]"
                      />
                      使用本机 Codex 登录态
                    </label>
                  )}
                  <div className="flex items-start gap-2 rounded-lg border border-[#3a6ff7]/20 bg-[#3a6ff7]/10 px-3 py-2 text-xs leading-5 text-[#b9caff]">
                    <ServerCog size={15} className="mt-0.5 shrink-0" />
                    <span>
                      保存后 AgentHub 会把凭据写入本机 Codex .env，并让 Codex 通过本机凭据读取器按需读取；不会存进 Agent 配置。
                    </span>
                  </div>
                </ConfigSection>
              </div>
            )}

            <div className="lg:col-span-2">
              <ConfigSection icon={SlidersHorizontal} title="高级环境变量" description="仅用于非密钥类 CLI 覆盖，API Key 会被过滤">
                <textarea
                  value={envText}
                  onChange={(event) => setEnvText(event.target.value)}
                  placeholder="KEY=VALUE"
                  rows={4}
                  className={`${inputClass} resize-none font-mono text-xs leading-5`}
                />
              </ConfigSection>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-white/10 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          {formError ? (
            <div className="flex items-center gap-2 text-xs leading-5 text-red-300">
              <AlertCircle size={15} />
              {formError}
            </div>
          ) : (
            <div className="text-xs text-[#74747d]">更改会在下次启动 CLI 进程时生效</div>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="rounded-lg border border-white/10 px-4 py-2 text-sm text-[#d8d8df] hover:bg-white/[0.08]"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saving || !name.trim()}
              className="inline-flex items-center gap-2 rounded-lg bg-[#ececf1] px-4 py-2 text-sm font-medium text-[#171717] hover:bg-white disabled:opacity-50"
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

const FALLBACK_SKILLS: SkillDefinition[] = [
  { id: "general_coding", name: "通用工程师", description: "处理常规代码实现、修复和项目内工程任务。", tags: [] },
  { id: "workspace_editing", name: "Workspace 编辑", description: "负责在项目工作区中读写文件。", tags: [] },
  { id: "orchestrator_planner", name: "调度器规划", description: "只负责需求拆解、DAG 计划和 Agent 分配建议。", tags: [] },
];

function skillOptions(skills: SkillDefinition[]) {
  return skills.length > 0 ? skills : FALLBACK_SKILLS;
}

function toggleSkill(current: string[], skillId: string) {
  if (current.includes(skillId)) return current.filter((id) => id !== skillId);
  return [...current, skillId];
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

const inputClass = "w-full rounded-lg border border-white/10 bg-[#25262a] px-3 py-2 text-sm text-[#ececf1] outline-none transition focus:border-[#6f93ff]/70 focus:ring-2 focus:ring-[#3a6ff7]/25 placeholder:text-[#666a73]";

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
    <section className="space-y-3 rounded-lg border border-white/10 bg-[#202126] p-4">
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/[0.06] text-[#c9d5ff]">
          <Icon size={17} />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <p className="mt-0.5 text-xs leading-5 text-[#8f8f98]">{description}</p>
        </div>
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function FieldLabel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-[#aeb3bd]">{label}</span>
      {children}
    </label>
  );
}

function StatusBadge({ ready, label }: { ready: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs ${
      ready ? "bg-emerald-400/15 text-emerald-200" : "bg-amber-400/15 text-amber-200"
    }`}>
      {ready ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
      {label}
    </span>
  );
}

function SmallBadge({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.06] px-2.5 py-1 text-xs text-[#cfd4df]">
      <Icon size={14} />
      {label}
    </span>
  );
}

function StatusLine({ ok, text }: { ok: boolean; text: string }) {
  return (
    <div className={`flex items-center gap-2 text-xs ${ok ? "text-emerald-200" : "text-amber-200"}`}>
      {ok ? <CheckCircle2 size={14} /> : <CircleDot size={14} />}
      {text}
    </div>
  );
}
