import { useState } from "react";
import type { Session, AgentConfig, Project } from "../types";

interface Props {
  project: Project | null;
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

export function SessionList({ project, sessions, currentSessionId, agents, onSelectSession, onNewSession, onNewGroupSession, onDeleteSession, onRenameSession, onSummarizeSession }: Props) {
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
    <div className="w-full h-full bg-[#171717] text-[#ececf1] flex flex-col">
      <div className="p-4 border-b border-white/[0.08]">
        {project ? (
          <>
            <h2 className="text-sm font-semibold text-white truncate">{project.name}</h2>
            <p className="text-xs text-[#8f8f98] truncate mt-0.5">{project.workspacePath}</p>
          </>
        ) : (
          <>
            <h2 className="text-sm font-semibold text-white">选择项目开始</h2>
            <p className="text-xs text-[#8f8f98] mt-0.5">所有聊天都会绑定到项目 workspace。</p>
          </>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {!project ? (
          <div className="flex flex-col items-center justify-center py-12 text-[#74747d]">
            <svg className="w-11 h-11 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3 7h18M6 7v10a2 2 0 002 2h8a2 2 0 002-2V7M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2" />
            </svg>
            <p className="text-sm">选择或创建 Project</p>
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-[#74747d]">
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
                  currentSessionId === session.id ? "bg-white/10 text-white" : "hover:bg-white/[0.07] text-[#d8d8df]"
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
                      <p className="text-xs text-[#8f8f98]">
                        {new Date(session.updatedAt).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                      </p>
                      <p className="text-xs text-[#74747d]">{getSessionInfo(session).label}</p>
                    </div>
                  </>
                )}
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); setMenuOpen(menuOpen === session.id ? null : session.id); }}
                className="absolute right-1 top-2 p-1 text-[#8f8f98] hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
              >
                ···
              </button>
              {menuOpen === session.id && (
                <div className="absolute right-0 top-8 z-10 bg-[#2b2b2f] border border-white/10 rounded-xl shadow-lg py-1 w-36">
                  <button onClick={() => { setRenaming(session.id); setRenameTitle(session.title); setMenuOpen(null); }}
                    className="w-full text-left px-3 py-1.5 text-sm text-[#ececf1] hover:bg-white/[0.08]">重命名</button>
                  <button onClick={() => { onSummarizeSession(session.id); setMenuOpen(null); }}
                    className="w-full text-left px-3 py-1.5 text-sm text-[#ececf1] hover:bg-white/[0.08]">AI 总结标题</button>
                  <button onClick={() => { onDeleteSession(session.id); setMenuOpen(null); }}
                    className="w-full text-left px-3 py-1.5 text-sm text-red-300 hover:bg-red-500/15">删除</button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {project && (
        <div className="p-3 border-t border-white/[0.08] grid grid-cols-2 gap-2">
          <button
            onClick={handleCreate} disabled={creating}
            className="py-2 bg-[#ececf1] text-[#171717] rounded-lg hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center justify-center gap-2"
          >
            {creating && <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
            私聊
          </button>
          <button
            onClick={onNewGroupSession}
            className="py-2 bg-white/[0.06] text-[#ececf1] border border-white/10 rounded-lg hover:bg-white/10 text-sm"
          >
            群聊
          </button>
        </div>
      )}
    </div>
  );
}
