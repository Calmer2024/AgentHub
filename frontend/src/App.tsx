import { useState } from "react";
import { useChatStore, type CollabSnapshot } from "./stores/chatStore";
import { SessionList } from "./components/SessionList";
import { ChatWindow } from "./components/ChatWindow";
import { ProjectSidebar } from "./components/ProjectSidebar";
import { AgentPanel } from "./components/AgentPanel";
import { GroupChatCreator } from "./components/GroupChatCreator";
import { OrchestratorDebugPanel } from "./components/OrchestratorDebugPanel";
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
    draftPlan: null,
  };
}

function App() {
  const {
    currentSessionId, messages, isStreaming, streamingError,
    artifacts,
    setMessagesForSession,
    setArtifactsForSession,
    setStreamingError,
    setIsStreaming,
    setReplyTarget,
    updateMessage,
    replaceMessageContent,
    collabSnapshots,
  } = useChatStore();

  const {
    projects, currentProjectId, currentProject, sessions, agents, sidebarTab,
    creatingProject, sessionMembers, currentAgent, currentMode,
    setSidebarTab, loadData,
    handleSelectProject, handleArchiveProject,
    handleRenameProject, handleDeleteProject,
    handleCreateBlankProject, handlePickExistingFolder,
    handleSelectSession, handleNewSession, handleCreateGroup,
    handleDeleteSession, handleRenameSession, handleSummarizeSession,
  } = useWorkspaceRuntime();

  // --- 协作状态的读写桥接 (store ↔ 组件) ---
  const collabKey = currentSessionId ?? "__none__";
  const collab = collabSnapshots[collabKey] ?? emptyCollab();

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
  const handleSend = useSendMessage();

  const handleTogglePin = async (message: Message) => {
    try {
      if (message.isPinned) {
        await unpinMessage(message.id);
        updateMessage(message.id, { isPinned: false });
      } else {
        await pinMessage(message.id);
        updateMessage(message.id, { isPinned: true });
      }
    } catch {
      setStreamingError("Pin 操作失败，请稍后重试");
    }
  };

  const handleRegenerate = (message: Message) => {
    if (!currentSessionId) return;
    setStreamingError(null);
    setIsStreaming(true);
    replaceMessageContent(message.id, "");
    regenerateMessageStream(message.id, {
      onToken: (token) => {
        const state = useChatStore.getState();
        const current = state.messages.find((m) => m.id === message.id)?.content ?? "";
        state.replaceMessageContent(message.id, current + token);
      },
      onDone: async (_messageId, error) => {
        setIsStreaming(false);
        if (error) {
          setStreamingError(error === "重新生成超时" ? error : `重新生成失败：${error}`);
          replaceMessageContent(message.id, message.content);
          return;
        }
        try {
          setMessagesForSession(currentSessionId, await fetchMessages(currentSessionId));
        } catch { /* */ }
        try {
          setArtifactsForSession(currentSessionId, await fetchArtifacts(currentSessionId));
        } catch { /* */ }
      },
    });
  };

  const handleArtifactsChanged = async () => {
    if (!currentSessionId) return;
    try {
      setArtifactsForSession(currentSessionId, await fetchArtifacts(currentSessionId));
    } catch { /* */ }
  };

  return (
    <div className="h-[100dvh] w-screen flex flex-col md:flex-row overflow-hidden bg-[#171717] text-[#ececf1]">
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

      {sidebarTab !== "debug" && (
        <div className="w-full md:w-[300px] h-[32dvh] md:h-full bg-[#171717] border-r border-white/[0.08] flex flex-col shrink-0">
          <SessionList
            project={currentProject}
            sessions={sessions} currentSessionId={currentSessionId}
            agents={agents} onSelectSession={handleSelectSession}
            onNewSession={handleNewSession}
            onNewGroupSession={() => setShowGroupCreator(true)}
            onDeleteSession={handleDeleteSession}
            onRenameSession={handleRenameSession}
            onSummarizeSession={handleSummarizeSession}
          />
        </div>
      )}

      {sidebarTab === "debug" ? (
        <div className="flex-1 min-h-0">
          <OrchestratorDebugPanel agents={agents} onAgentsChanged={loadData} />
        </div>
      ) : currentSessionId ? (
        <ChatWindow
          messages={messages} isStreaming={isStreaming}
          artifacts={artifacts}
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
          draftPlan={draftPlan}
          onSend={handleSend}
          onDismissError={() => setStreamingError(null)}
          onReply={setReplyTarget}
          onRegenerate={handleRegenerate}
          onTogglePin={handleTogglePin}
          onArtifactsChanged={handleArtifactsChanged}
        />
      ) : (
        <div className="flex-1 min-h-0 flex items-center justify-center bg-[#171717] text-[#8f8f98] text-lg px-6 text-center">
          {currentProject ? "在当前项目中新建私聊或群聊" : "创建 Project 后开始"}
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
