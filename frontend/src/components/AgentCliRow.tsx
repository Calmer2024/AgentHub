import { Settings, Trash2 } from "lucide-react";
import type { AgentConfig } from "../types";

export function AgentCliRow({
  agent,
  onEdit,
  onDelete,
}: {
  agent: AgentConfig;
  onEdit: () => void;
  onDelete: () => Promise<void>;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#202123] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${agent.status === "ready" ? "bg-emerald-300" : "bg-[#74747d]"}`}
            />
            <p className="truncate text-sm font-medium text-white">{agent.name}</p>
          </div>
          <p className="mt-1 truncate text-xs text-[#8f8f98]">
            {agent.executable || "未配置 executable"} {agent.initArgs.join(" ")}
          </p>
          {agent.description && (
            <p className="mt-1 truncate text-xs text-[#74747d]">{agent.description}</p>
          )}
          <p className="mt-1 text-xs text-[#74747d]">
            {agent.status === "ready" ? agent.version || "就绪" : "未找到 executable"}
          </p>
        </div>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={onEdit}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-[#cfd1d6] hover:bg-white/[0.08]"
          >
            <Settings size={13} />
            设置
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-red-300 hover:bg-red-500/15"
          >
            <Trash2 size={13} />
            删除
          </button>
        </div>
      </div>
    </div>
  );
}
