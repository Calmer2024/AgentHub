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
  const pushToast = useToastStore((state) => state.pushToast);

  const load = useCallback(async () => {
    try { setAgents(await fetchAgents()); } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (mode === "hidden") return null;

  const editingAgent = mode === "edit" ? agents.find((agent) => agent.id === agentId) : undefined;
  if (mode === "edit" && !editingAgent) return null;

  return (
    <AgentCliForm
      initial={editingAgent}
      runtimeScope={runtimeScope}
      onSave={async (data) => {
        try {
          if (editingAgent) {
            await updateAgent(editingAgent.id, data as AgentConfigUpdate);
            pushToast({ kind: "success", title: "Agent 已更新" });
          } else {
            await createAgent(data);
            pushToast({ kind: "success", title: "Agent 已创建" });
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
        onClose();
      }}
      onCancel={onClose}
    />
  );
}
