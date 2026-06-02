export interface OrchestratorProviderOption {
  key: string;
  label: string;
  settingsApiKey: string | null;
  models: string[];
  defaultModel: string;
}

interface Props {
  providers: OrchestratorProviderOption[];
  models: Record<string, string>;
  currentProvider: string;
  currentModel: string;
  saving: boolean;
  onSelectProvider: (providerKey: string) => Promise<void>;
  onSelectModel: (model: string) => Promise<void>;
}

export function OrchestratorModelSettings({
  providers, models, currentProvider, currentModel, saving,
  onSelectProvider, onSelectModel,
}: Props) {
  const selected = providers.find((p) => p.key === currentProvider) ?? providers[0];
  const baseModels = selected?.models ?? [];
  const selectedModels = currentModel && !baseModels.includes(currentModel)
    ? [currentModel, ...baseModels]
    : baseModels.length ? baseModels : [currentModel].filter(Boolean);
  const configured = Boolean(selected && selected.settingsApiKey !== null);

  return (
    <section className="p-4 border border-blue-200 rounded-xl bg-blue-50/60">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-9 h-9 rounded-lg bg-blue-600 text-white flex items-center justify-center text-sm font-semibold">
          O
        </div>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-gray-900">Orchestrator 中枢</h2>
          <p className="text-xs text-gray-500 truncate">
            {selected?.label ?? currentProvider} · {currentModel || models[currentProvider] || selected?.defaultModel}
          </p>
        </div>
        <span className={`ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${
          configured ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${configured ? "bg-green-500" : "bg-amber-500"}`} />
          {configured ? "可用" : "未配置 Key"}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2">
        <label className="text-xs text-gray-500">
          供应商
          <select
            value={currentProvider}
            onChange={(e) => onSelectProvider(e.target.value)}
            disabled={saving}
            className="w-full mt-1 px-2 py-1.5 border border-blue-200 rounded-lg text-xs bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {providers.map((p) => (
              <option key={p.key} value={p.key}>{p.label}</option>
            ))}
          </select>
        </label>

        <label className="text-xs text-gray-500">
          模型
          <select
            value={currentModel || models[currentProvider] || selected?.defaultModel || ""}
            onChange={(e) => onSelectModel(e.target.value)}
            disabled={saving || selectedModels.length === 0}
            className="w-full mt-1 px-2 py-1.5 border border-blue-200 rounded-lg text-xs bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {selectedModels.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </label>
      </div>
    </section>
  );
}
