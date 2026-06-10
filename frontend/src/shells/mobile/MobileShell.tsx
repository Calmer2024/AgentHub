import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  Archive,
  ArrowLeft,
  Bell,
  BellOff,
  CheckCircle2,
  FileCode2,
  FileImage,
  FileText,
  Files,
  Globe2,
  Inbox,
  Loader2,
  MessageCircle,
  Pin,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  User,
  Users,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import {
  archiveSession,
  createChatStream,
  decideMobileApproval,
  fetchApprovals,
  fetchArtifacts,
  fetchCurrentUser,
  fetchMessages,
  fetchNotifications,
  fetchProjects,
  fetchSessionMembers,
  fetchSessions,
  markNotificationRead,
  markSessionRead,
  muteSession,
  pinSession,
  renderArtifact,
} from "../../api/client";
import type {
  ApprovalCheckpoint,
  Artifact,
  CurrentUser,
  Message,
  Notification as HubNotification,
  Project,
  RenderedArtifact,
  Session,
  SessionMember,
} from "../../types";
import { chinaNowIso } from "../../utils/time";
import { getArtifactPreviewInfo } from "../../utils/artifactPreview";

type MobilePane = "inbox" | "chat" | "artifacts" | "approvals" | "notifications";
type SessionsByProject = Record<string, Session[]>;

export function MobileShell() {
  const [pane, setPane] = useState<MobilePane>("inbox");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessionsByProject, setSessionsByProject] = useState<SessionsByProject>({});
  const [notifications, setNotifications] = useState<HubNotification[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [approvals, setApprovals] = useState<ApprovalCheckpoint[]>([]);
  const [members, setMembers] = useState<SessionMember[]>([]);
  const [renderedArtifact, setRenderedArtifact] = useState<RenderedArtifact | null>(null);
  const [search, setSearch] = useState("");
  const [composer, setComposer] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [streamingSessionId, setStreamingSessionId] = useState<string | null>(null);
  const [streamProgress, setStreamProgress] = useState<string | null>(null);
  const [busyApprovalId, setBusyApprovalId] = useState<string | null>(null);
  const [busySessionAction, setBusySessionAction] = useState<string | null>(null);
  const [busyNotificationId, setBusyNotificationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortStreamRef = useRef<(() => void) | null>(null);

  const projectsById = useMemo(() => {
    const map = new Map<string, Project>();
    projects.forEach((project) => map.set(project.id, project));
    return map;
  }, [projects]);

  const allSessions = useMemo(
    () => projects.flatMap((project) => sessionsByProject[project.id] ?? []),
    [projects, sessionsByProject],
  );

  const activeProject = useMemo(
    () => projects.find((project) => project.id === activeProjectId) ?? null,
    [activeProjectId, projects],
  );

  const activeSession = useMemo(
    () => allSessions.find((session) => session.id === activeSessionId) ?? null,
    [activeSessionId, allSessions],
  );

  const activeSessionProject = activeSession?.projectId
    ? projectsById.get(activeSession.projectId) ?? activeProject
    : activeProject;
  const unreadTotal = allSessions.reduce((total, session) => total + (session.unreadCount ?? 0), 0);
  const unreadNotifications = notifications.filter((notification) => !notification.readAt).length;
  const pendingApprovals = approvals.filter((approval) => approval.status === "pending_review");
  const isStreaming = Boolean(activeSessionId && streamingSessionId === activeSessionId);

  const patchSession = useCallback((nextSession: Session) => {
    setSessionsByProject((current) => {
      const next: SessionsByProject = {};
      let patched = false;
      for (const [projectId, sessions] of Object.entries(current)) {
        next[projectId] = sessions.map((session) => {
          if (session.id !== nextSession.id) return session;
          patched = true;
          return nextSession;
        });
      }
      if (!patched && nextSession.projectId) {
        next[nextSession.projectId] = [nextSession, ...(next[nextSession.projectId] ?? [])];
      }
      return next;
    });
  }, []);

  const loadOverview = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [user, projectItems, notificationItems] = await Promise.all([
        fetchCurrentUser().catch(() => null),
        fetchProjects(),
        fetchNotifications().catch(() => []),
      ]);
      const failedProjects: string[] = [];
      const sessionEntries = await Promise.all(projectItems.map(async (project) => {
        try {
          const projectSessions = await fetchSessions(project.id, true);
          return [project.id, projectSessions] as const;
        } catch {
          failedProjects.push(project.name);
          return [project.id, []] as const;
        }
      }));
      const nextSessionsByProject = Object.fromEntries(sessionEntries) as SessionsByProject;
      const nextAllSessions = projectItems.flatMap((project) => nextSessionsByProject[project.id] ?? []);
      const firstProjectWithSessions = projectItems.find((project) => (nextSessionsByProject[project.id] ?? []).length > 0);
      const firstProjectId = firstProjectWithSessions?.id ?? projectItems[0]?.id ?? null;
      const firstSessionId = firstProjectId
        ? sortSessions(nextSessionsByProject[firstProjectId] ?? [])[0]?.id ?? null
        : null;

      setCurrentUser(user);
      setProjects(projectItems);
      setSessionsByProject(nextSessionsByProject);
      setNotifications(notificationItems);
      setActiveProjectId((current) => (
        current && projectItems.some((project) => project.id === current) ? current : firstProjectId
      ));
      setActiveSessionId((current) => (
        current && nextAllSessions.some((session) => session.id === current) ? current : firstSessionId
      ));
      if (failedProjects.length > 0) {
        setError(`${failedProjects.length} 个项目的对话加载失败，请稍后刷新`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "移动端工作台加载失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const loadSessionDetail = useCallback(async (sessionId: string, sessionMode: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      const [messageItems, artifactItems, approvalItems, memberItems] = await Promise.all([
        fetchMessages(sessionId),
        fetchArtifacts(sessionId),
        fetchApprovals(sessionId),
        sessionMode === "group" ? fetchSessionMembers(sessionId).catch(() => []) : Promise.resolve([]),
      ]);
      setMessages(messageItems);
      setArtifacts(artifactItems);
      setApprovals(approvalItems);
      setMembers(memberItems);
      setRenderedArtifact(null);
      markSessionRead(sessionId)
        .then((updated) => patchSession(updated))
        .catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "会话详情加载失败");
    } finally {
      setDetailLoading(false);
    }
  }, [patchSession]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (activeSession) {
      void loadSessionDetail(activeSession.id, activeSession.mode);
      return;
    }
    setMessages([]);
    setArtifacts([]);
    setApprovals([]);
    setMembers([]);
    setRenderedArtifact(null);
  }, [activeSession?.id, activeSession?.mode, loadSessionDetail]);

  useEffect(() => () => {
    abortStreamRef.current?.();
  }, []);

  const selectProject = (projectId: string) => {
    const nextSessions = sortSessions(sessionsByProject[projectId] ?? []);
    const nextSession = nextSessions.find((session) => !session.archivedAt) ?? nextSessions[0] ?? null;
    setActiveProjectId(projectId);
    setActiveSessionId(nextSession?.id ?? null);
    setPane("inbox");
  };

  const selectSession = (session: Session) => {
    if (session.projectId) setActiveProjectId(session.projectId);
    setActiveSessionId(session.id);
    setPane("chat");
  };

  const openArtifact = async (artifact: Artifact) => {
    setDetailLoading(true);
    setError(null);
    try {
      setRenderedArtifact(await renderArtifact(artifact.id, "html"));
      setPane("artifacts");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Artifact 渲染失败");
    } finally {
      setDetailLoading(false);
    }
  };

  const decideApproval = async (approval: ApprovalCheckpoint, decision: "approve" | "reject") => {
    setBusyApprovalId(approval.id);
    setError(null);
    try {
      await decideMobileApproval(approval.id, {
        decision,
        comment: decision === "approve" ? "移动端同意" : "移动端驳回",
      });
      if (activeSession) await loadSessionDetail(activeSession.id, activeSession.mode);
      await loadOverview(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "审批操作失败");
    } finally {
      setBusyApprovalId(null);
    }
  };

  const runSessionAction = async (key: string, action: () => Promise<Session>) => {
    setBusySessionAction(key);
    setError(null);
    try {
      patchSession(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : "会话操作失败");
    } finally {
      setBusySessionAction(null);
    }
  };

  const readNotification = async (notification: HubNotification) => {
    if (notification.readAt) return;
    setBusyNotificationId(notification.id);
    setError(null);
    try {
      await markNotificationRead(notification.id);
      setNotifications((current) => current.map((item) => (
        item.id === notification.id ? { ...item, readAt: chinaNowIso() } : item
      )));
    } catch (err) {
      setError(err instanceof Error ? err.message : "通知状态更新失败");
    } finally {
      setBusyNotificationId(null);
    }
  };

  const appendStreamingToken = useCallback((messageId: string, token: string) => {
    setMessages((current) => current.map((message) => (
      message.id === messageId ? { ...message, content: `${message.content}${token}` } : message
    )));
  }, []);

  const upsertArtifact = useCallback((artifact: Artifact) => {
    setArtifacts((current) => {
      const exists = current.some((item) => item.id === artifact.id);
      return exists ? current.map((item) => (item.id === artifact.id ? artifact : item)) : [artifact, ...current];
    });
  }, []);

  const upsertApproval = useCallback((approval: ApprovalCheckpoint) => {
    setApprovals((current) => {
      const exists = current.some((item) => item.id === approval.id);
      return exists ? current.map((item) => (item.id === approval.id ? approval : item)) : [approval, ...current];
    });
  }, []);

  const sendMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = composer.trim();
    if (!activeSessionId || !content || isStreaming) return;
    const now = chinaNowIso();
    const localUserId = `mobile-user-${Date.now()}`;
    const localAssistantId = `mobile-assistant-${Date.now()}`;
    setMessages((current) => [
      ...current,
      {
        id: localUserId,
        sessionId: activeSessionId,
        role: "user",
        content,
        agentName: null,
        createdAt: now,
      },
      {
        id: localAssistantId,
        sessionId: activeSessionId,
        role: "assistant",
        content: "",
        agentName: activeSession?.mode === "group" ? "协作 Agent" : null,
        createdAt: now,
      },
    ]);
    setComposer("");
    setError(null);
    setStreamProgress("正在连接云端运行环境");
    setStreamingSessionId(activeSessionId);

    abortStreamRef.current = createChatStream(activeSessionId, content, [], {
      onToken: (token) => appendStreamingToken(localAssistantId, token),
      onAgentStart: (startEvent) => {
        if (!startEvent.agentName) return;
        setMessages((current) => current.map((message) => (
          message.id === localAssistantId && !message.agentName
            ? { ...message, agentName: startEvent.agentName }
            : message
        )));
      },
      onAgentToken: (_agentId, agentName, token) => {
        setMessages((current) => current.map((message) => (
          message.id === localAssistantId
            ? { ...message, agentName: message.agentName ?? agentName, content: `${message.content}${token}` }
            : message
        )));
      },
      onProgress: (progress) => setStreamProgress(progress),
      onTraceDelta: (_messageId, item) => {
        if (item.title || item.text) setStreamProgress(item.title ?? item.text);
      },
      onArtifactCreated: upsertArtifact,
      onApprovalCreated: upsertApproval,
      onApprovalStatusChanged: upsertApproval,
      onSessionTitleUpdated: patchSession,
      onDone: (_messageId, streamError) => {
        abortStreamRef.current = null;
        setStreamingSessionId(null);
        setStreamProgress(null);
        if (streamError) {
          setError(streamError === "Stream ended unexpectedly" ? "连接中断，请检查网络后重试" : `请求失败：${streamError}`);
          setMessages((current) => current.map((message) => (
            message.id === localAssistantId && !message.content
              ? { ...message, content: "请求失败，请稍后重试。" }
              : message
          )));
          return;
        }
        Promise.all([
          fetchMessages(activeSessionId).then(setMessages),
          fetchArtifacts(activeSessionId).then(setArtifacts),
          fetchApprovals(activeSessionId).then(setApprovals),
          markSessionRead(activeSessionId).then(patchSession).catch(() => undefined),
          loadOverview(true),
        ]).catch((err) => {
          setError(err instanceof Error ? err.message : "消息刷新失败");
        });
      },
    });
  };

  const stopStreaming = () => {
    abortStreamRef.current?.();
    abortStreamRef.current = null;
    setStreamingSessionId(null);
    setStreamProgress(null);
  };

  return (
    <main className="agenthub-shell flex h-[100dvh] w-screen max-w-full min-w-0 flex-col overflow-hidden p-0">
      <MobileTopBar
        user={currentUser}
        project={activeSessionProject}
        activeSession={activeSession}
        unreadTotal={unreadTotal}
        refreshing={refreshing}
        onRefresh={() => void loadOverview(true)}
        onProfile={() => setShowProfile(true)}
      />

      {error && (
        <div className="mx-3 mt-3 rounded-lg border border-[color:var(--ah-danger)] bg-[color:var(--ah-danger-soft)] px-3 py-2 text-sm text-[color:var(--ah-danger)]">
          {error}
        </div>
      )}

      <section className="min-h-0 min-w-0 flex-1 overflow-hidden">
        {loading ? (
          <MobileLoading />
        ) : pane === "inbox" ? (
          <ProjectInbox
            projects={projects}
            sessionsByProject={sessionsByProject}
            activeProjectId={activeProjectId}
            activeSessionId={activeSessionId}
            projectsById={projectsById}
            search={search}
            showArchived={showArchived}
            onSearch={setSearch}
            onToggleArchived={() => setShowArchived((current) => !current)}
            onSelectProject={selectProject}
            onSelectSession={selectSession}
          />
        ) : pane === "chat" ? (
          <ChatPane
            session={activeSession}
            project={activeSessionProject}
            messages={messages}
            artifacts={artifacts}
            approvals={pendingApprovals}
            members={members}
            composer={composer}
            loading={detailLoading}
            streaming={isStreaming}
            streamProgress={streamProgress}
            busyAction={busySessionAction}
            onBack={() => setPane("inbox")}
            onComposerChange={setComposer}
            onSend={sendMessage}
            onStopStreaming={stopStreaming}
            onOpenArtifact={(artifact) => void openArtifact(artifact)}
            onOpenApprovals={() => setPane("approvals")}
            onPin={(session) => void runSessionAction(
              "pin",
              () => pinSession(session.id, !session.isPinned),
            )}
            onMute={(session) => void runSessionAction(
              "mute",
              () => muteSession(session.id, !session.isMuted),
            )}
            onArchive={(session) => void runSessionAction(
              "archive",
              () => archiveSession(session.id, !session.archivedAt),
            )}
          />
        ) : pane === "artifacts" ? (
          <ArtifactPane
            session={activeSession}
            artifacts={artifacts}
            renderedArtifact={renderedArtifact}
            loading={detailLoading}
            onBack={() => setPane("chat")}
            onOpenArtifact={(artifact) => void openArtifact(artifact)}
          />
        ) : pane === "approvals" ? (
          <ApprovalPane
            approvals={pendingApprovals}
            session={activeSession}
            busyApprovalId={busyApprovalId}
            onBack={() => setPane("chat")}
            onApprove={(approval) => void decideApproval(approval, "approve")}
            onReject={(approval) => void decideApproval(approval, "reject")}
          />
        ) : (
          <NotificationPane
            notifications={notifications}
            busyNotificationId={busyNotificationId}
            onRead={(notification) => void readNotification(notification)}
          />
        )}
      </section>

      <nav className="grid shrink-0 grid-cols-5 border-t bg-[color:var(--ah-header-bg)] px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur" style={{ borderColor: "var(--ah-border)" }}>
        <MobileNavButton icon={Inbox} label="项目" active={pane === "inbox"} count={unreadTotal} onClick={() => setPane("inbox")} />
        <MobileNavButton icon={MessageCircle} label="对话" active={pane === "chat"} disabled={!activeSession} onClick={() => setPane("chat")} />
        <MobileNavButton icon={FileText} label="产物" active={pane === "artifacts"} count={artifacts.length} disabled={!activeSession} onClick={() => setPane("artifacts")} />
        <MobileNavButton icon={ShieldCheck} label="审批" active={pane === "approvals"} count={pendingApprovals.length} disabled={!activeSession} onClick={() => setPane("approvals")} />
        <MobileNavButton icon={Bell} label="通知" active={pane === "notifications"} count={unreadNotifications} onClick={() => setPane("notifications")} />
      </nav>

      {showProfile && (
        <ProfileSheet
          user={currentUser}
          projects={projects}
          sessionCount={allSessions.length}
          unreadTotal={unreadTotal}
          onClose={() => setShowProfile(false)}
        />
      )}
    </main>
  );
}

function MobileTopBar({
  user,
  project,
  activeSession,
  unreadTotal,
  refreshing,
  onRefresh,
  onProfile,
}: {
  user: CurrentUser | null;
  project: Project | null;
  activeSession: Session | null;
  unreadTotal: number;
  refreshing: boolean;
  onRefresh: () => void;
  onProfile: () => void;
}) {
  return (
    <header className="shrink-0 border-b bg-[color:var(--ah-header-bg)] px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] backdrop-blur" style={{ borderColor: "var(--ah-border)" }}>
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onProfile}
          aria-label="打开个人信息"
          className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border bg-[color:var(--ah-card-soft)] text-sm font-semibold text-[color:var(--ah-text-strong)]"
          style={{ borderColor: "var(--ah-border)" }}
        >
          <UserAvatar user={user} />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[11px] text-[color:var(--ah-faint)]">
            {project?.name ?? user?.defaultSpace?.name ?? "AgentHub Mobile"}
          </p>
          <h1 className="truncate text-base font-semibold text-[color:var(--ah-text-strong)]">
            {activeSession?.title ?? "移动工作台"}
          </h1>
        </div>
        {unreadTotal > 0 && (
          <span className="inline-flex min-w-7 shrink-0 items-center justify-center rounded-full bg-[color:var(--ah-unread-bg)] px-2 py-1 text-xs font-semibold text-[color:var(--ah-unread-text)]">
            {unreadTotal > 99 ? "99+" : unreadTotal}
          </span>
        )}
        <button
          type="button"
          onClick={onRefresh}
          aria-label="刷新移动端数据"
          disabled={refreshing}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border text-[color:var(--ah-text-strong)] disabled:opacity-50"
          style={{ borderColor: "var(--ah-border)" }}
        >
          <RefreshCw size={17} className={refreshing ? "animate-spin" : ""} />
        </button>
      </div>
    </header>
  );
}

function ProjectInbox({
  projects,
  sessionsByProject,
  activeProjectId,
  activeSessionId,
  projectsById,
  search,
  showArchived,
  onSearch,
  onToggleArchived,
  onSelectProject,
  onSelectSession,
}: {
  projects: Project[];
  sessionsByProject: SessionsByProject;
  activeProjectId: string | null;
  activeSessionId: string | null;
  projectsById: Map<string, Project>;
  search: string;
  showArchived: boolean;
  onSearch: (value: string) => void;
  onToggleArchived: () => void;
  onSelectProject: (projectId: string) => void;
  onSelectSession: (session: Session) => void;
}) {
  const normalizedSearch = search.trim().toLowerCase();
  const activeSessions = sortSessions(activeProjectId ? sessionsByProject[activeProjectId] ?? [] : []);
  const allSessions = sortSessions(projects.flatMap((project) => sessionsByProject[project.id] ?? []));
  const visibleSessions = normalizedSearch
    ? allSessions.filter((session) => {
      const projectName = session.projectId ? projectsById.get(session.projectId)?.name ?? "" : "";
      return `${session.title} ${projectName}`.toLowerCase().includes(normalizedSearch);
    })
    : activeSessions.filter((session) => showArchived || !session.archivedAt);

  if (projects.length === 0) {
    return <EmptyState title="暂无项目" detail="登录后的云端项目会显示在这里。" />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 space-y-3 border-b px-3 py-3" style={{ borderColor: "var(--ah-border)" }}>
        <div className="flex gap-2 overflow-x-auto pb-1">
          {projects.map((project) => {
            const projectSessions = sessionsByProject[project.id] ?? [];
            const unread = projectSessions.reduce((total, session) => total + (session.unreadCount ?? 0), 0);
            return (
              <button
                key={project.id}
                type="button"
                onClick={() => onSelectProject(project.id)}
                className={`flex min-w-[9rem] max-w-[13rem] shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-left transition ${
                  activeProjectId === project.id ? "bg-[color:var(--ah-highlight-bg)]" : "bg-[color:var(--ah-card-bg)]"
                }`}
                style={{ borderColor: activeProjectId === project.id ? "var(--ah-border-strong)" : "var(--ah-border)" }}
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[color:var(--ah-card-soft)] text-xs font-semibold text-[color:var(--ah-text-strong)]">
                  {initials(project.name)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-[color:var(--ah-text-strong)]">{project.name}</span>
                  <span className="block text-[11px] text-[color:var(--ah-faint)]">{projectSessions.length} 个对话</span>
                </span>
                {unread > 0 && <Badge>{unread}</Badge>}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2">
          <label className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-lg border bg-[color:var(--ah-composer-bg)] px-3" style={{ borderColor: "var(--ah-border)" }}>
            <Search size={16} className="shrink-0 text-[color:var(--ah-faint)]" />
            <input
              value={search}
              onChange={(event) => onSearch(event.target.value)}
              aria-label="搜索项目和对话"
              placeholder="搜索项目或对话"
              className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[color:var(--ah-faint)]"
            />
          </label>
          <button
            type="button"
            onClick={onToggleArchived}
            className={`h-10 shrink-0 rounded-lg border px-3 text-xs font-medium ${
              showArchived ? "bg-[color:var(--ah-highlight-bg)] text-[color:var(--ah-text-strong)]" : "text-[color:var(--ah-muted)]"
            }`}
            style={{ borderColor: "var(--ah-border)" }}
          >
            含归档
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {visibleSessions.length === 0 ? (
          <EmptyState title="暂无对话" detail={normalizedSearch ? "没有匹配的项目或对话。" : "当前项目还没有可见对话。"} compact />
        ) : (
          <div className="space-y-2">
            {visibleSessions.map((session) => (
              <SessionRow
                key={session.id}
                session={session}
                project={session.projectId ? projectsById.get(session.projectId) ?? null : null}
                active={session.id === activeSessionId}
                onSelect={onSelectSession}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SessionRow({
  session,
  project,
  active,
  onSelect,
}: {
  session: Session;
  project: Project | null;
  active: boolean;
  onSelect: (session: Session) => void;
}) {
  const unread = session.unreadCount ?? 0;
  return (
    <button
      type="button"
      onClick={() => onSelect(session)}
      className={`flex w-full min-w-0 items-center gap-3 rounded-lg border px-3 py-3 text-left transition active:translate-y-px ${
        active ? "bg-[color:var(--ah-highlight-bg)]" : "bg-[color:var(--ah-card-bg)]"
      }`}
      style={{ borderColor: active ? "var(--ah-border-strong)" : "var(--ah-border)" }}
    >
      <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[color:var(--ah-card-soft)] text-[color:var(--ah-text-strong)]">
        {session.mode === "group" ? <Users size={18} /> : <MessageCircle size={18} />}
        {unread > 0 && <span className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-[color:var(--ah-unread-bg)]" />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-center gap-2">
          {session.isPinned && <Pin size={13} className="shrink-0 text-[color:var(--ah-text-strong)]" />}
          <span className="truncate text-sm font-semibold text-[color:var(--ah-text-strong)]">{session.title}</span>
        </span>
        <span className="mt-1 flex min-w-0 items-center gap-2 text-xs text-[color:var(--ah-faint)]">
          <span className="truncate">{project?.name ?? "个人项目"}</span>
          <span>·</span>
          <span>{session.mode === "group" ? "群聊" : "私聊"}</span>
          {session.archivedAt && <span>· 归档</span>}
          {session.isMuted && <span>· 免打扰</span>}
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1">
        <span className="text-[11px] text-[color:var(--ah-faint)]">{formatRelativeTime(session.updatedAt)}</span>
        {unread > 0 && <Badge>{unread}</Badge>}
      </span>
    </button>
  );
}

function ChatPane({
  session,
  project,
  messages,
  artifacts,
  approvals,
  members,
  composer,
  loading,
  streaming,
  streamProgress,
  busyAction,
  onBack,
  onComposerChange,
  onSend,
  onStopStreaming,
  onOpenArtifact,
  onOpenApprovals,
  onPin,
  onMute,
  onArchive,
}: {
  session: Session | null;
  project: Project | null;
  messages: Message[];
  artifacts: Artifact[];
  approvals: ApprovalCheckpoint[];
  members: SessionMember[];
  composer: string;
  loading: boolean;
  streaming: boolean;
  streamProgress: string | null;
  busyAction: string | null;
  onBack: () => void;
  onComposerChange: (value: string) => void;
  onSend: (event: FormEvent<HTMLFormElement>) => void;
  onStopStreaming: () => void;
  onOpenArtifact: (artifact: Artifact) => void;
  onOpenApprovals: () => void;
  onPin: (session: Session) => void;
  onMute: (session: Session) => void;
  onArchive: (session: Session) => void;
}) {
  if (!session) {
    return <EmptyState title="请选择对话" detail="从项目列表进入一个对话后即可开始移动协作。" />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 border-b bg-[color:var(--ah-header-bg)] px-3 py-2 backdrop-blur" style={{ borderColor: "var(--ah-border)" }}>
        <div className="flex min-w-0 items-center gap-2">
          <IconButton icon={ArrowLeft} label="返回项目列表" onClick={onBack} />
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-sm font-semibold text-[color:var(--ah-text-strong)]">{session.title}</h2>
            <p className="truncate text-[11px] text-[color:var(--ah-faint)]">
              {project?.name ?? "个人项目"} · {session.mode === "group" ? `${members.length || 0} 人群聊` : "私聊 Agent"}
            </p>
          </div>
          <IconButton icon={Pin} label={session.isPinned ? "取消置顶" : "置顶对话"} busy={busyAction === "pin"} onClick={() => onPin(session)} />
          <IconButton icon={session.isMuted ? Bell : BellOff} label={session.isMuted ? "关闭免打扰" : "开启免打扰"} busy={busyAction === "mute"} onClick={() => onMute(session)} />
          <IconButton icon={session.archivedAt ? RotateCcw : Archive} label={session.archivedAt ? "恢复对话" : "归档对话"} busy={busyAction === "archive"} onClick={() => onArchive(session)} />
        </div>
        {(members.length > 0 || approvals.length > 0 || artifacts.length > 0) && (
          <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
            {members.slice(0, 6).map((member) => (
              <span key={member.agentConfigId} className="shrink-0 rounded-full border px-2 py-1 text-[11px] text-[color:var(--ah-muted)]" style={{ borderColor: "var(--ah-border)" }}>
                {member.agentName}
              </span>
            ))}
            {approvals.length > 0 && (
              <button
                type="button"
                onClick={onOpenApprovals}
                className="shrink-0 rounded-full border px-2 py-1 text-[11px] text-[color:var(--ah-warning)]"
                style={{ borderColor: "color-mix(in srgb, var(--ah-warning) 40%, transparent)" }}
              >
                {approvals.length} 个待审批
              </button>
            )}
            {artifacts.length > 0 && (
              <span className="shrink-0 rounded-full border px-2 py-1 text-[11px] text-[color:var(--ah-muted)]" style={{ borderColor: "var(--ah-border)" }}>
                {artifacts.length} 个产物
              </span>
            )}
          </div>
        )}
      </div>
      {artifacts.length > 0 && (
        <ArtifactStrip artifacts={artifacts} onOpenArtifact={onOpenArtifact} />
      )}
      <MobileMessageList messages={messages} loading={loading} streaming={streaming} streamProgress={streamProgress} />
      <form onSubmit={onSend} className="shrink-0 border-t bg-[color:var(--ah-header-bg)] px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2" style={{ borderColor: "var(--ah-border)" }}>
        {streaming && streamProgress && (
          <div className="mb-2 flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2 text-xs text-[color:var(--ah-muted)]" style={{ borderColor: "var(--ah-border)" }}>
            <Loader2 size={14} className="shrink-0 animate-spin" />
            <span className="truncate">{streamProgress}</span>
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            value={composer}
            onChange={(event) => onComposerChange(event.target.value)}
            aria-label="输入移动端消息"
            placeholder="输入消息"
            rows={1}
            disabled={streaming}
            className="max-h-28 min-h-11 min-w-0 flex-1 resize-none rounded-lg border bg-[color:var(--ah-composer-bg)] px-3 py-2.5 text-sm leading-5 outline-none placeholder:text-[color:var(--ah-faint)] disabled:opacity-60"
            style={{ borderColor: "var(--ah-border)" }}
          />
          {streaming ? (
            <button
              type="button"
              onClick={onStopStreaming}
              aria-label="停止生成"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border text-[color:var(--ah-danger)]"
              style={{ borderColor: "color-mix(in srgb, var(--ah-danger) 38%, transparent)" }}
            >
              <XCircle size={18} />
            </button>
          ) : (
            <button
              type="submit"
              aria-label="发送消息"
              disabled={!composer.trim()}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[color:var(--ah-primary-bg)] text-[color:var(--ah-primary-text)] disabled:opacity-40"
            >
              <Send size={18} />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

function MobileMessageList({
  messages,
  loading,
  streaming,
  streamProgress,
}: {
  messages: Message[];
  loading: boolean;
  streaming: boolean;
  streamProgress: string | null;
}) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ block: "end" });
    }
  }, [messages.length, streaming, streamProgress]);

  if (loading) return <MobileLoading compact />;
  if (messages.length === 0) {
    return <EmptyState title="暂无消息" detail="发送第一条消息后，云端 Agent 会在这里回复。" compact />;
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
      <div className="space-y-3">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const name = isUser ? "我" : message.sourceName ?? message.agentName ?? "Agent";
  const trace = message.metadata?.executionTrace;
  return (
    <article className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[86%] rounded-lg border px-3 py-2 ${
          isUser
            ? "bg-[color:var(--ah-user-bg)] text-[color:var(--ah-user-text)]"
            : "bg-[color:var(--ah-card-bg)] text-[color:var(--ah-text)]"
        }`}
        style={{ borderColor: "var(--ah-border)" }}
      >
        <div className="mb-1 flex min-w-0 items-center gap-2 text-[11px] opacity-80">
          <span className="truncate font-medium">{name}</span>
          <span className="shrink-0">{formatRelativeTime(message.createdAt)}</span>
          {message.isCollaborating && <span className="shrink-0 rounded-full bg-[color:var(--ah-card-soft)] px-1.5 py-0.5">协作</span>}
        </div>
        <p className="whitespace-pre-wrap break-words text-sm leading-6">{message.content || (message.role === "assistant" ? "正在生成..." : "空消息")}</p>
        {(message.agentRole || message.taskName || message.phase) && (
          <p className="mt-2 text-[11px] opacity-70">
            {[message.agentRole, message.phase ? `Phase ${message.phase}` : null, message.taskName].filter(Boolean).join(" · ")}
          </p>
        )}
        {trace && (
          <div className="mt-2 rounded-lg border px-2 py-1.5 text-[11px] opacity-80" style={{ borderColor: "var(--ah-border)" }}>
            <span>{trace.status === "running" ? "运行中" : trace.status === "error" ? "运行失败" : "运行完成"}</span>
            <span> · {trace.items.length} 条执行记录</span>
          </div>
        )}
      </div>
    </article>
  );
}

function MobileArtifactIcon({ artifact }: { artifact: Artifact }) {
  const preview = getArtifactPreviewInfo(artifact);
  const className = "shrink-0 text-[color:var(--ah-text-strong)]";
  if (preview.kind === "html") return <Globe2 size={16} className={className} />;
  if (preview.kind === "diff") return <FileCode2 size={16} className={className} />;
  if (preview.kind === "file_tree") return <Files size={16} className={className} />;
  if (preview.kind === "image") return <FileImage size={16} className={className} />;
  return <FileText size={16} className={className} />;
}

function ArtifactStrip({
  artifacts,
  onOpenArtifact,
}: {
  artifacts: Artifact[];
  onOpenArtifact: (artifact: Artifact) => void;
}) {
  return (
    <div className="shrink-0 border-b px-3 py-2" style={{ borderColor: "var(--ah-border)" }}>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {artifacts.slice(0, 8).map((artifact) => (
          <button
            key={artifact.id}
            type="button"
            onClick={() => onOpenArtifact(artifact)}
            className="flex min-w-[11rem] shrink-0 items-center gap-2 rounded-lg border bg-[color:var(--ah-card-bg)] px-3 py-2 text-left"
            style={{ borderColor: "var(--ah-border)" }}
          >
            <MobileArtifactIcon artifact={artifact} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium text-[color:var(--ah-text-strong)]">{artifact.title}</span>
              <span className="block text-[11px] text-[color:var(--ah-faint)]">{getArtifactPreviewInfo(artifact).shortLabel} · v{artifact.version}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ArtifactPane({
  session,
  artifacts,
  renderedArtifact,
  loading,
  onBack,
  onOpenArtifact,
}: {
  session: Session | null;
  artifacts: Artifact[];
  renderedArtifact: RenderedArtifact | null;
  loading: boolean;
  onBack: () => void;
  onOpenArtifact: (artifact: Artifact) => void;
}) {
  if (!session) {
    return <EmptyState title="请选择对话" detail="进入会话后即可预览该对话的产物。" />;
  }
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <PaneHeader icon={ArrowLeft} title="产物预览" subtitle={session.title} onIconClick={onBack} />
      {artifacts.length === 0 ? (
        <EmptyState title="暂无 Artifact" detail="会话生成的网页、文档和文件树会显示在这里。" compact />
      ) : (
        <div className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] overflow-hidden">
          <div className="flex gap-2 overflow-x-auto border-b px-3 py-2" style={{ borderColor: "var(--ah-border)" }}>
            {artifacts.map((artifact) => (
              <button
                key={artifact.id}
                type="button"
                onClick={() => onOpenArtifact(artifact)}
                className="flex min-w-[12rem] shrink-0 items-center gap-2 rounded-lg border bg-[color:var(--ah-card-bg)] px-3 py-2 text-left"
                style={{ borderColor: "var(--ah-border)" }}
              >
                <MobileArtifactIcon artifact={artifact} />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-[color:var(--ah-text-strong)]">{artifact.title}</span>
                  <span className="block text-[11px] text-[color:var(--ah-faint)]">
                    {getArtifactPreviewInfo(artifact).shortLabel} · {artifact.status} · v{artifact.version}
                  </span>
                </span>
              </button>
            ))}
          </div>
          <div className="min-h-0 overflow-hidden p-3">
            {loading ? (
              <MobileLoading compact />
            ) : renderedArtifact ? (
              <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border bg-white" style={{ borderColor: "var(--ah-border)" }}>
                <div className="shrink-0 border-b px-3 py-2 text-xs text-slate-700" style={{ borderColor: "var(--ah-border)" }}>
                  {renderedArtifact.fileName}
                </div>
                <iframe
                  title="移动端 Artifact 预览"
                  srcDoc={renderedArtifact.content}
                  sandbox="allow-scripts"
                  className="min-h-0 flex-1 border-0 bg-white"
                />
              </div>
            ) : (
              <EmptyState title="选择一个产物" detail="点击上方产物即可打开移动端预览。" compact />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ApprovalPane({
  approvals,
  session,
  busyApprovalId,
  onBack,
  onApprove,
  onReject,
}: {
  approvals: ApprovalCheckpoint[];
  session: Session | null;
  busyApprovalId: string | null;
  onBack: () => void;
  onApprove: (approval: ApprovalCheckpoint) => void;
  onReject: (approval: ApprovalCheckpoint) => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <PaneHeader icon={ArrowLeft} title="移动审批" subtitle={session?.title ?? "当前对话"} onIconClick={onBack} />
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {approvals.length === 0 ? (
          <EmptyState title="暂无待审批" detail="需要你处理的运行确认会显示在这里。" compact />
        ) : (
          <div className="space-y-3">
            {approvals.map((approval) => {
              const busy = busyApprovalId === approval.id;
              return (
                <article key={approval.id} className="rounded-lg border bg-[color:var(--ah-card-bg)] px-3 py-3" style={{ borderColor: "var(--ah-border)" }}>
                  <p className="text-sm font-semibold text-[color:var(--ah-text-strong)]">{approval.title}</p>
                  <p className="mt-1 text-sm leading-6 text-[color:var(--ah-muted)]">{approval.summary}</p>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => onReject(approval)}
                      disabled={busy}
                      className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border text-sm text-[color:var(--ah-danger)] disabled:opacity-50"
                      style={{ borderColor: "color-mix(in srgb, var(--ah-danger) 34%, transparent)" }}
                    >
                      {busy ? <Loader2 size={15} className="animate-spin" /> : <XCircle size={15} />}
                      驳回
                    </button>
                    <button
                      type="button"
                      onClick={() => onApprove(approval)}
                      disabled={busy}
                      className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-[color:var(--ah-primary-bg)] text-sm font-medium text-[color:var(--ah-primary-text)] disabled:opacity-50"
                    >
                      {busy ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
                      同意
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function NotificationPane({
  notifications,
  busyNotificationId,
  onRead,
}: {
  notifications: HubNotification[];
  busyNotificationId: string | null;
  onRead: (notification: HubNotification) => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <PaneHeader icon={Bell} title="通知" subtitle={`${notifications.filter((item) => !item.readAt).length} 条未读`} />
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {notifications.length === 0 ? (
          <EmptyState title="暂无通知" detail="评论、审批和协作提醒会集中显示在这里。" compact />
        ) : (
          <div className="space-y-2">
            {notifications.map((notification) => (
              <button
                key={notification.id}
                type="button"
                onClick={() => onRead(notification)}
                className="flex w-full min-w-0 items-start gap-3 rounded-lg border bg-[color:var(--ah-card-bg)] px-3 py-3 text-left"
                style={{ borderColor: notification.readAt ? "var(--ah-border)" : "var(--ah-border-strong)" }}
              >
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[color:var(--ah-card-soft)] text-[color:var(--ah-text-strong)]">
                  {busyNotificationId === notification.id ? <Loader2 size={15} className="animate-spin" /> : <Bell size={15} />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-[color:var(--ah-text-strong)]">{notification.title}</span>
                  {notification.body && <span className="mt-1 block line-clamp-3 text-sm leading-6 text-[color:var(--ah-muted)]">{notification.body}</span>}
                  <span className="mt-2 block text-[11px] text-[color:var(--ah-faint)]">
                    {notification.readAt ? "已读" : "未读"} · {formatRelativeTime(notification.createdAt)}
                  </span>
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PaneHeader({
  icon: Icon,
  title,
  subtitle,
  onIconClick,
}: {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  onIconClick?: () => void;
}) {
  const iconNode = <Icon size={17} />;
  return (
    <div className="shrink-0 border-b bg-[color:var(--ah-header-bg)] px-3 py-3" style={{ borderColor: "var(--ah-border)" }}>
      <div className="flex min-w-0 items-center gap-2">
        {onIconClick ? (
          <IconButton icon={Icon} label={title === "产物预览" || title === "移动审批" ? "返回对话" : title} onClick={onIconClick} />
        ) : (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border text-[color:var(--ah-text-strong)]" style={{ borderColor: "var(--ah-border)" }}>
            {iconNode}
          </span>
        )}
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-[color:var(--ah-text-strong)]">{title}</h2>
          <p className="truncate text-[11px] text-[color:var(--ah-faint)]">{subtitle}</p>
        </div>
      </div>
    </div>
  );
}

function ProfileSheet({
  user,
  projects,
  sessionCount,
  unreadTotal,
  onClose,
}: {
  user: CurrentUser | null;
  projects: Project[];
  sessionCount: number;
  unreadTotal: number;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-[color:var(--ah-overlay)] px-3 pb-3" role="dialog" aria-modal="true">
      <section className="w-full rounded-lg border bg-[color:var(--ah-modal-bg)] px-4 py-4" style={{ borderColor: "var(--ah-border)" }}>
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-full border bg-[color:var(--ah-card-soft)] text-sm font-semibold text-[color:var(--ah-text-strong)]" style={{ borderColor: "var(--ah-border)" }}>
            <UserAvatar user={user} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-semibold text-[color:var(--ah-text-strong)]">{user?.displayName ?? "未登录用户"}</p>
            <p className="truncate text-sm text-[color:var(--ah-muted)]">{user?.username ? `@${user.username}` : user?.email ?? "云端账号"}</p>
          </div>
          <IconButton icon={X} label="关闭个人信息" onClick={onClose} />
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2">
          <ProfileStat label="项目" value={projects.length} />
          <ProfileStat label="对话" value={sessionCount} />
          <ProfileStat label="未读" value={unreadTotal} />
        </div>
        <div className="mt-4 rounded-lg border px-3 py-3 text-sm" style={{ borderColor: "var(--ah-border)" }}>
          <p className="text-[color:var(--ah-faint)]">默认空间</p>
          <p className="mt-1 truncate font-medium text-[color:var(--ah-text-strong)]">{user?.defaultSpace?.name ?? "个人空间"}</p>
        </div>
      </section>
    </div>
  );
}

function ProfileStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border bg-[color:var(--ah-card-bg)] px-3 py-2 text-center" style={{ borderColor: "var(--ah-border)" }}>
      <p className="text-base font-semibold text-[color:var(--ah-text-strong)]">{value}</p>
      <p className="text-[11px] text-[color:var(--ah-faint)]">{label}</p>
    </div>
  );
}

function IconButton({
  icon: Icon,
  label,
  busy = false,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  busy?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      disabled={busy}
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border text-[color:var(--ah-text-strong)] transition active:scale-95 disabled:opacity-50"
      style={{ borderColor: "var(--ah-border)" }}
    >
      {busy ? <Loader2 size={16} className="animate-spin" /> : <Icon size={16} />}
    </button>
  );
}

function MobileNavButton({
  icon: Icon,
  label,
  active,
  disabled = false,
  count,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  active: boolean;
  disabled?: boolean;
  count?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`relative flex min-h-12 min-w-0 flex-col items-center justify-center gap-1 rounded-lg text-[11px] transition disabled:opacity-40 ${
        active ? "bg-[color:var(--ah-highlight-bg)] text-[color:var(--ah-text-strong)]" : "text-[color:var(--ah-muted)]"
      }`}
    >
      <Icon size={16} />
      <span className="truncate">{label}</span>
      {Boolean(count) && <Badge floating>{count ?? 0}</Badge>}
    </button>
  );
}

function Badge({ children, floating = false }: { children: number; floating?: boolean }) {
  return (
    <span className={`${floating ? "absolute right-2 top-1" : ""} inline-flex min-w-5 items-center justify-center rounded-full bg-[color:var(--ah-unread-bg)] px-1.5 py-0.5 text-[10px] font-semibold text-[color:var(--ah-unread-text)]`}>
      {children > 99 ? "99+" : children}
    </span>
  );
}

function UserAvatar({ user }: { user: CurrentUser | null }) {
  if (user?.avatarUrl) {
    return <img src={user.avatarUrl} alt="" className="h-full w-full object-cover" />;
  }
  if (!user) return <User size={18} />;
  return <>{initials(user.displayName || user.username || user.email)}</>;
}

function MobileLoading({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`space-y-2 px-3 ${compact ? "py-3" : "pt-8"}`} aria-label="正在加载移动端数据">
      {Array.from({ length: compact ? 3 : 6 }).map((_, index) => (
        <div key={index} className="h-16 animate-pulse rounded-lg border bg-[color:var(--ah-card-soft)]" style={{ borderColor: "var(--ah-border)" }} />
      ))}
    </div>
  );
}

function EmptyState({ title, detail, compact = false }: { title: string; detail: string; compact?: boolean }) {
  return (
    <div className={`mx-3 flex flex-col items-center justify-center rounded-lg border px-4 text-center ${compact ? "my-3 min-h-48" : "my-6 min-h-64"}`} style={{ borderColor: "var(--ah-border)" }}>
      <p className="text-base font-semibold text-[color:var(--ah-text-strong)]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[color:var(--ah-muted)]">{detail}</p>
    </div>
  );
}

function sortSessions(sessions: Session[]): Session[] {
  return [...sessions].sort((left, right) => {
    if (Boolean(left.archivedAt) !== Boolean(right.archivedAt)) return left.archivedAt ? 1 : -1;
    if (Boolean(left.isPinned) !== Boolean(right.isPinned)) return left.isPinned ? -1 : 1;
    const unreadDelta = (right.unreadCount ?? 0) - (left.unreadCount ?? 0);
    if (unreadDelta !== 0) return unreadDelta;
    return new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime();
  });
}

function initials(value: string): string {
  const text = value.trim();
  if (!text) return "AH";
  return text.slice(0, 2).toUpperCase();
}

function formatRelativeTime(value?: string | null): string {
  if (!value) return "暂无";
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return "刚刚";
  const diff = Date.now() - time;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.max(1, Math.floor(diff / 60_000))} 分钟前`;
  if (diff < 86_400_000) return `${Math.max(1, Math.floor(diff / 3_600_000))} 小时前`;
  if (diff < 604_800_000) return `${Math.max(1, Math.floor(diff / 86_400_000))} 天前`;
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(value));
}
