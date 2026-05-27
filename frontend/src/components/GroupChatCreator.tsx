import { useState } from "react";
import type { AgentConfig } from "../types";

interface Props {
  agents: AgentConfig[];
  onConfirm: (selectedIds: string[]) => void;
  onCancel: () => void;
}

export function GroupChatCreator({ agents, onConfirm, onCancel }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState("");

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">新建群聊</h2>
        <p className="text-xs text-gray-500 mb-3">选择 2-5 个 Agent</p>

        <input value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="群聊名称（可选）"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <div className="max-h-60 overflow-y-auto space-y-1 mb-4">
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

        <div className="flex gap-3">
          <button onClick={onCancel} className="flex-1 py-2.5 text-gray-600 border border-gray-300 rounded-xl hover:bg-gray-50 text-sm">取消</button>
          <button onClick={() => onConfirm([...selected])} disabled={selected.size < 2 || selected.size > 5}
            className="flex-1 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm">
            创建 ({selected.size})
          </button>
        </div>
      </div>
    </div>
  );
}
