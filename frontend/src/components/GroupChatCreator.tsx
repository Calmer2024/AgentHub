/** GroupChatCreator — 群聊创建弹窗。

自动化优先: 链式协作由编排器自动触发，用户只需选择智能体。
*/

import { useEffect, useMemo, useState } from "react";
import { Check, Users, X } from "lucide-react";
import type { AgentConfig } from "../types";
import { AgentAvatar } from "./AgentAvatar";
import { GlobalModal } from "./GlobalModal";

const MAX_GROUP_AGENTS = 12;

interface Props {
  agents: AgentConfig[];
  onConfirm: (title: string, selectedIds: string[]) => void;
  onCancel: () => void;
}

export function GroupChatCreator({ agents, onConfirm, onCancel }: Props) {
  const leader = useMemo(
    () => agents.find((agent) => agent.name === "项目Leader" || agent.primarySkill === "orchestrator_planner") ?? null,
    [agents],
  );
  const [selected, setSelected] = useState<Set<string>>(() => new Set(leader ? [leader.id] : []));
  const [title, setTitle] = useState("");

  useEffect(() => {
    if (!leader) return;
    setSelected((current) => current.has(leader.id) ? current : new Set([...current, leader.id]));
  }, [leader]);

  const toggle = (id: string) => {
    if (leader?.id === id) return;
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const selectedList = [...selected];
  const canCreate = Boolean(leader && selected.has(leader.id) && selectedList.length >= 2 && selectedList.length <= MAX_GROUP_AGENTS);

  return (
    <GlobalModal
      title="新建群聊"
      subtitle={`默认带上调度器，最多选择 ${MAX_GROUP_AGENTS} 个 Agent`}
      icon={<Users size={18} />}
      zIndexClass="z-[1200]"
      panelClassName="max-w-3xl"
      onClose={onCancel}
      footer={(
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="agenthub-icon-button inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2.5 text-sm"
          >
            <X size={15} />
            取消
          </button>
          <button
            type="button"
            onClick={() => onConfirm(title, selectedList)}
            disabled={!canCreate}
            className="agenthub-primary-button inline-flex items-center justify-center gap-1.5 rounded-full px-5 py-2.5 text-sm disabled:cursor-not-allowed disabled:opacity-50">
            <Check size={15} />
            {selected.size > MAX_GROUP_AGENTS ? `最多 ${MAX_GROUP_AGENTS} 个` : `创建 (${selected.size})`}
          </button>
        </div>
      )}
    >
      <div className="space-y-4">
        <p className="agenthub-muted text-sm leading-6">
          在群聊中 @调度器 生成计划，普通消息仍按群聊协作处理。
        </p>

        <input value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="群聊名称（可选）"
          className="agenthub-composer agenthub-textarea agenthub-focus-ring w-full rounded-2xl border px-3 py-3 text-sm"
        />

        <div className="grid max-h-[54dvh] gap-2 overflow-y-auto pr-1 md:grid-cols-2">
          {agents.map((a) => (
            <label key={a.id} className={`flex cursor-pointer items-center gap-2 rounded-2xl px-3 py-2.5 transition-colors ${selected.has(a.id) ? "agenthub-nav-active" : "agenthub-nav-idle"}`}>
              <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggle(a.id)} disabled={leader?.id === a.id}
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
      </div>
    </GlobalModal>
  );
}

