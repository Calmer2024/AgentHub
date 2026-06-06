import { useMemo, useState } from "react";
import {
  FolderOpen,
  MessageCircle,
  MoreHorizontal,
  Pencil,
  Trash2,
  Users,
} from "lucide-react";
import type { Session, AgentConfig, Project, RunStatus } from "../types";
import { AgentAvatar } from "./AgentAvatar";
import { formatChinaDateTime } from "../utils/time";
import { useChatStore } from "../stores/chatStore";

interface Props {
  project: Project | null;
  sessions: Session[];
  currentSessionId: string | null;
  agents: AgentConfig[];
  onSelectSession: (id: string) => void;
  onNewSession: (agentId?: string) => void;
  onNewGroupSession: () => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, title: string) => void;
}

export function SessionList({ project, sessions, currentSessionId, agents, onSelectSession, onNewSession, onNewGroupSession, onDeleteSession, onRenameSession }: Props) {
  const [creating, setCreating] = useState(false);
  const [agentPickerOpen, setAgentPickerOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const runtimeBySession = useChatStore((state) => state.runtimeBySession);
  const runsBySession = useChatStore((state) => state.runsBySession);
  const agentById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents]);

  const handleCreate = async (agentId?: string) => {
    setCreating(true);
    try {
      await onNewSession(agentId);
      setAgentPickerOpen(false);
    }
    finally { setCreating(false); }
  };

  const getSessionInfo = (session: Session) => {
    if (session.mode === "group") {
      return { label: "群聊", agent: null };
    }
    const agent = session.agentConfigId ? agentById.get(session.agentConfigId) ?? null : null;
    return { label: agent?.name ?? "私聊", agent };
  };

  return (
    <div className="w-full h-full bg-[#171717] text-[#ececf1] flex flex-col">
      <div className="p-4">
        {project ? (
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.06] text-[#d8d8df]">
              <FolderOpen size={18} strokeWidth={1.8} />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-sm font-semibold text-white">{project.name}</h2>
              <p className="mt-0.5 truncate text-xs text-[#8f8f98]">{project.workspacePath}</p>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.06] text-[#8f8f98]">
              <FolderOpen size={18} strokeWidth={1.8} />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-white">选择项目开始</h2>
              <p className="mt-0.5 text-xs text-[#8f8f98]">所有聊天都会绑定到项目 workspace。</p>
            </div>
          </div>
        )}

        {project && (
          <div className="mt-4 grid grid-cols-2 gap-2">
            <div className="relative">
              <button
                onClick={() => setAgentPickerOpen((open) => !open)}
                disabled={creating || agents.length === 0}
                className="flex h-10 w-full items-center justify-center gap-2 rounded-full bg-[#2f7cf6] text-sm font-medium text-white shadow-[0_10px_26px_rgba(47,124,246,0.24)] transition hover:bg-[#3d88ff] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
              >
                {creating ? (
                  <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                ) : (
                  <MessageCircle size={15} />
                )}
                私聊
              </button>
              {agentPickerOpen && (
                <div className="absolute left-0 top-12 z-20 w-72 rounded-2xl border border-white/10 bg-[#242528]/95 p-1.5 shadow-2xl backdrop-blur">
                  {agents.map((agent) => (
                    <button
                      key={agent.id}
                      type="button"
                      onClick={() => handleCreate(agent.id)}
                      className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-[#f3f3f4] transition hover:bg-white/[0.08]"
                    >
                      <AgentAvatar agent={agent} size="sm" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{agent.name}</span>
                        <span className="mt-0.5 block truncate text-xs text-[#8f8f98]">{agent.executable || agent.cliTool}</span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={onNewGroupSession}
              className="flex h-10 items-center justify-center gap-2 rounded-full border border-white/10 bg-white/[0.06] text-sm font-medium text-[#ececf1] transition hover:bg-white/10 active:translate-y-px"
            >
              <Users size={15} />
              群聊
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {!project ? (
          <div className="flex flex-col items-center justify-center py-12 text-[#74747d]">
            <FolderOpen size={44} strokeWidth={1.5} className="mb-3" />
            <p className="text-sm">选择或创建项目</p>
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-[#74747d]">
            <MessageCircle size={48} strokeWidth={1.5} className="mb-3" />
            <p className="text-sm">还没有对话</p>
            <p className="text-xs mt-1">点击上方按钮开始</p>
          </div>
        ) : (
          sessions.map((session) => {
            const info = getSessionInfo(session);
            const running = isSessionRunning(session.id, runtimeBySession, runsBySession);
            return (
            <div key={session.id} className="relative group mb-1">
              <button
                onClick={() => onSelectSession(session.id)}
                className={`w-full text-left px-3 py-2.5 rounded-2xl transition-all duration-150 ${
                  currentSessionId === session.id
                    ? "bg-[#2b5278] text-white shadow-[inset_3px_0_0_rgba(96,165,250,0.95)]"
                    : "hover:bg-white/[0.07] text-[#d8d8df]"
                }`}
              >
                {renaming === session.id ? (
                  <input
                    value={renameTitle} onChange={(e) => setRenameTitle(e.target.value)}
                    onBlur={() => { if (renameTitle.trim()) onRenameSession(session.id, renameTitle.trim()); setRenaming(null); }}
                    onKeyDown={(e) => { if (e.key === "Enter") { if (renameTitle.trim()) onRenameSession(session.id, renameTitle.trim()); setRenaming(null); } }}
                    onClick={(e) => e.stopPropagation()}
                    className="w-full rounded-xl border border-blue-300 bg-[#111318] px-2 py-1 text-sm text-white outline-none"
                    autoFocus
                  />
                ) : (
                  <div className="flex items-center gap-3">
                    {session.mode === "group"
                      ? <AgentAvatar kind="group" name="群聊" size="md" />
                      : <AgentAvatar agent={info.agent} name={info.label} size="md" />}
                    <div className="min-w-0 flex-1">
                      <div className="flex min-w-0 items-center gap-2">
                        <p className="truncate text-sm font-semibold">{session.title}</p>
                        {session.mode === "group" && <Users size={13} className="shrink-0 text-[#b8c7d9]" />}
                      </div>
                      <div className="mt-0.5 flex items-center justify-between gap-2">
                        <p className="truncate text-xs text-[#9aa5b1]">
                          {running ? "对方正在输入" : info.label}
                        </p>
                        <p className="shrink-0 text-[11px] text-[#74747d]">
                          {formatChinaDateTime(session.updatedAt, {
                            month: "numeric",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); setMenuOpen(menuOpen === session.id ? null : session.id); }}
                className="absolute right-1 top-2 inline-flex h-7 w-7 items-center justify-center rounded-lg text-[#8f8f98] opacity-0 transition-opacity hover:bg-white/10 hover:text-white group-hover:opacity-100"
                aria-label="会话操作"
                title="会话操作"
              >
                <MoreHorizontal size={16} />
              </button>
              {menuOpen === session.id && (
                <div className="absolute right-0 top-8 z-10 w-40 rounded-2xl border border-white/10 bg-[#2b2b2f] p-1 shadow-2xl">
                  <button onClick={() => { setRenaming(session.id); setRenameTitle(session.title); setMenuOpen(null); }}
                    className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-[#ececf1] hover:bg-white/[0.08]">
                    <Pencil size={14} />
                    重命名
                  </button>
                  <button onClick={() => { onDeleteSession(session.id); setMenuOpen(null); }}
                    className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-red-300 hover:bg-red-500/15">
                    <Trash2 size={14} />
                    删除
                  </button>
                </div>
              )}
            </div>
          );})
        )}
      </div>
    </div>
  );
}

const ACTIVE_RUN_STATUSES = new Set<RunStatus>(["queued", "running", "pausing", "cancelling"]);

function isSessionRunning(
  sessionId: string,
  runtimeBySession: ReturnType<typeof useChatStore.getState>["runtimeBySession"],
  runsBySession: ReturnType<typeof useChatStore.getState>["runsBySession"],
) {
  if (runtimeBySession[sessionId]?.isStreaming) return true;
  return (runsBySession[sessionId] ?? []).some((run) => ACTIVE_RUN_STATUSES.has(run.status));
}
