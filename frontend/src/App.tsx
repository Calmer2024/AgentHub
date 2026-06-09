import { useCallback, useEffect, useState } from "react";
import { useChatStore, type CollabSnapshot } from "./stores/chatStore";
import { SessionList } from "./components/SessionList";
import { MemoChatWindow as ChatWindow } from "./components/ChatWindow";
import { AgentPanel } from "./components/AgentPanel";
import { GroupChatCreator } from "./components/GroupChatCreator";
import { ToastViewport } from "./components/ToastViewport";
import { OrchestratorDebugPanel } from "./components/OrchestratorDebugPanel";
import { useCapabilities } from "./app/ShellProvider";
import { LocalProjectSidebar } from "./shells/local/LocalProjectSidebar";
import { SaasProjectSidebar } from "./shells/saas/SaasProjectSidebar";
import { LocalProjectSettings } from "./shells/local/LocalProjectSettings";
import { CloudWorkspaceSettings } from "./shells/saas/CloudWorkspaceSettings";
import {
  deleteAgent,
  fetchArtifacts,
  fetchMessages,
  markSessionRead,
  pinMessage,
  regenerateMessageStream,
  unpinMessage,
} from "./api/client";
import { useSendMessage } from "./hooks/useSendMessage";
import { useWorkspaceRuntime } from "./hooks/useWorkspaceRuntime";
import { useToastStore } from "./stores/toastStore";
import type { AgentConfig, Message } from "./types";

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
    handleCreateBlankProject, handleCreateCloudProject, handleCreateTeam, handlePickExistingFolder,
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
  const handleSend = useSendMessage();
  const pushToast = useToastStore((state) => state.pushToast);

  useEffect(() => {
    const syncRoute = () => setAppRoute(window.location.hash || "#/");
    window.addEventListener("hashchange", syncRoute);
    return () => window.removeEventListener("hashchange", syncRoute);
  }, []);

  const notifyError = useCallback((title: string, error: unknown) => {
    pushToast({
      kind: "error",
      title,
      description: error instanceof Error ? error.message : "请稍后重试",
    });
  }, [pushToast]);

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

  if (appRoute === "#/dev/orchestrator") {
    return (
      <>
        <DeveloperToolsPage agents={agents} onAgentsChanged={loadData} />
        <ToastViewport />
      </>
    );
  }

  return (
    <div className="agenthub-shell flex h-[100dvh] min-w-0 w-full max-w-full flex-col overflow-hidden md:flex-row">
      <div className="agenthub-left-cluster flex min-w-0 w-full shrink-0 flex-col md:h-full md:w-[584px] md:flex-row">
        {edition === "local" ? (
        <LocalProjectSidebar
          projects={projects}
          currentProjectId={currentProjectId}
          agents={agents}
          activePanel={sidebarTab}
          currentUser={currentUser}
          teams={teams}
          currentTeamId={currentTeamId}
          creating={creatingProject}
          loading={initialLoading}
          onSelectProject={handleSelectProject}
          onSelectTeam={setCurrentTeamId}
          onCreateTeam={(name) => runCrudAction(
            () => handleCreateTeam(name),
            "团队已创建",
            "创建团队失败",
          )}
          onCreateBlankProject={(name) => runCrudAction(
            () => handleCreateBlankProject(name),
            "项目已创建",
            "创建项目失败",
          )}
          onCreateCloudProject={(name, teamId) => runCrudAction(
            () => handleCreateCloudProject(name, teamId),
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
          onOpenPanel={setSidebarTab}
          onStartAgentChat={handleNewSession}
          onCreateAgent={() => setAgentModal({ mode: "create" })}
          onEditAgent={(agentId) => setAgentModal({ mode: "edit", agentId })}
          onDeleteAgent={async (agentId) => {
            await runCrudAction(async () => {
              await deleteAgent(agentId);
              await loadData();
            }, "Agent 已删除", "删除 Agent 失败");
          }}
        />
        ) : (
        <SaasProjectSidebar
          projects={projects}
          currentProjectId={currentProjectId}
          agents={agents}
          activePanel={sidebarTab}
          currentUser={currentUser}
          teams={teams}
          currentTeamId={currentTeamId}
          creating={creatingProject}
          loading={initialLoading}
          onSelectProject={handleSelectProject}
          onSelectTeam={setCurrentTeamId}
          onCreateTeam={(name) => runCrudAction(
            () => handleCreateTeam(name),
            "团队已创建",
            "创建团队失败",
          )}
          onCreateBlankProject={(name) => runCrudAction(
            () => handleCreateBlankProject(name),
            "项目已创建",
            "创建项目失败",
          )}
          onCreateCloudProject={(name, teamId) => runCrudAction(
            () => handleCreateCloudProject(name, teamId),
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
          onOpenPanel={setSidebarTab}
          onStartAgentChat={handleNewSession}
          onCreateAgent={() => setAgentModal({ mode: "create" })}
          onEditAgent={(agentId) => setAgentModal({ mode: "edit", agentId })}
          onDeleteAgent={async (agentId) => {
            await runCrudAction(async () => {
              await deleteAgent(agentId);
              await loadData();
            }, "Agent 已删除", "删除 Agent 失败");
          }}
        />
        )}

        <div className="agenthub-session-nest flex h-[32dvh] min-w-0 w-full shrink-0 flex-col transition-colors duration-300 md:h-full md:w-[300px]">
          <SessionList
            project={currentProject}
            sessions={sessions} currentSessionId={currentSessionId}
            loading={sessionsLoading}
            agents={agents} onSelectSession={handleSelectSession}
            onNewSession={(agentId) => runCrudAction(
              () => handleNewSession(agentId),
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
          />
        </div>
      </div>

      {sidebarTab === "workspace" ? (
        edition === "local" ? (
          <LocalProjectSettings
            project={currentProject}
            currentUser={currentUser}
            teams={teams}
            onRefreshProjects={loadData}
          />
        ) : (
          <CloudWorkspaceSettings
            project={currentProject}
            currentUser={currentUser}
            teams={teams}
            onRefreshProjects={loadData}
          />
        )
      ) : currentSessionId ? (
        <ChatWindow
          messages={messages} isStreaming={isStreaming}
          artifacts={artifacts}
          hydrating={sessionHydrating}
          streamingError={streamingError}
          currentAgent={currentAgent} currentSessionId={currentSessionId}
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
        />
      ) : (
        <div className="agenthub-chat flex min-h-0 min-w-0 flex-1 items-center justify-center px-6 text-center text-lg">
          <span className="agenthub-muted">
          {currentProject ? "在当前项目中新建私聊或群聊" : "创建项目后开始"}
          </span>
        </div>
      )}

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

      <AgentPanel
        mode={agentModal?.mode ?? "hidden"}
        agentId={agentModal?.agentId ?? null}
        runtimeScope={capabilities.features.localCliRuntime ? "local" : "cloud"}
        onChanged={loadData}
        onClose={() => setAgentModal(null)}
      />
      <ToastViewport />
    </div>
  );
}

export default AgentHubWorkbench;

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
