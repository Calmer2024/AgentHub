import { useCallback, useState } from "react";
import { useChatStore, type CollabSnapshot } from "./stores/chatStore";
import { SessionList } from "./components/SessionList";
import { MemoChatWindow as ChatWindow } from "./components/ChatWindow";
import { ProjectSidebar } from "./components/ProjectSidebar";
import { AgentPanel } from "./components/AgentPanel";
import { GroupChatCreator } from "./components/GroupChatCreator";
import { deleteAgent, fetchArtifacts, fetchMessages, pinMessage, regenerateMessageStream, unpinMessage } from "./api/client";
import { useSendMessage } from "./hooks/useSendMessage";
import { useWorkspaceRuntime } from "./hooks/useWorkspaceRuntime";
import type { Message } from "./types";

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
  };
}

const EMPTY_COLLAB = emptyCollab();

function App() {
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
    creatingProject, sessionsLoading, sessionHydrating, sessionMembers, currentAgent, currentMode,
    setSidebarTab, loadData,
    handleSelectProject, handleArchiveProject,
    handleRenameProject, handleDeleteProject,
    handleCreateBlankProject, handlePickExistingFolder,
    handleSelectSession, handleNewSession, handleCreateGroup,
    handleDeleteSession, handleRenameSession,
  } = useWorkspaceRuntime();

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

  const [showGroupCreator, setShowGroupCreator] = useState(false);
  const [agentModal, setAgentModal] = useState<{ mode: "create" | "edit"; agentId?: string } | null>(null);
  const handleSend = useSendMessage();

  const handleTogglePin = useCallback(async (message: Message) => {
    try {
      if (message.isPinned) {
        await unpinMessage(message.id);
        updateMessage(message.id, { isPinned: false });
      } else {
        await pinMessage(message.id);
        updateMessage(message.id, { isPinned: true });
      }
    } catch {
      setStreamingError("Pin 操作失败，请稍后重试", message.sessionId || currentSessionId);
    }
  }, [currentSessionId, setStreamingError, updateMessage]);

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

  return (
    <div className="agenthub-shell h-[100dvh] w-screen flex flex-col md:flex-row overflow-hidden">
      <div className="agenthub-left-cluster flex w-full shrink-0 flex-col md:h-full md:w-[584px] md:flex-row">
        <ProjectSidebar
          projects={projects}
          currentProjectId={currentProjectId}
          agents={agents}
          activePanel={sidebarTab}
          creating={creatingProject}
          onSelectProject={handleSelectProject}
          onCreateBlankProject={handleCreateBlankProject}
          onPickExistingFolder={handlePickExistingFolder}
          onArchiveProject={handleArchiveProject}
          onRenameProject={handleRenameProject}
          onDeleteProject={handleDeleteProject}
          onOpenPanel={setSidebarTab}
          onStartAgentChat={handleNewSession}
          onCreateAgent={() => setAgentModal({ mode: "create" })}
          onEditAgent={(agentId) => setAgentModal({ mode: "edit", agentId })}
          onDeleteAgent={async (agentId) => {
            await deleteAgent(agentId);
            await loadData();
          }}
        />

        <div className="agenthub-session-nest flex h-[32dvh] w-full flex-col shrink-0 transition-colors duration-300 md:h-full md:w-[300px]">
          <SessionList
            project={currentProject}
            sessions={sessions} currentSessionId={currentSessionId}
            loading={sessionsLoading}
            agents={agents} onSelectSession={handleSelectSession}
            onNewSession={handleNewSession}
            onNewGroupSession={() => setShowGroupCreator(true)}
            onDeleteSession={handleDeleteSession}
            onRenameSession={handleRenameSession}
          />
        </div>
      </div>

      {currentSessionId ? (
        <ChatWindow
          messages={messages} isStreaming={isStreaming}
          artifacts={artifacts}
          hydrating={sessionHydrating}
          streamingError={streamingError}
          currentAgent={currentAgent} currentSessionId={currentSessionId}
          agents={agents} mode={currentMode}
          routeAgents={routeAgents} orchestratorIntent={orchestratorIntent}
          planSummary={planSummary}
          mentionableAgents={currentMode === "group" ? sessionMembers : agents}
          collabTasks={collabTasks}
          dagPhases={dagPhases}
          chainSteps={chainSteps}
          collabCompleted={collabCompleted}
          collabSummary={collabSummary}
          onSend={handleSend}
          onDismissError={() => setStreamingError(null, currentSessionId)}
          onReply={setReplyTarget}
          onRegenerate={handleRegenerate}
          onTogglePin={handleTogglePin}
          onArtifactsChanged={handleArtifactsChanged}
        />
      ) : (
        <div className="agenthub-chat flex-1 min-h-0 flex items-center justify-center text-lg px-6 text-center">
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
            handleCreateGroup(title, selectedIds);
          }}
          onCancel={() => setShowGroupCreator(false)}
        />
      )}

      <AgentPanel
        mode={agentModal?.mode ?? "hidden"}
        agentId={agentModal?.agentId ?? null}
        onChanged={loadData}
        onClose={() => setAgentModal(null)}
      />
    </div>
  );
}

export default App;
