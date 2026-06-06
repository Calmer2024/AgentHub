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
  loading?: boolean;
  agents: AgentConfig[];
  onSelectSession: (id: string) => void;
  onNewSession: (agentId?: string) => void;
  onNewGroupSession: () => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, title: string) => void;
}

export function SessionList({ project, sessions, currentSessionId, loading = false, agents, onSelectSession, onNewSession, onNewGroupSession, onDeleteSession, onRenameSession }: Props) {
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
    <div className="agenthub-sidebar w-full h-full flex flex-col transition-colors duration-300">
      <div className="p-4">
        {project ? (
          <div className="flex items-start gap-3">
            <span className="agenthub-soft agenthub-muted mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border">
              <FolderOpen size={18} strokeWidth={1.8} />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="agenthub-strong truncate text-sm font-semibold">{project.name}</h2>
              <p className="agenthub-muted mt-0.5 truncate text-xs">{project.workspacePath}</p>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-3">
            <span className="agenthub-soft agenthub-muted mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border">
              <FolderOpen size={18} strokeWidth={1.8} />
            </span>
            <div>
              <h2 className="agenthub-strong text-sm font-semibold">选择项目开始</h2>
              <p className="agenthub-muted mt-0.5 text-xs">所有聊天都会绑定到项目 workspace。</p>
            </div>
          </div>
        )}

        {project && (
          <div className="mt-4 grid grid-cols-2 gap-2">
            <div className="relative">
              <button
                onClick={() => setAgentPickerOpen((open) => !open)}
                disabled={creating || agents.length === 0}
                className="flex h-10 w-full items-center justify-center gap-2 rounded-full text-sm font-medium text-white shadow-[0_10px_26px_rgba(91,121,111,0.22)] transition hover:brightness-105 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
                style={{ background: "var(--ah-accent-strong)" }}
              >
                {creating ? (
                  <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                ) : (
                  <MessageCircle size={15} />
                )}
                私聊
              </button>
              {agentPickerOpen && (
                <div className="agenthub-menu absolute left-0 top-12 z-20 w-72 rounded-2xl border p-1.5">
                  {agents.map((agent) => (
                    <button
                      key={agent.id}
                      type="button"
                      onClick={() => handleCreate(agent.id)}
                      className="agenthub-nav-idle flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition"
                    >
                      <AgentAvatar agent={agent} size="sm" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{agent.name}</span>
                        <span className="agenthub-muted mt-0.5 block truncate text-xs">{agent.executable || agent.cliTool}</span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={onNewGroupSession}
              className="agenthub-icon-button flex h-10 items-center justify-center gap-2 rounded-full text-sm font-medium"
            >
              <Users size={15} />
              群聊
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {!project ? (
          <div className="agenthub-faint flex flex-col items-center justify-center py-12">
            <FolderOpen size={44} strokeWidth={1.5} className="mb-3" />
            <p className="text-sm">选择或创建项目</p>
          </div>
        ) : loading && sessions.length === 0 ? (
          <SessionListSkeleton />
        ) : sessions.length === 0 ? (
          <div className="agenthub-faint flex flex-col items-center justify-center py-12">
            <MessageCircle size={48} strokeWidth={1.5} className="mb-3" />
            <p className="text-sm">还没有对话</p>
            <p className="text-xs mt-1">点击上方按钮开始</p>
          </div>
        ) : (
          sessions.map((session) => {
            const info = getSessionInfo(session);
            const running = isSessionRunning(session.id, runtimeBySession, runsBySession);
            return (
            <div key={session.id} className="relative group mb-1 animate-[agenthub-slide-in_180ms_ease-out_both]">
              <button
                onClick={() => onSelectSession(session.id)}
                className={`w-full text-left px-3 py-2.5 rounded-2xl transition-all duration-200 ${
                  currentSessionId === session.id
                    ? "agenthub-nav-active"
                    : "agenthub-nav-idle"
                }`}
              >
                {renaming === session.id ? (
                  <input
                    value={renameTitle} onChange={(e) => setRenameTitle(e.target.value)}
                    onBlur={() => { if (renameTitle.trim()) onRenameSession(session.id, renameTitle.trim()); setRenaming(null); }}
                    onKeyDown={(e) => { if (e.key === "Enter") { if (renameTitle.trim()) onRenameSession(session.id, renameTitle.trim()); setRenaming(null); } }}
                    onClick={(e) => e.stopPropagation()}
                    className="agenthub-composer agenthub-textarea w-full rounded-xl border px-2 py-1 text-sm outline-none"
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
                        <p className="agenthub-muted truncate text-xs">
                          {running ? "对方正在输入" : info.label}
                        </p>
                        <p className="agenthub-faint shrink-0 text-[11px]">
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
                className="agenthub-icon-button absolute right-1 top-2 inline-flex h-7 w-7 items-center justify-center rounded-lg opacity-0 transition-opacity group-hover:opacity-100"
                aria-label="会话操作"
                title="会话操作"
              >
                <MoreHorizontal size={16} />
              </button>
              {menuOpen === session.id && (
                <div className="agenthub-menu absolute right-0 top-8 z-10 w-40 rounded-2xl border p-1">
                  <button onClick={() => { setRenaming(session.id); setRenameTitle(session.title); setMenuOpen(null); }}
                    className="agenthub-nav-idle flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm">
                    <Pencil size={14} />
                    重命名
                  </button>
                  <button onClick={() => { onDeleteSession(session.id); setMenuOpen(null); }}
                    className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-[color:var(--ah-danger)] hover:bg-red-500/15">
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

function SessionListSkeleton() {
  return (
    <div className="space-y-2 px-1 py-2" aria-label="正在加载对话">
      {Array.from({ length: 6 }).map((_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 rounded-2xl border border-white/[0.04] bg-white/[0.035] px-3 py-2.5"
        >
          <div className="h-10 w-10 shrink-0 animate-pulse rounded-full bg-white/[0.08]" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-3 w-2/3 animate-pulse rounded-full bg-white/[0.10]" />
            <div className="h-2.5 w-5/6 animate-pulse rounded-full bg-white/[0.06]" />
          </div>
        </div>
      ))}
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
