import { useCallback, useEffect, useState } from "react";
import type { AgentConfig, AgentConfigUpdate } from "../types";
import { createAgent, fetchAgents, updateAgent } from "../api/client";
import { AgentCliForm } from "./AgentCliForm";
import { useToastStore } from "../stores/toastStore";

interface Props {
  mode: "hidden" | "create" | "edit";
  agentId?: string | null;
  runtimeScope?: "local" | "cloud";
  onChanged: () => void;
  onClose: () => void;
}

export function AgentPanel({ mode, agentId, runtimeScope = "local", onChanged, onClose }: Props) {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const pushToast = useToastStore((state) => state.pushToast);

  const load = useCallback(async () => {
    try { setAgents(await fetchAgents()); } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (mode === "hidden") return null;

  const editingAgent = mode === "edit" && agentId
    ? agents.find((agent) => agent.id === agentId)
    : undefined;
  if (mode === "edit" && !editingAgent) {
    return loading ? (
      <div className="agenthub-agent-settings agenthub-agent-settings-page flex h-full items-center justify-center">
        <span className="agenthub-muted text-sm">正在加载 Agent 配置</span>
      </div>
    ) : null;
  }

  const form = (
    <AgentCliForm
      initial={editingAgent}
      runtimeScope={runtimeScope}
      presentation={mode === "create" ? "dialog" : "page"}
      onSave={async (data) => {
        try {
          if (editingAgent) {
            await updateAgent(editingAgent.id, data as AgentConfigUpdate);
          } else {
            await createAgent(data);
            pushToast({ kind: "success", title: "智能体已创建" });
          }
        } catch (error) {
          pushToast({
            kind: "error",
            title: editingAgent ? "更新 Agent 失败" : "创建 Agent 失败",
            description: error instanceof Error ? error.message : "请稍后重试",
          });
          throw error;
        }
        await load();
        onChanged();
        if (!editingAgent) onClose();
      }}
      onCancel={onClose}
    />
  );

  if (mode === "create") {
    return (
      <div className="agenthub-backdrop fixed inset-0 z-[1450] flex items-center justify-center p-5" role="presentation">
        <div
          className="agenthub-agent-create-dialog h-[min(860px,calc(100dvh-40px))] w-[min(1120px,calc(100vw-40px))] overflow-hidden rounded-[18px]"
          role="dialog"
          aria-modal="true"
          aria-label="添加 Agent"
        >
          {form}
        </div>
      </div>
    );
  }

  return form;
}
