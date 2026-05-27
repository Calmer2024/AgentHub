import { useState } from "react";
import type { Session, AgentConfig } from "../types";

interface Props {
  sessions: Session[];
  currentSessionId: string | null;
  agents: AgentConfig[];
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onNewGroupSession: () => void;
}

export function SessionList({ sessions, currentSessionId, agents, onSelectSession, onNewSession, onNewGroupSession }: Props) {
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    setCreating(true);
    try { await onNewSession(); }
    finally { setCreating(false); }
  };

  const getAgentName = (session: Session) => {
    if (!session.agentConfigId) return "";
    return agents.find((a) => a.id === session.agentConfigId)?.name ?? "";
  };

  return (
    <div className="w-72 h-full bg-gray-50 border-r border-gray-200 flex flex-col">
      <div className="p-4 space-y-2">
        <button
          onClick={handleCreate} disabled={creating}
          className="w-full py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm flex items-center justify-center gap-2"
        >
          {creating && <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
          {creating ? "..." : "+ 新建对话"}
        </button>
        <button
          onClick={onNewGroupSession}
          className="w-full py-2 bg-blue-50 text-blue-700 border border-blue-200 rounded-xl hover:bg-blue-100 text-sm"
        >
          + 新建群聊
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
            <p className="text-xs mt-1">点击上方按钮开始</p>
          </div>
        ) : (
          sessions.map((session) => (
            <button
              key={session.id} onClick={() => onSelectSession(session.id)}
              className={`w-full text-left px-3 py-3 mb-1 rounded-xl transition-colors ${
                currentSessionId === session.id ? "bg-blue-100 text-blue-900" : "hover:bg-gray-200 text-gray-700"
              }`}
            >
              <p className="font-medium truncate">{session.title}</p>
              <div className="flex items-center justify-between mt-0.5">
                <p className="text-xs text-gray-500">
                  {new Date(session.updatedAt).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </p>
                {getAgentName(session) && <p className="text-xs text-gray-400">{getAgentName(session)}</p>}
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
