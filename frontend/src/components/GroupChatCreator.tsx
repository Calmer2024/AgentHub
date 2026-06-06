/** GroupChatCreator — 群聊创建弹窗。

自动化优先: 链式协作由编排器自动触发，用户只需选择智能体。
*/

import { useState } from "react";
import { Check, Users, X } from "lucide-react";
import type { AgentConfig } from "../types";
import { AgentAvatar } from "./AgentAvatar";

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
    <div className="agenthub-backdrop fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="agenthub-modal max-h-[90vh] w-full max-w-sm overflow-y-auto rounded-3xl border p-5">
        <div className="mb-1 flex items-center gap-2">
          <span className="agenthub-soft flex h-9 w-9 items-center justify-center rounded-full border">
            <Users size={17} />
          </span>
          <h2 className="agenthub-strong text-lg font-semibold">新建群聊</h2>
        </div>
        <p className="agenthub-muted mb-3 text-xs">
          选择 2-5 个智能体，编排器自动编排协作
        </p>

        <input value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="群聊名称（可选）"
          className="agenthub-composer agenthub-textarea agenthub-focus-ring mb-3 w-full rounded-2xl border px-3 py-2 text-sm"
        />

        <div className="max-h-48 overflow-y-auto space-y-1 mb-4">
          {agents.map((a) => (
            <label key={a.id} className={`flex cursor-pointer items-center gap-2 rounded-2xl px-3 py-2 transition-colors ${selected.has(a.id) ? "agenthub-nav-active" : "agenthub-nav-idle"}`}>
              <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggle(a.id)}
                className="h-4 w-4 rounded accent-[color:var(--ah-accent-strong)]" />
              <AgentAvatar agent={a} size="sm" />
              <div className="min-w-0">
                <p className="agenthub-strong truncate text-sm font-medium">{a.name}</p>
                <p className="agenthub-muted truncate text-xs">{a.description || `${a.cliTool} · ${a.executable ?? "未配置"}`}</p>
              </div>
            </label>
          ))}
        </div>

        <div className="flex gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="agenthub-icon-button inline-flex flex-1 items-center justify-center gap-1.5 rounded-full py-2.5 text-sm"
          >
            <X size={15} />
            取消
          </button>
          <button
            type="button"
            onClick={() => onConfirm(title, selectedList)}
            disabled={!canCreate}
            className="agenthub-primary-button inline-flex flex-1 items-center justify-center gap-1.5 rounded-full py-2.5 text-sm disabled:cursor-not-allowed disabled:opacity-50">
            <Check size={15} />
            创建 ({selected.size})
          </button>
        </div>
      </div>
    </div>
  );
}
