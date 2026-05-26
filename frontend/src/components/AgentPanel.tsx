import { useState, useEffect, useCallback } from "react";
import type { AgentConfig, AgentConfigCreate, AgentConfigUpdate, Provider } from "../types";
import { fetchAgents, createAgent, updateAgent, deleteAgent } from "../api/client";

interface Props {
  providers: Provider[];
  onChanged: () => void;
}

export function AgentPanel({ providers, onChanged }: Props) {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try { setAgents(await fetchAgents()); }
    catch { setError("加载失败"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const availableProviders = providers.filter((p) => p.isAvailable);

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Agent 管理</h2>
          <p className="text-xs text-gray-500">创建自定义 AI 智能体</p>
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700"
        >
          + 新建
        </button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-4">
          <div className="w-4 h-4 border-2 border-blue-300 border-t-blue-600 rounded-full animate-spin" />
          <span className="text-xs text-gray-400">加载中...</span>
        </div>
      ) : error ? (
        <div className="text-sm text-red-600 py-2">{error}</div>
      ) : null}

      {showNew && (
        <AgentForm
          providers={availableProviders}
          onSave={async (data) => {
            await createAgent(data);
            setShowNew(false);
            await load();
            onChanged();
          }}
          onCancel={() => setShowNew(false)}
        />
      )}

      {agents.map((agent) =>
        editingId === agent.id ? (
          <AgentForm
            key={agent.id}
            providers={availableProviders}
            initial={agent}
            onSave={async (data) => {
              await updateAgent(agent.id, data as AgentConfigUpdate);
              setEditingId(null);
              await load();
              onChanged();
            }}
            onCancel={() => setEditingId(null)}
          />
        ) : (
          <div key={agent.id} className="p-3 border border-gray-200 rounded-xl bg-white">
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm text-gray-900 truncate">{agent.name}</p>
                {agent.description && (
                  <p className="text-xs text-gray-500 mt-0.5 truncate">{agent.description}</p>
                )}
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">{agent.provider}</span>
                  <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">{agent.model}</span>
                </div>
              </div>
              <div className="flex gap-1 ml-2">
                <button onClick={() => setEditingId(agent.id)} className="px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 rounded">编辑</button>
                <button onClick={async () => { await deleteAgent(agent.id); await load(); onChanged(); }} className="px-2 py-1 text-xs text-red-500 hover:bg-red-50 rounded">删除</button>
              </div>
            </div>
          </div>
        )
      )}

      {!loading && !showNew && agents.length === 0 && (
        <div className="text-center py-8 text-sm text-gray-400">
          还没有 Agent，点击"新建"创建第一个
        </div>
      )}
    </div>
  );
}

function AgentForm({ providers, initial, onSave, onCancel }: {
  providers: Provider[];
  initial?: AgentConfig;
  onSave: (data: AgentConfigCreate) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [systemPrompt, setSystemPrompt] = useState(initial?.systemPrompt ?? "");
  const [provider, setProvider] = useState(initial?.provider ?? "deepseek");
  const [model, setModel] = useState(initial?.model ?? "deepseek-v4-flash");
  const [saving, setSaving] = useState(false);

  const selectedProvider = providers.find((p) => p.name === provider);
  const models = selectedProvider?.models ?? [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      await onSave({ name: name.trim(), description: description.trim(), systemPrompt, provider, model });
    } finally { setSaving(false); }
  };

  return (
    <form onSubmit={handleSubmit} className="p-3 border border-blue-300 rounded-xl bg-blue-50/50 space-y-2">
      <input
        value={name} onChange={(e) => setName(e.target.value)}
        placeholder="Agent 名称" required
        className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <input
        value={description} onChange={(e) => setDescription(e.target.value)}
        placeholder="描述（可选）"
        className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <textarea
        value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)}
        placeholder="系统提示词" rows={2}
        className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <div className="flex gap-2">
        <select value={provider} onChange={(e) => { setProvider(e.target.value); setModel(""); }}
          className="flex-1 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {providers.map((p) => <option key={p.name} value={p.name}>{p.displayName}</option>)}
        </select>
        <select value={model} onChange={(e) => setModel(e.target.value)}
          className="flex-1 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">选模型</option>
          {models.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={saving || !name.trim()}
          className="flex-1 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
        >{saving ? "..." : "保存"}</button>
        <button type="button" onClick={onCancel}
          className="px-4 py-1.5 text-gray-600 border border-gray-300 rounded-lg text-sm hover:bg-gray-50"
        >取消</button>
      </div>
    </form>
  );
}
