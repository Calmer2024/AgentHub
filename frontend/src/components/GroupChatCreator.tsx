/** GroupChatCreator — 群聊创建弹窗。

自动化优先: 链式协作由 Orchestrator 自动触发，用户只需选择 Agent。
*/

import { useState } from "react";
import { Check, Users, X } from "lucide-react";
import type { AgentConfig } from "../types";

interface Props {
  agents: AgentConfig[];
  onConfirm: (title: string, selectedIds: string[]) => void;
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

  const selectedList = [...selected];
  const canCreate = selectedList.length >= 2 && selectedList.length <= 5;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6 max-h-[90vh] overflow-y-auto">
        <div className="mb-1 flex items-center gap-2">
          <Users size={18} className="text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-900">新建群聊</h2>
        </div>
        <p className="text-xs text-gray-400 mb-3">
          选择 2-5 个 Agent，Orchestrator 自动编排协作
        </p>

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
                <p className="text-xs text-gray-400">{a.description || `${a.cliTool} · ${a.executable ?? "未配置"}`}</p>
              </div>
            </label>
          ))}
        </div>

        <div className="flex gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-gray-300 py-2.5 text-sm text-gray-600 hover:bg-gray-50"
          >
            <X size={15} />
            取消
          </button>
          <button
            type="button"
            onClick={() => onConfirm(title, selectedList)}
            disabled={!canCreate}
            className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-blue-600 py-2.5 text-sm text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50">
            <Check size={15} />
            创建 ({selected.size})
          </button>
        </div>
      </div>
    </div>
  );
}
