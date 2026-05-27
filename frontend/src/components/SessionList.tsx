import { useState } from "react";
import type { Session, AgentConfig } from "../types";

interface Props {
  sessions: Session[];
  currentSessionId: string | null;
  agents: AgentConfig[];
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onNewGroupSession: () => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, title: string) => void;
  onSummarizeSession: (id: string) => void;
}

export function SessionList({ sessions, currentSessionId, agents, onSelectSession, onNewSession, onNewGroupSession, onDeleteSession, onRenameSession, onSummarizeSession }: Props) {
  const [creating, setCreating] = useState(false);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState("");

  const handleCreate = async () => {
    setCreating(true);
    try { await onNewSession(); }
    finally { setCreating(false); }
  };

  const getSessionInfo = (session: Session) => {
    if (session.mode === "group") {
      return { label: "群聊", sub: "" };
    }
    const name = agents.find((a) => a.id === session.agentConfigId)?.name ?? "";
    return { label: name, sub: "" };
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
            <div key={session.id} className="relative group mb-1">
              <button
                onClick={() => onSelectSession(session.id)}
                className={`w-full text-left px-3 py-3 rounded-xl transition-colors ${
                  currentSessionId === session.id ? "bg-blue-100 text-blue-900" : "hover:bg-gray-200 text-gray-700"
                }`}
              >
                {renaming === session.id ? (
                  <input
                    value={renameTitle} onChange={(e) => setRenameTitle(e.target.value)}
                    onBlur={() => { if (renameTitle.trim()) onRenameSession(session.id, renameTitle.trim()); setRenaming(null); }}
                    onKeyDown={(e) => { if (e.key === "Enter") { if (renameTitle.trim()) onRenameSession(session.id, renameTitle.trim()); setRenaming(null); } }}
                    onClick={(e) => e.stopPropagation()}
                    className="w-full px-2 py-1 border border-blue-300 rounded text-sm"
                    autoFocus
                  />
                ) : (
                  <>
                    <div className="flex items-center gap-1.5">
                      {session.mode === "group" && <span className="text-xs">👥</span>}
                      <p className="font-medium truncate">{session.title}</p>
                    </div>
                    <div className="flex items-center justify-between mt-0.5">
                      <p className="text-xs text-gray-500">
                        {new Date(session.updatedAt).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                      </p>
                      <p className="text-xs text-gray-400">{getSessionInfo(session).label}</p>
                    </div>
                  </>
                )}
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); setMenuOpen(menuOpen === session.id ? null : session.id); }}
                className="absolute right-1 top-2 p-1 text-gray-400 hover:text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                ···
              </button>
              {menuOpen === session.id && (
                <div className="absolute right-0 top-8 z-10 bg-white border border-gray-200 rounded-xl shadow-lg py-1 w-36">
                  <button onClick={() => { setRenaming(session.id); setRenameTitle(session.title); setMenuOpen(null); }}
                    className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50">重命名</button>
                  <button onClick={() => { onSummarizeSession(session.id); setMenuOpen(null); }}
                    className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50">AI 总结标题</button>
                  <button onClick={() => { onDeleteSession(session.id); setMenuOpen(null); }}
                    className="w-full text-left px-3 py-1.5 text-sm text-red-500 hover:bg-red-50">删除</button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
