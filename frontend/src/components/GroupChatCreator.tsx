import { useState } from "react";
import type { AgentConfig } from "../types";

interface Props {
  agents: AgentConfig[];
  onConfirm: (title: string, selectedIds: string[], chainConfig?: ChainConfig) => void;
  onCancel: () => void;
}

export interface ChainConfig {
  enabled: boolean;
  producerId: string;
  reviewerId: string;
}

export function GroupChatCreator({ agents, onConfirm, onCancel }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState("");
  const [chainEnabled, setChainEnabled] = useState(false);
  const [producerId, setProducerId] = useState("");
  const [reviewerId, setReviewerId] = useState("");

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const selectedList = [...selected];
  const canCreate = selectedList.length >= 2 && selectedList.length <= 5;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6 max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">新建群聊</h2>
        <p className="text-xs text-gray-500 mb-3">选择 2-5 个 Agent</p>

        <input value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="群聊名称（可选）"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <div className="max-h-48 overflow-y-auto space-y-1 mb-4">
          {agents.map((a) => (
            <label key={a.id} className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${selected.has(a.id) ? "bg-blue-50" : "hover:bg-gray-50"}`}>
              <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggle(a.id)}
                className="w-4 h-4 text-blue-600 rounded" />
              <div>
                <p className="text-sm font-medium text-gray-900">{a.name}</p>
                <p className="text-xs text-gray-400">{a.provider}/{a.model}</p>
              </div>
            </label>
          ))}
        </div>

        {/* 链式协作管线配置 */}
        {selectedList.length >= 2 && (
          <div className="border-t border-gray-100 pt-3 mb-4">
            <label className="flex items-center gap-2 cursor-pointer mb-3">
              <input type="checkbox" checked={chainEnabled} onChange={(e) => setChainEnabled(e.target.checked)}
                className="w-4 h-4 text-indigo-600 rounded" />
              <span className="text-sm font-medium text-gray-700">启用链式协作（A 产出 → B 审查）</span>
            </label>

            {chainEnabled && (
              <div className="space-y-2 pl-6">
                <div>
                  <label className="text-xs text-gray-500">产出 Agent</label>
                  <select value={producerId} onChange={(e) => setProducerId(e.target.value)}
                    className="w-full mt-0.5 px-2 py-1.5 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <option value="">选择...</option>
                    {selectedList.map((id) => {
                      const a = agents.find((ag) => ag.id === id);
                      return a ? <option key={id} value={id}>{a.name}</option> : null;
                    })}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-500">审查 Agent</label>
                  <select value={reviewerId} onChange={(e) => setReviewerId(e.target.value)}
                    className="w-full mt-0.5 px-2 py-1.5 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <option value="">选择...</option>
                    {selectedList.map((id) => {
                      const a = agents.find((ag) => ag.id === id);
                      return a && id !== producerId ? <option key={id} value={id}>{a.name}</option> : null;
                    })}
                  </select>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3">
          <button onClick={onCancel} className="flex-1 py-2.5 text-gray-600 border border-gray-300 rounded-xl hover:bg-gray-50 text-sm">取消</button>
          <button
            onClick={() => onConfirm(title, selectedList,
              chainEnabled && producerId && reviewerId
                ? { enabled: true, producerId, reviewerId }
                : undefined
            )}
            disabled={!canCreate}
            className="flex-1 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm">
            创建 ({selected.size})
          </button>
        </div>
      </div>
    </div>
  );
}
