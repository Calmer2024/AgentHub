/** GroupChatCreator — 群聊创建弹窗。

自动化优先: 链式协作由编排器自动触发，用户只需选择智能体。
*/

import { useMemo, useState } from "react";
import { Check, Users, X } from "lucide-react";
import type { AgentConfig } from "../types";
import { AgentAvatar } from "./AgentAvatar";

const MAX_GROUP_AGENTS = 12;

interface Props {
  agents: AgentConfig[];
  onConfirm: (title: string, selectedIds: string[]) => void;
  onCancel: () => void;
}

export function GroupChatCreator({ agents, onConfirm, onCancel }: Props) {
  const defaultSelected = useMemo(
    () => agents.filter((agent) => agent.primarySkill === "orchestrator_planner").map((agent) => agent.id),
    [agents],
  );
  const [selected, setSelected] = useState<Set<string>>(new Set(defaultSelected));
  const [title, setTitle] = useState("");

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const selectedList = [...selected];
  const canCreate = selectedList.length >= 2 && selectedList.length <= MAX_GROUP_AGENTS;

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
          默认带上调度器；在群聊中 @调度器 生成计划，普通消息仍按群聊协作处理。最多选择 {MAX_GROUP_AGENTS} 个 Agent。
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
                <p className="agenthub-muted truncate text-xs">
                  {a.primarySkill === "orchestrator_planner"
                    ? "调度器 · @它生成 draft plan"
                    : a.description || `${a.cliTool} · ${a.executable ?? "未配置"}`}
                </p>
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
            {selected.size > MAX_GROUP_AGENTS ? `最多 ${MAX_GROUP_AGENTS} 个` : `创建 (${selected.size})`}
          </button>
        </div>
      </div>
    </div>
  );
}
