import { useState } from "react";
import type { Session, Agent } from "../types";

interface Props {
  sessions: Session[];
  currentSessionId: string | null;
  agents: Agent[];
  agentsLoading: boolean;
  agentsError: string | null;
  onRetryAgents: () => void;
  onSelectSession: (id: string) => void;
  onNewSession: (title: string, agentName: string) => void;
  onOpenSettings: () => void;
}

export function SessionList({
  sessions,
  currentSessionId,
  agents,
  agentsLoading,
  agentsError,
  onRetryAgents,
  onSelectSession,
  onNewSession,
  onOpenSettings,
}: Props) {
  const [title, setTitle] = useState("");
  const [selectedAgent, setSelectedAgent] = useState("");
  const [creating, setCreating] = useState(false);

  const availableAgents = agents.filter((a) => a.isAvailable);

  const effectiveAgent = selectedAgent || (availableAgents[0]?.name ?? "");

  const handleCreate = async () => {
    if (!effectiveAgent) return;
    setCreating(true);
    try {
      await onNewSession(title || "新对话", effectiveAgent);
      setTitle("");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="w-72 h-full bg-gray-50 border-r border-gray-200 flex flex-col">
      <div className="p-4 space-y-3">
        {agentsError ? (
          <div className="px-3 py-2 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600 flex items-center justify-between">
            <span>{agentsError}</span>
            <button onClick={onRetryAgents} className="text-red-600 hover:text-red-800 underline text-xs">
              重试
            </button>
          </div>
        ) : agentsLoading ? (
          <div className="flex items-center gap-2 px-1">
            <div className="w-4 h-4 border-2 border-blue-300 border-t-blue-600 rounded-full animate-spin" />
            <span className="text-xs text-gray-400">加载 Agent...</span>
          </div>
        ) : availableAgents.length === 0 ? (
          <div className="px-3 py-2 bg-amber-50 border border-amber-200 rounded-xl text-sm">
            <p className="text-amber-700 mb-1">未配置 API Key</p>
            <button onClick={onOpenSettings} className="text-blue-600 hover:text-blue-800 underline text-xs">
              打开设置
            </button>
          </div>
        ) : (
          <select
            value={effectiveAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            className="w-full px-2 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {agents.map((agent) => (
              <option key={agent.name} value={agent.name} disabled={!agent.isAvailable}>
                {agent.displayName}{agent.isAvailable ? "" : " (不可用)"}
              </option>
            ))}
          </select>
        )}

        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={creating}
          placeholder="会话标题（可选）"
          className="w-full px-2 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <button
          onClick={handleCreate}
          disabled={creating || !effectiveAgent}
          className="w-full py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm flex items-center justify-center gap-2"
        >
          {creating && (
            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          )}
          {creating ? "创建中..." : "+ 新建对话"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <svg className="w-12 h-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p className="text-sm">还没有对话</p>
            <p className="text-xs mt-1">选择 Agent 后点击上方按钮开始</p>
          </div>
        ) : (
          sessions.map((session) => (
            <button
              key={session.id}
              onClick={() => onSelectSession(session.id)}
              className={`w-full text-left px-3 py-3 mb-1 rounded-xl transition-colors ${
                currentSessionId === session.id
                  ? "bg-blue-100 text-blue-900"
                  : "hover:bg-gray-200 text-gray-700"
              }`}
            >
              <p className="font-medium truncate">{session.title}</p>
              <div className="flex items-center justify-between mt-0.5">
                <p className="text-xs text-gray-500">
                  {new Date(session.updatedAt).toLocaleString("zh-CN", {
                    month: "numeric",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
                <p className="text-xs text-gray-400">{session.agentName}</p>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
