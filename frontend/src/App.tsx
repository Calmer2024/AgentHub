import { forwardRef, useCallback, useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import {
  Building2,
  Check,
  Copy,
  FolderOpen,
  HardDrive,
  MessageCircle,
  Monitor,
  Moon,
  PanelLeftClose,
  Plus,
  Settings,
  Sun,
  Trash2,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useChatStore, type CollabSnapshot } from "./stores/chatStore";
import { ActivityPanelContent, type ActivityPanel } from "./components/ActivityPanelContent";
import { MemoChatWindow as ChatWindow } from "./components/ChatWindow";
import { AgentPanel } from "./components/AgentPanel";
import { FloatingMenu } from "./components/FloatingMenu";
import { GroupChatCreator } from "./components/GroupChatCreator";
import { ToastViewport } from "./components/ToastViewport";
import { OrchestratorDebugPanel } from "./components/OrchestratorDebugPanel";
import { ProjectFileWorkspaceModal } from "./components/ProjectFileWorkspaceModal";
import { BrandLogo } from "./components/BrandLogo";
import { DesktopTitleBar } from "./components/DesktopTitleBar";
import { useCapabilities } from "./app/ShellProvider";
import { CloudWorkspaceSettings } from "./shells/saas/CloudWorkspaceSettings";
import { AppSettingsPage } from "./components/AppSettingsPage";
import {
  deleteAgent,
  addTeamMember,
  fetchTeamMembers,
  fetchTeamJoinCode,
  fetchArtifacts,
  fetchMessages,
  markSessionRead,
  removeTeamMember,
  pinMessage,
  regenerateMessageStream,
  updateTeamMemberRole,
  unpinMessage,
} from "./api/client";
import { useSendMessage } from "./hooks/useSendMessage";
import { useWorkspaceRuntime } from "./hooks/useWorkspaceRuntime";
import { useThemeStore } from "./stores/themeStore";
import { useToastStore } from "./stores/toastStore";
import type { AgentConfig, Message, Project, Team, TeamMember, TeamRole } from "./types";

type RailFloatingMenu = "workspace" | "teams";

const ACTIVITY_PANEL_WIDTH_STORAGE_KEY = "agenthub.activityPanelWidth";
const ACTIVITY_PANEL_MIN_WIDTH = 248;
const ACTIVITY_PANEL_MAX_WIDTH = 480;

function clampActivityPanelWidth(width: number) {
  return Math.min(ACTIVITY_PANEL_MAX_WIDTH, Math.max(ACTIVITY_PANEL_MIN_WIDTH, width));
}

function readActivityPanelWidth() {
  if (typeof window === "undefined") return 306;
  const stored = Number(window.localStorage.getItem(ACTIVITY_PANEL_WIDTH_STORAGE_KEY));
  return Number.isFinite(stored) && stored > 0 ? clampActivityPanelWidth(stored) : 306;
}

/** 从 store 读取当前会话的协作状态（零值 = 空快照）。 */
function emptyCollab(): CollabSnapshot {
  return {
    routeAgents: null,
    collabTasks: [],
    dagPhases: [],
    chainSteps: [],
    orchestratorIntent: null,
    planSummary: null,
    collabCompleted: false,
    collabSummary: null,
    draftPlan: null,
  };
}

const EMPTY_COLLAB = emptyCollab();

export function AgentHubWorkbench() {
  const { capabilities, edition } = useCapabilities();
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const messages = useChatStore((state) => state.messages);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const streamingError = useChatStore((state) => state.streamingError);
  const artifacts = useChatStore((state) => state.artifacts);
  const setMessagesForSession = useChatStore((state) => state.setMessagesForSession);
  const setArtifactsForSession = useChatStore((state) => state.setArtifactsForSession);
  const setStreamingError = useChatStore((state) => state.setStreamingError);
  const setReplyTarget = useChatStore((state) => state.setReplyTarget);
  const updateMessage = useChatStore((state) => state.updateMessage);
  const replaceSessionMessageContent = useChatStore((state) => state.replaceSessionMessageContent);

  const {
    projects, currentProjectId, currentProject, sessions, agents, sidebarTab,
    creatingProject, initialLoading, sessionsLoading, sessionHydrating, sessionMembers, sessionMembersLoading,
    currentAgent, currentMode,
    currentUser, teams, currentTeamId, setCurrentTeamId,
    setSidebarTab, loadData,
    handleSelectProject, handleArchiveProject,
    handleRenameProject, handleDeleteProject,
    handleCreateTeam, handleJoinTeam,
    handleCreateBlankProject, handleCreateCloudProject, handlePickExistingFolder,
    handleSelectSession, handleNewSession, handleCreateGroup,
    handleAddGroupMember, handleRemoveGroupMember,
    handleDeleteSession, handleRenameSession, handlePinSession, handleArchiveSession,
    handleMuteSession,
  } = useWorkspaceRuntime({
    projectMode: edition === "local" ? "local" : "cloud",
    loadCloudIdentity: edition === "saas",
  });

  // --- 协作状态的读写桥接 (store ↔ 组件) ---
  const collabKey = currentSessionId ?? "__none__";
  const activeCollab = useChatStore((state) => state.collabSnapshots[collabKey]);
  const collab = activeCollab ?? EMPTY_COLLAB;

  const routeAgents = collab.routeAgents;
  const collabTasks = collab.collabTasks;
  const dagPhases = collab.dagPhases;
  const chainSteps = collab.chainSteps;
  const orchestratorIntent = collab.orchestratorIntent;
  const planSummary = collab.planSummary;
  const collabCompleted = collab.collabCompleted;
  const collabSummary = collab.collabSummary;
  const draftPlan = collab.draftPlan;

  const [showGroupCreator, setShowGroupCreator] = useState(false);
  const [agentModal, setAgentModal] = useState<{ mode: "create" | "edit"; agentId?: string } | null>(null);
  const [appRoute, setAppRoute] = useState(() => window.location.hash || "#/");
  const [fileWorkspaceOpen, setFileWorkspaceOpen] = useState(false);
  const [fileWorkspaceInitialPath, setFileWorkspaceInitialPath] = useState<string | null>(null);
  const effectiveSidebarTab = sidebarTab;
  const [activityPanel, setActivityPanel] = useState<ActivityPanel | null>("sessions");
  const [activityPanelWidth, setActivityPanelWidth] = useState(readActivityPanelWidth);
  const [resizingActivityPanel, setResizingActivityPanel] = useState(false);
  const [pendingProjectSession, setPendingProjectSession] = useState<{ projectId: string; agentId: string } | null>(null);
  const handleSend = useSendMessage();
  const pushToast = useToastStore((state) => state.pushToast);

  useEffect(() => {
    const syncRoute = () => setAppRoute(window.location.hash || "#/");
    window.addEventListener("hashchange", syncRoute);
    return () => window.removeEventListener("hashchange", syncRoute);
  }, []);

  useEffect(() => {
    if (effectiveSidebarTab === "sessions" || effectiveSidebarTab === "agents") {
      setActivityPanel(effectiveSidebarTab);
    }
  }, [effectiveSidebarTab]);

  const notifyError = useCallback((title: string, error: unknown) => {
    pushToast({
      kind: "error",
      title,
      description: error instanceof Error ? error.message : "请稍后重试",
    });
  }, [pushToast]);

  const openProjectFiles = useCallback((path?: string | null) => {
    setFileWorkspaceInitialPath(path ?? null);
    setFileWorkspaceOpen(true);
  }, []);

  const toggleProjectFiles = useCallback(() => {
    if (!currentProjectId) return;
    setFileWorkspaceInitialPath(null);
    setFileWorkspaceOpen((value) => !value);
  }, [currentProjectId]);

  const toggleActivityPanel = useCallback((panel: ActivityPanel) => {
    setActivityPanel((current) => (current === panel ? null : panel));
    if (panel === "sessions" || panel === "agents") setSidebarTab(panel);
  }, [setSidebarTab]);

  useEffect(() => {
    window.localStorage.setItem(ACTIVITY_PANEL_WIDTH_STORAGE_KEY, String(activityPanelWidth));
  }, [activityPanelWidth]);

  const beginActivityPanelResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = activityPanelWidth;
    setResizingActivityPanel(true);
    document.body.classList.add("agenthub-resizing-panel");

    const resize = (moveEvent: PointerEvent) => {
      setActivityPanelWidth(clampActivityPanelWidth(startWidth + moveEvent.clientX - startX));
    };
    const finish = () => {
      window.removeEventListener("pointermove", resize);
      window.removeEventListener("pointerup", finish);
      document.body.classList.remove("agenthub-resizing-panel");
      setResizingActivityPanel(false);
    };

    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", finish, { once: true });
  }, [activityPanelWidth]);

  const resizeActivityPanelWithKeyboard = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    setActivityPanelWidth((width) => clampActivityPanelWidth(width + (event.key === "ArrowRight" ? 16 : -16)));
  }, []);

  const handleSelectProjectSession = useCallback((projectId: string, sessionId: string) => {
    if (projectId !== currentProjectId) {
      void handleSelectProject(projectId);
    }
    void handleSelectSession(sessionId);
    setSidebarTab("sessions");
  }, [currentProjectId, handleSelectProject, handleSelectSession, setSidebarTab]);

  const handleNewProjectSession = useCallback(async (projectId: string, agentId: string) => {
    if (projectId !== currentProjectId) {
      setPendingProjectSession({ projectId, agentId });
      handleSelectProject(projectId);
      return;
    }
    await handleNewSession(agentId);
    setSidebarTab("sessions");
    setActivityPanel("sessions");
  }, [currentProjectId, handleNewSession, handleSelectProject, setSidebarTab]);

  useEffect(() => {
    if (!pendingProjectSession || pendingProjectSession.projectId !== currentProjectId) return;
    setPendingProjectSession(null);
    void handleNewSession(pendingProjectSession.agentId).then(() => {
      setSidebarTab("sessions");
      setActivityPanel("sessions");
    });
  }, [currentProjectId, handleNewSession, pendingProjectSession, setSidebarTab]);

  useEffect(() => {
    const onOpenProjectFile = (event: Event) => {
      const detail = (event as CustomEvent<{ projectId?: string | null; path?: string | null }>).detail;
      if (detail?.projectId && detail.projectId !== currentProjectId) {
        void handleSelectProject(detail.projectId);
      }
      openProjectFiles(detail?.path ?? null);
    };
    window.addEventListener("agenthub:open-project-file", onOpenProjectFile);
    return () => window.removeEventListener("agenthub:open-project-file", onOpenProjectFile);
  }, [currentProjectId, handleSelectProject, openProjectFiles]);

  const runCrudAction = useCallback(async (
    action: () => Promise<void>,
    successTitle: string,
    errorTitle: string,
    description?: string,
  ) => {
    try {
      await action();
      pushToast({ kind: "success", title: successTitle, description });
    } catch (error) {
      notifyError(errorTitle, error);
    }
  }, [notifyError, pushToast]);

  const handleTogglePin = useCallback(async (message: Message) => {
    try {
      if (message.isPinned) {
        await unpinMessage(message.id);
        updateMessage(message.id, { isPinned: false });
        pushToast({ kind: "success", title: "已取消 Pin" });
      } else {
        await pinMessage(message.id);
        updateMessage(message.id, { isPinned: true });
        pushToast({ kind: "success", title: "消息已 Pin" });
      }
    } catch {
      setStreamingError("Pin 操作失败，请稍后重试", message.sessionId || currentSessionId);
      pushToast({ kind: "error", title: "Pin 操作失败" });
    }
  }, [currentSessionId, pushToast, setStreamingError, updateMessage]);

  const handleRegenerate = useCallback((message: Message) => {
    const sessionId = message.sessionId || currentSessionId;
    if (!sessionId) return;
    const streamKey = `regenerate-${sessionId}-${message.id}-${Date.now()}`;
    setStreamingError(null, sessionId);
    useChatStore.getState().startStreamRun(sessionId, streamKey);
    replaceSessionMessageContent(sessionId, message.id, "");
    const abort = regenerateMessageStream(message.id, {
      onToken: (token) => {
        const state = useChatStore.getState();
        const current = (state.messagesBySession[sessionId] ?? state.messages)
          .find((m) => m.id === message.id)?.content ?? "";
        state.replaceSessionMessageContent(sessionId, message.id, current + token);
      },
      onDone: async (_messageId, error) => {
        useChatStore.getState().finishStreamRun(streamKey, sessionId);
        if (error) {
          setStreamingError(error === "重新生成超时" ? error : `重新生成失败：${error}`, sessionId);
          replaceSessionMessageContent(sessionId, message.id, message.content);
          return;
        }
        try {
          setMessagesForSession(sessionId, await fetchMessages(sessionId));
        } catch { /* */ }
        try {
          setArtifactsForSession(sessionId, await fetchArtifacts(sessionId));
        } catch { /* */ }
        markSessionRead(sessionId).catch(() => {});
      },
    });
    useChatStore.getState().setActiveStreamAbort(streamKey, abort);
  }, [
    currentSessionId,
    replaceSessionMessageContent,
    setArtifactsForSession,
    setMessagesForSession,
    setStreamingError,
  ]);

  const handleArtifactsChanged = useCallback(async () => {
    if (!currentSessionId) return;
    try {
      setArtifactsForSession(currentSessionId, await fetchArtifacts(currentSessionId));
    } catch { /* */ }
  }, [currentSessionId, setArtifactsForSession]);

  const mainContent = effectiveSidebarTab === "settings" ? (
    <AppSettingsPage />
  ) : effectiveSidebarTab === "workspace" ? (
    <CloudWorkspaceSettings
      project={currentProject}
      currentUser={currentUser}
      teams={teams}
      onRefreshProjects={loadData}
    />
  ) : currentSessionId ? (
    <ChatWindow
      messages={messages} isStreaming={isStreaming}
      artifacts={artifacts}
      hydrating={sessionHydrating}
      streamingError={streamingError}
      currentAgent={currentAgent} currentSessionId={currentSessionId}
      currentUser={currentUser}
      sessions={sessions}
      agents={agents} mode={currentMode}
      routeAgents={routeAgents} orchestratorIntent={orchestratorIntent}
      planSummary={planSummary}
      mentionableAgents={currentMode === "group" ? sessionMembers : agents}
      mentionLoading={currentMode === "group" ? sessionMembersLoading : false}
      groupMembers={sessionMembers}
      groupMembersLoading={sessionMembersLoading}
      collabTasks={collabTasks}
      dagPhases={dagPhases}
      chainSteps={chainSteps}
      collabCompleted={collabCompleted}
      collabSummary={collabSummary}
      draftPlan={draftPlan}
      onSend={handleSend}
      onDismissError={() => setStreamingError(null, currentSessionId)}
      onReply={setReplyTarget}
      onRegenerate={handleRegenerate}
      onTogglePin={handleTogglePin}
      onArtifactsChanged={handleArtifactsChanged}
      onToggleProjectFiles={toggleProjectFiles}
      projectFilesOpen={fileWorkspaceOpen}
      onRenameSession={(sessionId, title) => runCrudAction(
        () => handleRenameSession(sessionId, title),
        "群聊已重命名",
        "重命名群聊失败",
      )}
      onAddGroupMember={(sessionId, agentId) => runCrudAction(
        () => handleAddGroupMember(sessionId, agentId),
        "成员已加入群聊",
        "添加成员失败",
      )}
      onRemoveGroupMember={(sessionId, agentId) => runCrudAction(
        () => handleRemoveGroupMember(sessionId, agentId),
        "成员已移出群聊",
        "移除成员失败",
      )}
      onOpenAgentSettings={(agentId) => setAgentModal({ mode: "edit", agentId })}
    />
  ) : (
    <div className="agenthub-chat flex min-h-0 min-w-0 flex-1 items-center justify-center px-6 text-center text-lg">
      <span className="agenthub-muted">
        {currentProject ? "在当前项目中新建私聊或群聊" : "创建项目后开始"}
      </span>
    </div>
  );

  if (appRoute === "#/dev/orchestrator") {
    return (
      <>
        <DeveloperToolsPage agents={agents} onAgentsChanged={loadData} />
        <ToastViewport />
      </>
    );
  }

  const desktopSurface = capabilities.surface === "desktop";

  if (agentModal?.mode === "edit") {
    return (
      <div className={desktopSurface ? "agenthub-desktop-root agenthub-agent-settings-shell" : "contents"}>
        {desktopSurface && <DesktopTitleBar />}
        <div className={`agenthub-shell min-w-0 w-full max-w-full overflow-hidden ${desktopSurface ? "agenthub-workbench-shell-desktop" : "h-[100dvh]"}`}>
          <AgentPanel
            mode="edit"
            agentId={agentModal.agentId ?? null}
            runtimeScope={capabilities.features.localCliRuntime ? "local" : "cloud"}
            onChanged={loadData}
            onClose={() => setAgentModal(null)}
          />
          <ToastViewport />
        </div>
      </div>
    );
  }

  return (
    <div className={desktopSurface ? "agenthub-desktop-root" : "contents"}>
      {desktopSurface && <DesktopTitleBar />}
      <div className={`agenthub-shell agenthub-workbench-shell flex min-w-0 w-full max-w-full overflow-hidden ${desktopSurface ? "agenthub-workbench-shell-desktop" : "h-[100dvh]"}`}>
      <aside className={`agenthub-activity-zone ${activityPanel ? "agenthub-activity-zone-open" : "agenthub-activity-zone-closed"}`}>
        <ActivityRail
          activePanel={activityPanel}
          currentProject={currentProject}
          teams={teams}
          currentTeamId={currentTeamId}
          onSelectTeam={setCurrentTeamId}
          onCreateTeam={handleCreateTeam}
          onJoinTeam={handleJoinTeam}
          onOpenSettings={() => {
            setSidebarTab("settings");
            setActivityPanel(null);
          }}
          onTogglePanel={toggleActivityPanel}
          onOpenProjectFiles={toggleProjectFiles}
          projectFilesDisabled={!currentProjectId}
          showCloudNavigation={edition !== "local"}
        />

        <div className={`agenthub-activity-panel min-h-0 shrink-0 transition-all duration-200 ${
          activityPanel ? "agenthub-activity-panel-open" : "agenthub-activity-panel-closed"
        } ${resizingActivityPanel ? "agenthub-activity-panel-resizing" : ""}`} style={activityPanel ? { width: activityPanelWidth } : undefined}>
          {activityPanel && (
            <ActivityPanelContent
              panel={activityPanel}
              project={currentProject}
              projects={projects}
              currentProjectId={currentProjectId}
              currentTeamId={currentTeamId}
              sessions={sessions}
              currentSessionId={currentSessionId}
              sessionsLoading={sessionsLoading}
              projectsLoading={initialLoading}
              creatingProject={creatingProject}
              agents={agents}
              canCreateLocalProject={edition !== "saas"}
              canCreateCloudProject={edition !== "local"}
              onSelectSession={handleSelectSession}
              onNewSession={(agentId) => runCrudAction(
                async () => {
                  await handleNewSession(agentId);
                  setSidebarTab("sessions");
                  setActivityPanel("sessions");
                },
                "私聊已创建",
                "创建私聊失败",
              )}
              onNewGroupSession={() => setShowGroupCreator(true)}
              onDeleteSession={(sessionId) => runCrudAction(
                () => handleDeleteSession(sessionId),
                "对话已删除",
                "删除对话失败",
              )}
              onRenameSession={(sessionId, title) => runCrudAction(
                () => handleRenameSession(sessionId, title),
                "对话已重命名",
                "重命名对话失败",
              )}
              onPinSession={(sessionId, pinned) => runCrudAction(
                () => handlePinSession(sessionId, pinned),
                pinned ? "对话已置顶" : "已取消置顶",
                "更新置顶失败",
              )}
              onArchiveSession={(sessionId, archived) => runCrudAction(
                () => handleArchiveSession(sessionId, archived),
                archived === false ? "对话已恢复" : "对话已归档",
                "更新归档失败",
              )}
              onMuteSession={(sessionId, muted) => runCrudAction(
                () => handleMuteSession(sessionId, muted),
                muted ? "已开启免打扰" : "已关闭免打扰",
                "更新免打扰失败",
              )}
              onSelectProject={handleSelectProject}
              onSelectProjectSession={handleSelectProjectSession}
              onCreateBlankProject={() => runCrudAction(
                () => handleCreateBlankProject(),
                "项目已创建",
                "创建项目失败",
              )}
              onCreateCloudProject={() => runCrudAction(
                () => handleCreateCloudProject("云端项目"),
                "云端项目已创建",
                "创建云端项目失败",
              )}
              onPickExistingFolder={() => runCrudAction(
                handlePickExistingFolder,
                "项目已绑定",
                "选择文件夹失败",
              )}
              onArchiveProject={(projectId) => runCrudAction(
                () => handleArchiveProject(projectId),
                "项目已归档",
                "归档项目失败",
              )}
              onRenameProject={(projectId, name) => runCrudAction(
                () => handleRenameProject(projectId, name),
                "项目已重命名",
                "重命名项目失败",
              )}
              onDeleteProject={(projectId, deleteFiles) => runCrudAction(
                () => handleDeleteProject(projectId, deleteFiles),
                "项目已删除",
                "删除项目失败",
              )}
              onNewProjectSession={(projectId, agentId) => runCrudAction(
                () => handleNewProjectSession(projectId, agentId),
                "私聊已创建",
                "创建私聊失败",
              )}
              onStartAgentChat={(agentId) => runCrudAction(
                async () => {
                  await handleNewSession(agentId);
                  setSidebarTab("sessions");
                  setActivityPanel("sessions");
                },
                "私聊已创建",
                "创建私聊失败",
              )}
              onCreateAgent={() => setAgentModal({ mode: "create" })}
              onEditAgent={(agentId) => setAgentModal({ mode: "edit", agentId })}
              onDeleteAgent={(agentId) => runCrudAction(async () => {
                await deleteAgent(agentId);
                await loadData();
              }, "Agent 已删除", "删除 Agent 失败")}
            />
          )}
        </div>
        {activityPanel && (
          <div
            className="agenthub-activity-resizer"
            role="separator"
            aria-label="调整侧边面板宽度"
            aria-orientation="vertical"
            aria-valuemin={ACTIVITY_PANEL_MIN_WIDTH}
            aria-valuemax={ACTIVITY_PANEL_MAX_WIDTH}
            aria-valuenow={activityPanelWidth}
            tabIndex={0}
            onPointerDown={beginActivityPanelResize}
            onKeyDown={resizeActivityPanelWithKeyboard}
          />
        )}
      </aside>

      <main className="agenthub-main-workspace min-h-0 min-w-0 flex-1 overflow-hidden">
        <div className={`agenthub-workspace-frame ${fileWorkspaceOpen ? "agenthub-workspace-frame-split" : ""}`}>
          <div className="agenthub-workspace-primary min-h-0 min-w-0 flex-1">
            {mainContent}
          </div>
          <ProjectFileWorkspaceModal
            open={fileWorkspaceOpen}
            project={currentProject}
            initialPath={fileWorkspaceInitialPath}
            onClose={() => {
              setFileWorkspaceOpen(false);
              setFileWorkspaceInitialPath(null);
            }}
            onChanged={handleArtifactsChanged}
          />
        </div>
      </main>

      {showGroupCreator && (
        <GroupChatCreator
          agents={agents}
          onConfirm={(title, selectedIds) => {
            setShowGroupCreator(false);
            void runCrudAction(
              () => handleCreateGroup(title, selectedIds),
              "群聊已创建",
              "创建群聊失败",
            );
          }}
          onCancel={() => setShowGroupCreator(false)}
        />
      )}

      {agentModal?.mode === "create" && (
        <AgentPanel
          mode="create"
          runtimeScope={capabilities.features.localCliRuntime ? "local" : "cloud"}
          onChanged={loadData}
          onClose={() => setAgentModal(null)}
        />
      )}

      <ToastViewport />
      </div>
    </div>
  );
}

export default AgentHubWorkbench;

function ActivityRail({
  activePanel,
  currentProject,
  teams,
  currentTeamId,
  onSelectTeam,
  onCreateTeam,
  onJoinTeam,
  onOpenSettings,
  onTogglePanel,
  onOpenProjectFiles,
  projectFilesDisabled,
  showCloudNavigation,
}: {
  activePanel: ActivityPanel | null;
  currentProject: Project | null;
  teams: Team[];
  currentTeamId: string | null;
  onSelectTeam: (teamId: string | null) => void;
  onCreateTeam: (name: string) => Promise<void> | void;
  onJoinTeam: (code: string) => Promise<void> | void;
  onOpenSettings: () => void;
  onTogglePanel: (panel: ActivityPanel) => void;
  onOpenProjectFiles: () => void;
  projectFilesDisabled: boolean;
  showCloudNavigation: boolean;
}) {
  const [menuOpen, setMenuOpen] = useState<RailFloatingMenu | null>(null);
  const workspaceButtonRef = useRef<HTMLButtonElement | null>(null);
  const teamButtonRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const theme = useThemeStore((state) => state.theme);
  const themePreference = useThemeStore((state) => state.preference);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (menuRef.current?.contains(target)) return;
      const anchors = [workspaceButtonRef.current, teamButtonRef.current];
      if (anchors.some((anchor) => anchor?.contains(target))) return;
      setMenuOpen(null);
    };
    window.addEventListener("pointerdown", close, true);
    return () => window.removeEventListener("pointerdown", close, true);
  }, [menuOpen]);

  const currentMenuAnchor = menuOpen === "workspace" ? workspaceButtonRef : teamButtonRef;

  return (
    <nav className="agenthub-activity-rail flex shrink-0 flex-col items-center" aria-label="主导航">
      <div className="agenthub-rail-logo-wrap">
        <BrandLogo size="rail" className="agenthub-product-logo" />
      </div>

      <div className="agenthub-rail-main">
        <ActivityRailButton
          icon={MessageCircle}
          label="对话"
          active={activePanel === "sessions"}
          onClick={() => onTogglePanel("sessions")}
        />
        <ActivityRailButton
          icon={Users}
          label="好友"
          active={activePanel === "agents"}
          onClick={() => onTogglePanel("agents")}
        />
        <ActivityRailButton
          icon={FolderOpen}
          label="项目"
          active={activePanel === "projects"}
          onClick={() => onTogglePanel("projects")}
        />
        <ActivityRailButton
          icon={PanelLeftClose}
          label={currentProject ? `资源管理器：${currentProject.name}` : "资源管理器"}
          disabled={projectFilesDisabled}
          onClick={onOpenProjectFiles}
        />
      </div>

      <div className="agenthub-rail-bottom">
        {showCloudNavigation && (
          <>
            <ActivityRailButton
              ref={workspaceButtonRef}
              icon={HardDrive}
              label="工作空间"
              active={menuOpen === "workspace"}
              onClick={() => setMenuOpen((value) => value === "workspace" ? null : "workspace")}
            />
            <ActivityRailButton
              ref={teamButtonRef}
              icon={Building2}
              label="团队"
              active={menuOpen === "teams"}
              onClick={() => setMenuOpen((value) => value === "teams" ? null : "teams")}
            />
          </>
        )}
        <ActivityRailButton
          icon={themePreference === "system" ? Monitor : theme === "dark" ? Moon : Sun}
          label={themePreference === "system" ? `跟随系统（当前${theme === "dark" ? "暗黑" : "明亮"}）` : theme === "dark" ? "切换明亮主题" : "切换跟随系统"}
          onClick={() => {
            setMenuOpen(null);
            toggleTheme();
          }}
        />
        <ActivityRailButton icon={Settings} label="设置" onClick={() => { setMenuOpen(null); onOpenSettings(); }} />
      </div>

      <FloatingMenu
        open={Boolean(menuOpen)}
        anchorRef={currentMenuAnchor}
        menuRef={menuRef}
        width={256}
        placement="top-start"
        ariaLabel="活动栏菜单"
      >
        {showCloudNavigation && menuOpen === "workspace" && (
          <WorkspaceFloatingMenu
            currentProject={currentProject}
            teams={teams}
            currentTeamId={currentTeamId}
            onSelectTeam={(teamId) => {
              onSelectTeam(teamId);
              setMenuOpen(null);
            }}
          />
        )}
        {showCloudNavigation && menuOpen === "teams" && (
          <TeamFloatingMenu
            teams={teams}
            currentTeamId={currentTeamId}
            onSelectTeam={(teamId) => {
              onSelectTeam(teamId);
              setMenuOpen(null);
            }}
            onCreateTeam={onCreateTeam}
            onJoinTeam={onJoinTeam}
          />
        )}
      </FloatingMenu>
    </nav>
  );
}

const ActivityRailButton = forwardRef<HTMLButtonElement, {
  icon: LucideIcon;
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}>(function ActivityRailButton({
  icon: Icon,
  label,
  active = false,
  disabled = false,
  onClick,
}, ref) {
  return (
    <button
      ref={ref}
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`agenthub-activity-button agenthub-focus-ring ${active ? "agenthub-activity-active" : ""}`}
      aria-label={label}
      title={label}
      data-active={active}
    >
      <Icon size={18} strokeWidth={active ? 2.35 : 1.85} aria-hidden="true" />
    </button>
  );
});

function WorkspaceFloatingMenu({
  currentProject,
  teams,
  currentTeamId,
  onSelectTeam,
}: {
  currentProject: Project | null;
  teams: Team[];
  currentTeamId: string | null;
  onSelectTeam: (teamId: string | null) => void;
}) {
  return (
    <div className="agenthub-rail-menu">
      <div className="agenthub-rail-menu-profile">
        <span className="agenthub-rail-menu-mark">
          <HardDrive size={16} aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="agenthub-strong block truncate text-sm font-semibold">
            {currentProject?.name ?? "未选择项目"}
          </span>
          <span className="agenthub-muted block truncate text-xs">
            {currentProject ? currentProject.workspaceMode === "cloud" ? "云端工作区" : currentProject.workspacePath ?? "本机工作区" : "选择空间后载入项目"}
          </span>
        </span>
      </div>
      <div className="agenthub-floating-section-title">空间</div>
      <button type="button" onClick={() => onSelectTeam(null)} className="agenthub-floating-row">
        <UserRound size={14} aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate">个人空间</span>
        {!currentTeamId && <Check size={14} aria-hidden="true" />}
      </button>
      {teams.map((team) => (
        <button
          key={team.id}
          type="button"
          onClick={() => onSelectTeam(team.id)}
          className="agenthub-floating-row"
        >
          <Users size={14} aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate">{team.name}</span>
          {currentTeamId === team.id && <Check size={14} aria-hidden="true" />}
        </button>
      ))}
      {teams.length === 0 && (
        <div className="agenthub-rail-menu-empty">当前只有个人空间</div>
      )}
    </div>
  );
}

const TEAM_ROLE_LABELS: Record<Team["role"], string> = {
  owner: "所有者",
  admin: "管理员",
  member: "成员",
  viewer: "访客",
};

function TeamFloatingMenu({
  teams,
  currentTeamId,
  onSelectTeam,
  onCreateTeam,
  onJoinTeam,
}: {
  teams: Team[];
  currentTeamId: string | null;
  onSelectTeam: (teamId: string | null) => void;
  onCreateTeam: (name: string) => Promise<void> | void;
  onJoinTeam: (code: string) => Promise<void> | void;
}) {
  const [teamName, setTeamName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [expandedTeamId, setExpandedTeamId] = useState<string | null>(currentTeamId);
  const [membersByTeam, setMembersByTeam] = useState<Record<string, TeamMember[]>>({});
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<TeamRole>("member");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pushToast = useToastStore((state) => state.pushToast);

  const runAction = async (action: string, task: () => Promise<void>) => {
    if (busyAction) return;
    setBusyAction(action);
    setError(null);
    try {
      await task();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败，请稍后重试");
    } finally {
      setBusyAction(null);
    }
  };

  const submitCreate = () => {
    const name = teamName.trim();
    if (!name) return;
    void runAction("create", async () => {
      await onCreateTeam(name);
      setTeamName("");
      pushToast({ kind: "success", title: "团队已创建" });
    });
  };

  const submitJoin = () => {
    const code = joinCode.trim();
    if (!code) return;
    void runAction("join", async () => {
      await onJoinTeam(code);
      setJoinCode("");
      pushToast({ kind: "success", title: "已加入团队" });
    });
  };

  const copyJoinCode = (team: Team) => {
    void runAction(`copy-${team.id}`, async () => {
      const result = await fetchTeamJoinCode(team.id);
      if (!navigator.clipboard?.writeText) {
        throw new Error("当前浏览器不支持自动复制");
      }
      await navigator.clipboard.writeText(result.code);
      pushToast({ kind: "success", title: "邀请码已复制", description: team.name });
    });
  };

  const loadMembers = (teamId: string) => {
    void runAction(`members-${teamId}`, async () => {
      const members = await fetchTeamMembers(teamId);
      setMembersByTeam((value) => ({ ...value, [teamId]: members }));
    });
  };

  const toggleTeamManagement = (teamId: string) => {
    setExpandedTeamId((value) => value === teamId ? null : teamId);
    if (!membersByTeam[teamId]) loadMembers(teamId);
  };

  const submitAddMember = (teamId: string) => {
    const email = memberEmail.trim();
    if (!email) return;
    void runAction(`add-member-${teamId}`, async () => {
      await addTeamMember(teamId, email, memberRole);
      setMemberEmail("");
      const members = await fetchTeamMembers(teamId);
      setMembersByTeam((value) => ({ ...value, [teamId]: members }));
      pushToast({ kind: "success", title: "成员已加入" });
    });
  };

  const changeMemberRole = (teamId: string, member: TeamMember, role: TeamRole) => {
    void runAction(`role-${member.id}`, async () => {
      const updated = await updateTeamMemberRole(teamId, member.id, role);
      setMembersByTeam((value) => ({
        ...value,
        [teamId]: (value[teamId] ?? []).map((item) => item.id === member.id ? updated : item),
      }));
    });
  };

  const removeMember = (teamId: string, member: TeamMember) => {
    void runAction(`remove-${member.id}`, async () => {
      await removeTeamMember(teamId, member.id);
      setMembersByTeam((value) => ({
        ...value,
        [teamId]: (value[teamId] ?? []).filter((item) => item.id !== member.id),
      }));
      pushToast({ kind: "success", title: "成员已移除" });
    });
  };

  return (
    <div className="agenthub-rail-menu agenthub-team-menu">
      <div className="agenthub-rail-menu-profile">
        <span className="agenthub-rail-menu-mark">
          <Users size={16} aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="agenthub-strong block truncate text-sm font-semibold">团队</span>
          <span className="agenthub-muted block truncate text-xs">{teams.length} 个团队空间</span>
        </span>
      </div>

      <div className="agenthub-floating-section-title">当前空间</div>
      <button type="button" onClick={() => onSelectTeam(null)} className="agenthub-floating-row">
        <UserRound size={14} aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate">个人空间</span>
        {!currentTeamId && <Check size={14} aria-hidden="true" />}
      </button>
      {teams.map((team) => (
        <button
          key={team.id}
          type="button"
          onClick={() => onSelectTeam(team.id)}
          className="agenthub-floating-row"
        >
          <Users size={14} aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate">{team.name}</span>
          {currentTeamId === team.id && <Check size={14} aria-hidden="true" />}
        </button>
      ))}

      <div className="agenthub-floating-section-title">加入团队</div>
      <div className="agenthub-floating-form">
        <input
          value={joinCode}
          onChange={(event) => setJoinCode(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") submitJoin();
          }}
          className="agenthub-inline-input"
          placeholder="输入邀请码"
        />
        <button
          type="button"
          onClick={submitJoin}
          disabled={!joinCode.trim() || Boolean(busyAction)}
          className="agenthub-floating-action-button"
        >
          加入
        </button>
      </div>

      <div className="agenthub-floating-section-title">创建团队</div>
      <div className="agenthub-floating-form">
        <input
          value={teamName}
          onChange={(event) => setTeamName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") submitCreate();
          }}
          className="agenthub-inline-input"
          placeholder="团队名称"
        />
        <button
          type="button"
          onClick={submitCreate}
          disabled={!teamName.trim() || Boolean(busyAction)}
          className="agenthub-floating-action-button"
        >
          <Plus size={13} aria-hidden="true" />
          创建
        </button>
      </div>

      <div className="agenthub-floating-section-title">团队管理</div>
      {teams.length === 0 ? (
        <div className="agenthub-rail-menu-empty">创建或加入团队后会显示管理入口</div>
      ) : (
        <div className="agenthub-team-card-list">
          {teams.map((team) => {
            const canManage = team.role === "owner" || team.role === "admin";
            const actionBusy = busyAction === `copy-${team.id}`;
            return (
              <div key={team.id} className="agenthub-team-card">
                <div className="min-w-0">
                  <div className="agenthub-strong truncate text-sm font-semibold">{team.name}</div>
                  <div className="agenthub-muted mt-1 text-xs">
                    {TEAM_ROLE_LABELS[team.role]} · {team.memberCount} 人
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => copyJoinCode(team)}
                  disabled={!canManage || Boolean(busyAction)}
                  className="agenthub-team-code-button"
                  title={canManage ? "复制团队邀请码" : "需要管理员权限"}
                >
                  <Copy size={13} aria-hidden="true" />
                  {actionBusy ? "复制中" : "邀请码"}
                </button>
                <button
                  type="button"
                  onClick={() => toggleTeamManagement(team.id)}
                  className="agenthub-team-code-button"
                  title="成员管理"
                >
                  <Users size={13} aria-hidden="true" />
                  管理
                </button>
                {expandedTeamId === team.id && (
                  <div className="agenthub-team-member-panel">
                    <div className="agenthub-team-member-form">
                      <input
                        value={memberEmail}
                        onChange={(event) => setMemberEmail(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") submitAddMember(team.id);
                        }}
                        disabled={!canManage || Boolean(busyAction)}
                        className="agenthub-inline-input"
                        placeholder="成员邮箱"
                      />
                      <select
                        value={memberRole}
                        onChange={(event) => setMemberRole(event.target.value as TeamRole)}
                        disabled={!canManage || Boolean(busyAction)}
                        className="agenthub-team-role-select"
                      >
                        <option value="admin">管理员</option>
                        <option value="member">成员</option>
                        <option value="viewer">访客</option>
                      </select>
                      <button
                        type="button"
                        onClick={() => submitAddMember(team.id)}
                        disabled={!canManage || !memberEmail.trim() || Boolean(busyAction)}
                        className="agenthub-floating-action-button"
                      >
                        添加
                      </button>
                    </div>
                    {(membersByTeam[team.id] ?? []).length === 0 ? (
                      <div className="agenthub-rail-menu-empty">
                        {busyAction === `members-${team.id}` ? "正在加载成员" : "暂无成员数据"}
                      </div>
                    ) : (
                      <div className="agenthub-team-member-list">
                        {(membersByTeam[team.id] ?? []).map((member) => (
                          <div key={member.id} className="agenthub-team-member-row">
                            <span className="min-w-0 flex-1">
                              <span className="agenthub-strong block truncate text-xs font-semibold">{member.displayName || member.email}</span>
                              <span className="agenthub-muted block truncate text-[11px]">{member.email}</span>
                            </span>
                            <select
                              value={member.role}
                              onChange={(event) => changeMemberRole(team.id, member, event.target.value as TeamRole)}
                              disabled={!canManage || member.role === "owner" || Boolean(busyAction)}
                              className="agenthub-team-role-select"
                            >
                              <option value="owner">所有者</option>
                              <option value="admin">管理员</option>
                              <option value="member">成员</option>
                              <option value="viewer">访客</option>
                            </select>
                            <button
                              type="button"
                              onClick={() => removeMember(team.id, member)}
                              disabled={!canManage || member.role === "owner" || Boolean(busyAction)}
                              className="agenthub-team-member-danger"
                              aria-label={`移除 ${member.displayName || member.email}`}
                              title="移除成员"
                            >
                              <Trash2 size={13} aria-hidden="true" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {error && <div className="agenthub-floating-error">{error}</div>}
    </div>
  );
}

function DeveloperToolsPage({
  agents,
  onAgentsChanged,
}: {
  agents: AgentConfig[];
  onAgentsChanged: () => Promise<void>;
}) {
  return (
    <div className="agenthub-shell h-[100dvh] overflow-hidden">
      <div className="agenthub-header flex items-center justify-between border-b px-4 py-3">
        <div>
          <p className="agenthub-faint text-xs">开发者页面</p>
          <h1 className="agenthub-strong text-base font-semibold">调度器手动桥接</h1>
        </div>
        <a href="#/" className="agenthub-icon-button rounded-full px-4 py-2 text-sm">
          返回对话
        </a>
      </div>
      <div className="min-h-0 h-[calc(100dvh-65px)]">
        <OrchestratorDebugPanel agents={agents} onAgentsChanged={onAgentsChanged} />
      </div>
    </div>
  );
}
