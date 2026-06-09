import { Check, Settings, Trash2 } from "lucide-react";
import { useState } from "react";
import type { AgentConfig } from "../types";
import { AgentAvatar } from "./AgentAvatar";

export function AgentCliRow({
  agent,
  onEdit,
  onDelete,
}: {
  agent: AgentConfig;
  onEdit: () => void;
  onDelete: () => Promise<void>;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      return;
    }
    setDeleting(true);
    try {
      await onDelete();
      setConfirmingDelete(false);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="agenthub-card rounded-2xl border p-3">
      <div className="flex items-start justify-between gap-3">
        <AgentAvatar agent={agent} size="sm" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${agent.status === "ready" ? "bg-[color:var(--ah-text-strong)]" : "bg-[color:var(--ah-faint)]"}`}
            />
            <p className="agenthub-strong truncate text-sm font-medium">{agent.name}</p>
          </div>
          <p className="agenthub-muted mt-1 truncate text-xs">
            Engine: {engineLabel(agent.cliTool)} · 工具集 {agent.toolset.length} 项
          </p>
          <p className="agenthub-muted mt-1 truncate text-xs">
            {agent.executable || "未配置 executable"} {agent.initArgs.join(" ")}
          </p>
          {agent.description && (
            <p className="agenthub-faint mt-1 truncate text-xs">{agent.description}</p>
          )}
          <p className="agenthub-faint mt-1 truncate text-xs">
            {agent.systemPrompt ? "已配置 System Prompt" : "未配置 System Prompt"}
            {" · "}
            {agent.rules ? "已配置 Rules" : "未配置 Rules"}
          </p>
          <p className="agenthub-faint mt-1 text-xs">
            {agent.status === "ready" ? agent.version || "就绪" : "未找到 executable"}
          </p>
        </div>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => {
              setConfirmingDelete(false);
              onEdit();
            }}
            className="agenthub-icon-button inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs"
          >
            <Settings size={13} />
            设置
          </button>
          <button
            type="button"
            onClick={() => void handleDelete()}
            disabled={deleting}
            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50 ${
              confirmingDelete
                ? "agenthub-confirm-danger hover:bg-[color:var(--ah-danger-soft)]"
                : "agenthub-icon-button"
            }`}
          >
            {confirmingDelete && !deleting ? <Check size={13} /> : <Trash2 size={13} />}
            {deleting ? "删除中" : confirmingDelete ? "确认" : "删除"}
          </button>
        </div>
      </div>
    </div>
  );
}

function engineLabel(value: string) {
  if (value === "claude_code") return "Claude Code";
  if (value === "codex") return "Codex";
  if (value === "opencode") return "OpenCode";
  return "Custom";
}
