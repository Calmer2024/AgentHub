import { useCallback, useEffect, useState } from "react";
import type { AgentConfig, AgentConfigUpdate } from "../types";
import { createAgent, fetchAgents, updateAgent } from "../api/client";
import { AgentCliForm } from "./AgentCliForm";

interface Props {
  mode: "hidden" | "create" | "edit";
  agentId?: string | null;
  onChanged: () => void;
  onClose: () => void;
}

export function AgentPanel({ mode, agentId, onChanged, onClose }: Props) {
  const [agents, setAgents] = useState<AgentConfig[]>([]);

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
      onSave={async (data) => {
        if (editingAgent) {
          await updateAgent(editingAgent.id, data as AgentConfigUpdate);
        } else {
          await createAgent(data);
        }
        await load();
        onChanged();
        onClose();
      }}
      onCancel={onClose}
    />
  );
}
