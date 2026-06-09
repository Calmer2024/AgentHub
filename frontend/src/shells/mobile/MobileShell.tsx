import { useCallback, useEffect, useMemo, useState } from "react";
import { Bell, CheckCircle2, FileText, Loader2, MessageCircle, XCircle, type LucideIcon } from "lucide-react";
import {
  decideMobileApproval,
  fetchApprovals,
  fetchArtifacts,
  fetchMessages,
  fetchMobileSessions,
  fetchNotifications,
  renderArtifact,
} from "../../api/client";
import type {
  ApprovalCheckpoint,
  Artifact,
  Message,
  MobileSessionSummary,
  Notification as HubNotification,
  RenderedArtifact,
} from "../../types";

type MobileTab = "sessions" | "notifications" | "approvals" | "artifacts";

export function MobileShell() {
  const [tab, setTab] = useState<MobileTab>("sessions");
  const [sessions, setSessions] = useState<MobileSessionSummary[]>([]);
  const [notifications, setNotifications] = useState<HubNotification[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [approvals, setApprovals] = useState<ApprovalCheckpoint[]>([]);
  const [renderedArtifact, setRenderedArtifact] = useState<RenderedArtifact | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busyApprovalId, setBusyApprovalId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [activeSessionId, sessions],
  );
  const pendingApprovals = approvals.filter((approval) => approval.status === "pending_review");

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sessionItems, notificationItems] = await Promise.all([
        fetchMobileSessions(),
        fetchNotifications(),
      ]);
      setSessions(sessionItems);
      setNotifications(notificationItems);
      setActiveSessionId((current) => current ?? sessionItems[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "移动端数据加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSessionDetail = useCallback(async (sessionId: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      const [messageItems, artifactItems, approvalItems] = await Promise.all([
        fetchMessages(sessionId),
        fetchArtifacts(sessionId),
        fetchApprovals(sessionId),
      ]);
      setMessages(messageItems);
      setArtifacts(artifactItems);
      setApprovals(approvalItems);
      setRenderedArtifact(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "会话详情加载失败");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (activeSessionId) void loadSessionDetail(activeSessionId);
  }, [activeSessionId, loadSessionDetail]);

  const decideApproval = async (approval: ApprovalCheckpoint, decision: "approve" | "reject") => {
    setBusyApprovalId(approval.id);
    setError(null);
    try {
      await decideMobileApproval(approval.id, {
        decision,
        comment: decision === "approve" ? "移动端同意" : "移动端驳回",
      });
      if (activeSessionId) await loadSessionDetail(activeSessionId);
      await loadOverview();
    } catch (err) {
      setError(err instanceof Error ? err.message : "审批操作失败");
    } finally {
      setBusyApprovalId(null);
    }
  };

  const openArtifact = async (artifact: Artifact) => {
    setDetailLoading(true);
    setError(null);
    try {
      setRenderedArtifact(await renderArtifact(artifact.id, "html"));
      setTab("artifacts");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Artifact 渲染失败");
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <main className="agenthub-shell flex h-[100dvh] w-screen max-w-full min-w-0 flex-col overflow-hidden">
      <header className="agenthub-header border-b px-4 py-3">
        <p className="agenthub-faint text-[11px]">AgentHub Mobile</p>
        <h1 className="agenthub-strong truncate text-base font-semibold">
          {activeSession?.title ?? "移动协作"}
        </h1>
      </header>

      {error && (
        <div className="agenthub-status-error mx-3 mt-3 rounded-lg border px-3 py-2 text-sm">
          {error}
        </div>
      )}

      <section className="min-h-0 min-w-0 max-w-full flex-1 overflow-y-auto overflow-x-hidden px-3 py-3">
        {loading ? (
          <MobileLoading />
        ) : tab === "sessions" ? (
          <MobileSessionList
            sessions={sessions}
            activeSessionId={activeSessionId}
            messages={messages}
            loading={detailLoading}
            onSelect={(sessionId) => {
              setActiveSessionId(sessionId);
              setTab("sessions");
            }}
            onOpenArtifact={openArtifact}
            artifacts={artifacts}
          />
        ) : tab === "notifications" ? (
          <MobileNotificationView notifications={notifications} />
        ) : tab === "approvals" ? (
          <MobileApprovalView
            approvals={pendingApprovals}
            busyApprovalId={busyApprovalId}
            onApprove={(approval) => void decideApproval(approval, "approve")}
            onReject={(approval) => void decideApproval(approval, "reject")}
          />
        ) : (
          <MobileArtifactView
            artifacts={artifacts}
            renderedArtifact={renderedArtifact}
            loading={detailLoading}
            onOpenArtifact={(artifact) => void openArtifact(artifact)}
          />
        )}
      </section>

      <nav className="agenthub-header grid w-full min-w-0 max-w-full shrink-0 grid-cols-[repeat(4,minmax(0,1fr))] gap-1 overflow-hidden border-t px-2 py-2">
        <MobileNavButton icon={MessageCircle} label="会话" active={tab === "sessions"} onClick={() => setTab("sessions")} />
        <MobileNavButton icon={Bell} label="通知" active={tab === "notifications"} onClick={() => setTab("notifications")} />
        <MobileNavButton icon={CheckCircle2} label="审批" active={tab === "approvals"} onClick={() => setTab("approvals")} />
        <MobileNavButton icon={FileText} label="产物" active={tab === "artifacts"} onClick={() => setTab("artifacts")} />
      </nav>
    </main>
  );
}

function MobileSessionList({
  sessions,
  activeSessionId,
  messages,
  artifacts,
  loading,
  onSelect,
  onOpenArtifact,
}: {
  sessions: MobileSessionSummary[];
  activeSessionId: string | null;
  messages: Message[];
  artifacts: Artifact[];
  loading: boolean;
  onSelect: (sessionId: string) => void;
  onOpenArtifact: (artifact: Artifact) => Promise<void>;
}) {
  if (sessions.length === 0) {
    return <EmptyState title="暂无会话" detail="有新协作消息或审批后会出现在这里。" />;
  }
  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {sessions.map((session) => (
          <button
            key={session.id}
            type="button"
            onClick={() => onSelect(session.id)}
            className={`agenthub-nav-idle flex w-full min-w-0 max-w-full items-center justify-between overflow-hidden rounded-lg border px-3 py-3 text-left ${
              activeSessionId === session.id ? "agenthub-nav-active" : ""
            }`}
          >
            <span className="min-w-0 max-w-full">
              <span className="agenthub-strong block truncate text-sm font-semibold">{session.title}</span>
              <span className="agenthub-faint mt-1 block text-xs">
                未读 {session.unreadCount} · 待审批 {session.pendingApprovalCount}
              </span>
            </span>
          </button>
        ))}
      </div>
      <section className="border-t pt-3" style={{ borderColor: "var(--ah-border)" }}>
        {loading ? (
          <MobileLoading compact />
        ) : (
          <div className="space-y-2">
            {messages.slice(-6).map((message) => (
              <div key={message.id} className="agenthub-card rounded-lg border px-3 py-2 text-sm">
                <p className="agenthub-faint text-[11px]">{message.role === "user" ? "用户" : message.agentName ?? "Agent"}</p>
                <p className="agenthub-strong mt-1 line-clamp-3 whitespace-pre-wrap">{message.content || "空消息"}</p>
              </div>
            ))}
            {artifacts.length > 0 && (
              <div className="grid gap-2">
                {artifacts.slice(0, 3).map((artifact) => (
                  <button
                    key={artifact.id}
                    type="button"
                    onClick={() => void onOpenArtifact(artifact)}
                    className="agenthub-nav-idle rounded-lg border px-3 py-2 text-left text-sm"
                  >
                    <span className="agenthub-strong block truncate">{artifact.title}</span>
                    <span className="agenthub-faint mt-1 block text-xs">{artifact.type} · v{artifact.version}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function MobileNotificationView({ notifications }: { notifications: HubNotification[] }) {
  if (notifications.length === 0) {
    return <EmptyState title="暂无通知" detail="评论、审批和协作提醒会集中显示在这里。" />;
  }
  return (
    <div className="space-y-2">
      {notifications.map((item) => (
        <div key={item.id} className="agenthub-card rounded-lg border px-3 py-3">
          <p className="agenthub-strong text-sm font-semibold">{item.title}</p>
          {item.body && <p className="agenthub-muted mt-1 text-sm leading-6">{item.body}</p>}
          <p className="agenthub-faint mt-2 text-[11px]">{item.readAt ? "已读" : "未读"}</p>
        </div>
      ))}
    </div>
  );
}

function MobileApprovalView({
  approvals,
  busyApprovalId,
  onApprove,
  onReject,
}: {
  approvals: ApprovalCheckpoint[];
  busyApprovalId: string | null;
  onApprove: (approval: ApprovalCheckpoint) => void;
  onReject: (approval: ApprovalCheckpoint) => void;
}) {
  if (approvals.length === 0) {
    return <EmptyState title="暂无待审批" detail="需要你处理的运行确认会显示在这里。" />;
  }
  return (
    <div className="space-y-3">
      {approvals.map((approval) => {
        const busy = busyApprovalId === approval.id;
        return (
          <div key={approval.id} className="agenthub-card rounded-lg border px-3 py-3">
            <p className="agenthub-strong text-sm font-semibold">{approval.title}</p>
            <p className="agenthub-muted mt-1 text-sm leading-6">{approval.summary}</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => onReject(approval)}
                disabled={busy}
                className="agenthub-icon-button inline-flex h-10 items-center justify-center gap-2 rounded-lg text-sm disabled:opacity-50"
              >
                {busy ? <Loader2 size={15} className="animate-spin" /> : <XCircle size={15} />}
                驳回
              </button>
              <button
                type="button"
                onClick={() => onApprove(approval)}
                disabled={busy}
                className="agenthub-primary-button inline-flex h-10 items-center justify-center gap-2 rounded-lg text-sm font-medium disabled:opacity-50"
              >
                {busy ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
                同意
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MobileArtifactView({
  artifacts,
  renderedArtifact,
  loading,
  onOpenArtifact,
}: {
  artifacts: Artifact[];
  renderedArtifact: RenderedArtifact | null;
  loading: boolean;
  onOpenArtifact: (artifact: Artifact) => void;
}) {
  if (artifacts.length === 0) {
    return <EmptyState title="暂无 Artifact" detail="会话中的产物和预览摘要会显示在这里。" />;
  }
  return (
    <div className="space-y-3">
      <div className="grid gap-2">
        {artifacts.map((artifact) => (
          <button
            key={artifact.id}
            type="button"
            onClick={() => onOpenArtifact(artifact)}
            className="agenthub-nav-idle rounded-lg border px-3 py-2 text-left text-sm"
          >
            <span className="agenthub-strong block truncate">{artifact.title}</span>
            <span className="agenthub-faint mt-1 block text-xs">{artifact.type} · {artifact.status}</span>
          </button>
        ))}
      </div>
      {loading ? (
        <MobileLoading compact />
      ) : renderedArtifact && (
        <div className="agenthub-card overflow-hidden rounded-lg border">
          <div className="agenthub-header border-b px-3 py-2 text-xs">{renderedArtifact.fileName}</div>
          <iframe
            title="移动端 Artifact 预览"
            srcDoc={renderedArtifact.content}
            sandbox="allow-scripts"
            className="h-[56dvh] w-full border-0 bg-white"
          />
        </div>
      )}
    </div>
  );
}

function MobileNavButton({
  icon: Icon,
  label,
  active,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex min-h-12 min-w-0 flex-col items-center justify-center gap-1 rounded-lg text-[11px] ${
        active ? "agenthub-nav-active" : "agenthub-nav-idle"
      }`}
    >
      <Icon size={16} />
      {label}
    </button>
  );
}

function MobileLoading({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`space-y-2 ${compact ? "" : "pt-8"}`} aria-label="正在加载移动端数据">
      {Array.from({ length: compact ? 2 : 5 }).map((_, index) => (
        <div key={index} className="agenthub-skeleton h-16 animate-pulse rounded-lg border" />
      ))}
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="agenthub-muted flex min-h-64 flex-col items-center justify-center rounded-lg border px-4 text-center">
      <p className="agenthub-strong text-base font-semibold">{title}</p>
      <p className="mt-2 text-sm leading-6">{detail}</p>
    </div>
  );
}
