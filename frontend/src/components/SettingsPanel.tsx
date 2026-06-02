import { useState, useEffect, useCallback, type FormEvent } from "react";
import { fetchSettings, updateSettings } from "../api/client";
import type { Provider } from "../types";
import { OrchestratorModelSettings } from "./OrchestratorModelSettings";

interface ProviderDef {
  key: string;
  label: string;
  icon: string;
  placeholder: string;
  settingsModelKey: string;
  settingsApiKey: string | null;
  models: string[];
  defaultModel: string;
}

function buildProviders(providers: Provider[], keys: Record<string, string | null>): ProviderDef[] {
  const providerMap = new Map(providers.map((p) => [p.name, p]));
  const defaults: Omit<ProviderDef, "settingsModelKey" | "settingsApiKey" | "models" | "defaultModel">[] = [
    { key: "openai", label: "OpenAI", icon: "🤖", placeholder: "sk-..." },
    { key: "claude", label: "Anthropic Claude", icon: "🧠", placeholder: "sk-ant-..." },
    { key: "deepseek", label: "DeepSeek", icon: "🔍", placeholder: "sk-..." },
    { key: "gemini", label: "Google Gemini", icon: "🌐", placeholder: "AIza..." },
    { key: "minimax", label: "MiniMax", icon: "🎯", placeholder: "eyJ..." },
    { key: "glm", label: "智谱 GLM", icon: "🏔️", placeholder: "xxx..." },
  ];
  return defaults.map((d) => ({
    ...d,
    settingsModelKey: `${d.key}Model`,
    settingsApiKey: keys[d.key] ?? null,
    models: providerMap.get(d.key)?.models ?? [],
    defaultModel: providerMap.get(d.key)?.defaultModel ?? "",
  }));
}

function maskKey(key: string | null): string | null {
  if (!key) return null;
  if (key.length <= 8) return key.slice(0, 2) + "****";
  return key.slice(0, 3) + "****" + key.slice(-3);
}

interface ProviderCardProps {
  provider: ProviderDef;
  currentModel: string;
  saving: boolean;
  onSave: (apiKey: string) => Promise<void>;
  onDelete: () => Promise<void>;
  onSelectModel: (model: string) => Promise<void>;
}

function ProviderCard({ provider, currentModel, saving, onSave, onDelete, onSelectModel }: ProviderCardProps) {
  const [editing, setEditing] = useState(false);
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const configured = provider.settingsApiKey !== null;

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!key.trim()) return;
    setError(null);
    try {
      await onSave(key.trim());
      setKey("");
      setEditing(false);
    } catch {
      setError("保存失败");
    }
  };

  return (
    <div className="p-4 border border-gray-200 rounded-xl bg-white">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-2xl">{provider.icon}</span>
        <div>
          <p className="font-medium text-gray-900 text-sm">{provider.label}</p>
        </div>
        <div className="ml-auto">
          {configured ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-100 text-green-700 rounded-full text-xs font-medium">
              <span className="w-1.5 h-1.5 bg-green-500 rounded-full" /> 已配置
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full text-xs">
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full" /> 未配置
            </span>
          )}
        </div>
      </div>

      {configured && (
        <div className="mb-2">
          <label className="text-xs text-gray-500">模型</label>
          <select
            value={currentModel}
            onChange={(e) => onSelectModel(e.target.value)}
            disabled={saving}
            className="w-full mt-0.5 px-2 py-1.5 border border-gray-300 rounded-lg text-xs bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {provider.models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
      )}

      {configured && !editing ? (
        <div className="flex items-center gap-2">
          <code className="flex-1 px-3 py-2 bg-gray-50 rounded-lg text-xs text-gray-500 font-mono truncate">
            {maskKey(provider.settingsApiKey)}
          </code>
          <button onClick={() => setEditing(true)} className="px-3 py-2 text-xs text-blue-600 hover:bg-blue-50 rounded-lg">编辑</button>
          <button onClick={onDelete} className="px-3 py-2 text-xs text-red-500 hover:bg-red-50 rounded-lg">删除</button>
        </div>
      ) : (
        <form onSubmit={handleSave} className="space-y-2">
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={configured ? "输入新 Key 覆盖" : provider.placeholder}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <div className="flex gap-2">
            <button type="submit" disabled={saving || !key.trim()}
              className="flex-1 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm">
              {saving ? "..." : configured ? "更新" : "保存"}
            </button>
            {editing && (
              <button type="button" onClick={() => { setEditing(false); setKey(""); }}
                className="px-4 py-2 text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">取消</button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

interface Props {
  providers: Provider[];
  onSaved: () => void;
}

export function SettingsPanel({ providers, onSaved }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [keys, setKeys] = useState<Record<string, string | null>>({});
  const [models, setModels] = useState<Record<string, string>>({});
  const [orchestratorProvider, setOrchestratorProvider] = useState("deepseek");
  const [orchestratorModel, setOrchestratorModel] = useState("deepseek-v4-flash");
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await fetchSettings();
      setKeys({
        openai: s.openaiApiKey, claude: s.anthropicApiKey,
        deepseek: s.deepseekApiKey, gemini: s.geminiApiKey,
        minimax: s.minimaxApiKey, glm: s.glmApiKey,
      });
      setModels({
        openai: s.openaiModel, claude: s.claudeModel,
        deepseek: s.deepseekModel, gemini: s.geminiModel,
        minimax: s.minimaxModel, glm: s.glmModel,
      });
      setOrchestratorProvider(s.orchestratorProvider);
      setOrchestratorModel(s.orchestratorModel);
    } catch {
      setError("无法加载设置");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const providerDefs = buildProviders(providers, keys);

  const keyFieldMap: Record<string, string> = {
    openai: "openaiApiKey", claude: "anthropicApiKey",
    deepseek: "deepseekApiKey", gemini: "geminiApiKey",
    minimax: "minimaxApiKey", glm: "glmApiKey",
  };

  const handleSave = async (providerKey: string, apiKey: string) => {
    setSavingKey(providerKey);
    await updateSettings({ [keyFieldMap[providerKey]]: apiKey });
    setSavingKey(null);
    await load();
    onSaved();
  };

  const handleDelete = async (providerKey: string) => {
    setSavingKey(providerKey);
    await updateSettings({ [keyFieldMap[providerKey]]: "" });
    setSavingKey(null);
    await load();
    onSaved();
  };

  const handleSelectModel = async (providerKey: string, model: string) => {
    const p = providerDefs.find((x) => x.key === providerKey);
    if (!p) return;
    await updateSettings({ [p.settingsModelKey]: model });
    await load();
  };

  const preferredModelFor = (providerKey: string) => {
    const p = providerDefs.find((x) => x.key === providerKey);
    return models[providerKey] || p?.defaultModel || p?.models[0] || "";
  };

  const handleSelectOrchestratorProvider = async (providerKey: string) => {
    const model = preferredModelFor(providerKey);
    setSavingKey("orchestrator");
    await updateSettings({ orchestratorProvider: providerKey, orchestratorModel: model });
    setSavingKey(null);
    await load();
  };

  const handleSelectOrchestratorModel = async (model: string) => {
    setSavingKey("orchestrator");
    await updateSettings({ orchestratorModel: model });
    setSavingKey(null);
    await load();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-6 h-6 border-2 border-blue-300 border-t-blue-600 rounded-full animate-spin" />
        <span className="ml-2 text-sm text-gray-400">加载中...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center">
        <p className="text-sm text-red-600 mb-3">{error}</p>
        <button onClick={load} className="text-sm text-blue-600 hover:text-blue-800 underline">重试</button>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-3">
      <OrchestratorModelSettings
        providers={providerDefs}
        models={models}
        currentProvider={orchestratorProvider}
        currentModel={orchestratorModel}
        saving={savingKey === "orchestrator"}
        onSelectProvider={handleSelectOrchestratorProvider}
        onSelectModel={handleSelectOrchestratorModel}
      />
      <h2 className="text-sm font-semibold text-gray-900 px-1">模型供应商</h2>
      <p className="text-xs text-gray-500 px-1 -mt-2 mb-1">配置 API Key 后即可在对话中选择对应模型</p>
      {providerDefs.map((p) => (
        <ProviderCard
          key={p.key}
          provider={p}
          currentModel={models[p.key] ?? ""}
          saving={savingKey === p.key}
          onSave={(k) => handleSave(p.key, k)}
          onDelete={() => handleDelete(p.key)}
          onSelectModel={(m) => handleSelectModel(p.key, m)}
        />
      ))}
    </div>
  );
}
