import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Archive,
  Bell,
  BellOff,
  Check,
  FolderOpen,
  Inbox,
  MessageCircle,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Search,
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
  onDeleteSession: (id: string) => Promise<void> | void;
  onRenameSession: (id: string, title: string) => void;
  onPinSession: (id: string, isPinned: boolean) => void;
  onArchiveSession: (id: string, archived?: boolean) => void;
  onMuteSession: (id: string, isMuted: boolean) => void;
}

export function SessionList({
  project,
  sessions,
  currentSessionId,
  loading = false,
  agents,
  onSelectSession,
  onNewSession,
  onNewGroupSession,
  onDeleteSession,
  onRenameSession,
  onPinSession,
  onArchiveSession,
  onMuteSession,
}: Props) {
  const [creating, setCreating] = useState(false);
  const [agentPickerOpen, setAgentPickerOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"active" | "archive">("active");
  const [deleteConfirmSessionId, setDeleteConfirmSessionId] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const previousProjectIdRef = useRef(project?.id);
  const menuRef = useRef<HTMLDivElement>(null);
  const runtimeBySession = useChatStore((state) => state.runtimeBySession);
  const runsBySession = useChatStore((state) => state.runsBySession);
  const agentById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents]);

  useEffect(() => {
    if (previousProjectIdRef.current === project?.id) return;
    previousProjectIdRef.current = project?.id;
    setView("active");
    setMenuOpen(null);
    setDeleteConfirmSessionId(null);
    setQuery("");
  }, [project?.id]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (menuRef.current?.contains(target)) return;
      setMenuOpen(null);
      setDeleteConfirmSessionId(null);
    };
    window.addEventListener("pointerdown", close, true);
    return () => window.removeEventListener("pointerdown", close, true);
  }, [menuOpen]);

  const getSessionInfo = (session: Session) => {
    if (session.mode === "group") {
      return { label: "群聊", agent: null };
    }
    const agent = session.agentConfigId ? agentById.get(session.agentConfigId) ?? null : null;
    return { label: agent?.name ?? "私聊", agent };
  };

  const sessionGroups = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const matchesQuery = (session: Session) => {
      if (!normalized) return true;
      const info = session.mode === "group"
        ? "群聊"
        : agentById.get(session.agentConfigId ?? "")?.name ?? "私聊";
      return `${session.title} ${info}`.toLowerCase().includes(normalized);
    };
    const sortActive = (a: Session, b: Session) => {
      const pinnedDelta = Number(Boolean(b.isPinned)) - Number(Boolean(a.isPinned));
      if (pinnedDelta !== 0) return pinnedDelta;
      return Date.parse(b.updatedAt || "") - Date.parse(a.updatedAt || "");
    };
    const sortRecent = (a: Session, b: Session) => (
      Date.parse(b.updatedAt || "") - Date.parse(a.updatedAt || "")
    );
    const active = sessions
      .filter((session) => !session.archivedAt && matchesQuery(session))
      .sort(sortActive);
    const archived = sessions
      .filter((session) => Boolean(session.archivedAt) && matchesQuery(session))
      .sort(sortRecent);
    return {
      active,
      archived,
      pinned: active.filter((session) => Boolean(session.isPinned)),
      regular: active.filter((session) => !session.isPinned),
      activeTotal: sessions.filter((session) => !session.archivedAt).length,
      archivedTotal: sessions.filter((session) => Boolean(session.archivedAt)).length,
    };
  }, [agentById, query, sessions]);

  const handleCreate = async (agentId?: string) => {
    setCreating(true);
    try {
      await onNewSession(agentId);
      setAgentPickerOpen(false);
    }
    finally { setCreating(false); }
  };

  const archivedView = view === "archive";
  const visibleSessions = archivedView ? sessionGroups.archived : sessionGroups.active;

  const requestDeleteSession = async (session: Session) => {
    if (deleteConfirmSessionId !== session.id) {
      setDeleteConfirmSessionId(session.id);
      return;
    }
    setDeleteBusy(true);
    try {
      await onDeleteSession(session.id);
      setDeleteConfirmSessionId(null);
      setMenuOpen(null);
    } finally {
      setDeleteBusy(false);
    }
  };

  const renderArchiveFolderButton = () => (
    <button
      type="button"
      onClick={() => { setView("archive"); setMenuOpen(null); }}
      className="agenthub-archive-folder mb-2 flex w-full items-center gap-3 rounded-2xl border px-3 py-2.5 text-left transition"
    >
      <span className="agenthub-archive-icon inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full">
        <Archive size={17} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="agenthub-strong block truncate text-sm font-semibold">归档对话</span>
        <span className="agenthub-muted block truncate text-xs">{sessionGroups.archivedTotal} 个对话已收起</span>
      </span>
    </button>
  );

  const renderSessionRow = (session: Session, variant: "pinned" | "regular" | "archived") => {
    const info = getSessionInfo(session);
    const running = isSessionRunning(session.id, runtimeBySession, runsBySession);
    const menuIsOpen = menuOpen === session.id;
    const unreadCount = Math.max(0, Number(session.unreadCount ?? 0));
    const hasUnread = unreadCount > 0;
    const muted = Boolean(session.isMuted);
    const rowTone = variant === "pinned"
      ? "agenthub-session-pinned"
      : variant === "archived"
        ? "agenthub-session-archived"
        : "";

    return (
      <div
        key={session.id}
        onContextMenu={(event) => {
          event.preventDefault();
          setMenuOpen(session.id);
          setDeleteConfirmSessionId(null);
        }}
        className={`group relative mb-1 animate-[agenthub-slide-in_180ms_ease-out_both] ${
          menuIsOpen ? "z-40" : "z-0"
        }`}
        ref={menuIsOpen ? menuRef : undefined}
      >
        <button
          onClick={() => onSelectSession(session.id)}
          className={`w-full text-left px-3 py-2.5 rounded-2xl transition-all duration-200 ${rowTone} ${
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
                  {variant === "pinned" && (
                    <span className="agenthub-pin-badge inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold">
                      <Pin size={10} aria-label="已置顶" />
                      置顶
                    </span>
                  )}
                  {muted && <BellOff size={13} className="agenthub-faint shrink-0" aria-label="免打扰" />}
                  {session.mode === "group" && <Users size={13} className="agenthub-muted shrink-0" />}
                </div>
                <div className="mt-0.5 flex items-center justify-between gap-2">
                  {running && variant !== "archived" ? (
                    <span className="agenthub-runtime-chip agenthub-runtime-chip-active max-w-full px-2 py-0.5 text-[11px]">
                      <span className="truncate">对方正在输入</span>
                    </span>
                  ) : (
                    <p className="agenthub-muted truncate text-xs">
                      {variant === "archived" ? "已归档" : info.label}
                    </p>
                  )}
                  <div className="flex shrink-0 items-center gap-1.5">
                    {hasUnread && (
                      <span className={`agenthub-unread-badge inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px] font-semibold ${
                        muted ? "agenthub-unread-muted" : ""
                      }`}>
                        {unreadCount > 99 ? "99+" : unreadCount}
                      </span>
                    )}
                    <p className="agenthub-faint text-[11px]">
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
            </div>
          )}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setDeleteConfirmSessionId(null);
            setMenuOpen(menuIsOpen ? null : session.id);
          }}
          className="agenthub-icon-button absolute right-1 top-2 inline-flex h-7 w-7 items-center justify-center rounded-lg opacity-0 transition-opacity group-hover:opacity-100"
          aria-label="会话操作"
          title="会话操作"
        >
          <MoreHorizontal size={16} />
        </button>
        {menuIsOpen && (
          <div className="agenthub-menu agenthub-popover absolute right-0 top-8 z-50 w-44 rounded-2xl border p-1">
            {variant === "archived" ? (
              <button
                onClick={() => { onArchiveSession(session.id, false); setMenuOpen(null); setDeleteConfirmSessionId(null); }}
                className="agenthub-nav-idle flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm"
              >
                <Inbox size={14} />
                取消归档
              </button>
            ) : (
              <button
                onClick={() => { onPinSession(session.id, !session.isPinned); setMenuOpen(null); setDeleteConfirmSessionId(null); }}
                className="agenthub-nav-idle flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm"
              >
                {session.isPinned ? <PinOff size={14} /> : <Pin size={14} />}
                {session.isPinned ? "取消置顶" : "置顶"}
              </button>
            )}
            {variant !== "archived" && (
              <button
                onClick={() => { onMuteSession(session.id, !session.isMuted); setMenuOpen(null); setDeleteConfirmSessionId(null); }}
                className="agenthub-nav-idle flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm"
              >
                {session.isMuted ? <Bell size={14} /> : <BellOff size={14} />}
                {session.isMuted ? "关闭免打扰" : "免打扰"}
              </button>
            )}
            <button onClick={() => { setRenaming(session.id); setRenameTitle(session.title); setMenuOpen(null); setDeleteConfirmSessionId(null); }}
              className="agenthub-nav-idle flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm">
              <Pencil size={14} />
              重命名
            </button>
            {variant !== "archived" && (
              <button onClick={() => { onArchiveSession(session.id, true); setMenuOpen(null); setDeleteConfirmSessionId(null); }}
                className="agenthub-nav-idle flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm">
                <Archive size={14} />
                归档
              </button>
            )}
            <button
              onClick={() => void requestDeleteSession(session)}
              disabled={deleteBusy}
              className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm disabled:cursor-not-allowed disabled:opacity-50 ${
                deleteConfirmSessionId === session.id
                  ? "agenthub-confirm-danger hover:bg-[color:var(--ah-danger-soft)]"
                  : "agenthub-nav-idle"
              }`}
            >
              {deleteConfirmSessionId === session.id && !deleteBusy ? <Check size={14} /> : <Trash2 size={14} />}
              {deleteBusy && deleteConfirmSessionId === session.id
                ? "删除中"
                : deleteConfirmSessionId === session.id ? "确认" : "删除"}
            </button>
          </div>
        )}
      </div>
    );
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
              <p className="agenthub-muted mt-0.5 truncate text-xs">
                {project.workspaceMode === "cloud"
                  ? `云端工作区 · ${projectStatusLabel(project.status)}`
                  : `本机 · ${project.workspacePath ?? "未绑定"}`}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-3">
            <span className="agenthub-soft agenthub-muted mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border">
              <FolderOpen size={18} strokeWidth={1.8} />
            </span>
            <div>
              <h2 className="agenthub-strong text-sm font-semibold">选择项目开始</h2>
              <p className="agenthub-muted mt-0.5 text-xs">所有对话都会绑定到项目工作区。</p>
            </div>
          </div>
        )}

        {project && (
          <>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <div className="relative">
                <button
                  onClick={() => setAgentPickerOpen((open) => !open)}
                  disabled={creating || agents.length === 0}
                  className="agenthub-primary-button flex h-10 w-full items-center justify-center gap-2 rounded-full text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {creating ? (
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-current/30 border-t-current" />
                  ) : (
                    <MessageCircle size={15} />
                  )}
                  私聊
                </button>
                {agentPickerOpen && (
                  <div className="agenthub-menu agenthub-popover absolute left-0 top-12 z-20 w-72 rounded-2xl border p-1.5">
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
            <label className="agenthub-composer mt-3 flex h-10 items-center gap-2 rounded-full border px-3">
              <Search size={14} className="agenthub-faint shrink-0" aria-hidden="true" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索对话"
                className="agenthub-textarea min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[color:var(--ah-faint)]"
              />
            </label>
          </>
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
        ) : archivedView ? (
          <>
            <div className="sticky top-0 z-10 mb-2 bg-[color:var(--ah-sidebar-bg)]/95 py-2 backdrop-blur">
              <button
                type="button"
                onClick={() => { setView("active"); setMenuOpen(null); }}
                className="agenthub-nav-idle flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left transition"
              >
                <span className="agenthub-soft agenthub-muted inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border">
                  <ArrowLeft size={16} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="agenthub-strong block text-sm font-semibold">归档对话</span>
                  <span className="agenthub-muted block text-xs">{sessionGroups.archivedTotal} 个已归档对话</span>
                </span>
              </button>
            </div>
            {visibleSessions.length === 0 ? (
              <div className="agenthub-faint flex flex-col items-center justify-center py-12 text-center">
                <Archive size={42} strokeWidth={1.5} className="mb-3" />
                <p className="text-sm">{query.trim() ? "没有匹配的归档对话" : "归档箱为空"}</p>
                <p className="mt-1 text-xs">右键归档对话可取消归档</p>
              </div>
            ) : (
              visibleSessions.map((session) => renderSessionRow(session, "archived"))
            )}
          </>
        ) : sessionGroups.activeTotal === 0 ? (
          <>
            {sessionGroups.archivedTotal > 0 && renderArchiveFolderButton()}
            <div className="agenthub-faint flex flex-col items-center justify-center py-12">
              <MessageCircle size={48} strokeWidth={1.5} className="mb-3" />
              <p className="text-sm">{sessionGroups.archivedTotal > 0 ? "没有未归档对话" : "还没有对话"}</p>
              <p className="text-xs mt-1">{sessionGroups.archivedTotal > 0 ? "打开归档对话查看历史" : "点击上方按钮开始"}</p>
            </div>
          </>
        ) : visibleSessions.length === 0 ? (
          <div className="agenthub-faint flex flex-col items-center justify-center py-12 text-center">
            <Search size={42} strokeWidth={1.5} className="mb-3" />
            <p className="text-sm">没有匹配的对话</p>
            <p className="mt-1 text-xs">换个关键词试试</p>
          </div>
        ) : (
          <>
            {sessionGroups.archivedTotal > 0 && renderArchiveFolderButton()}
            {sessionGroups.pinned.length > 0 && (
              <div className="agenthub-session-section-label px-2 pb-1 pt-1 text-[11px] font-normal">
                置顶
              </div>
            )}
            {sessionGroups.pinned.map((session) => renderSessionRow(session, "pinned"))}
            {sessionGroups.pinned.length > 0 && sessionGroups.regular.length > 0 && (
              <div className="agenthub-session-section-label px-2 pb-1 pt-2 text-[11px] font-normal">
                最近对话
              </div>
            )}
            {sessionGroups.regular.map((session) => renderSessionRow(session, "regular"))}
          </>
        )}
      </div>
    </div>
  );
}

function projectStatusLabel(status: Project["status"]) {
  return {
    creating: "创建中",
    ready: "就绪",
    building: "构建中",
    error: "异常",
    archived: "已归档",
  }[status];
}

function SessionListSkeleton() {
  return (
    <div className="space-y-2 px-1 py-2" aria-label="正在加载对话">
      {Array.from({ length: 6 }).map((_, index) => (
        <div
          key={index}
          className="agenthub-skeleton flex items-center gap-3 rounded-2xl border px-3 py-2.5"
        >
          <div className="h-10 w-10 shrink-0 animate-pulse rounded-full bg-[color:var(--ah-panel-muted)]" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-3 w-2/3 animate-pulse rounded-full bg-[color:var(--ah-panel-muted)]" />
            <div className="h-2.5 w-5/6 animate-pulse rounded-full bg-[color:var(--ah-card-soft)]" />
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
