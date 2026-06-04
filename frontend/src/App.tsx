import { useEffect, useCallback, useRef, useState } from "react";
import { useChatStore, type CollabSnapshot } from "./stores/chatStore";
import { useSessionStore } from "./stores/sessionStore";
import { SessionList } from "./components/SessionList";
import { ChatWindow } from "./components/ChatWindow";
import { AgentPanel } from "./components/AgentPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { GroupChatCreator } from "./components/GroupChatCreator";
import { OrchestratorDebugPanel } from "./components/OrchestratorDebugPanel";
import {
  createSession, createGroupSession, fetchSessions, fetchMessages, fetchAgents,
  fetchProviders, updateSessionAgent, deleteSession, renameSession, summarizeSession,
  fetchSessionMembers, pinMessage, unpinMessage, regenerateMessageStream,
  fetchArtifacts,
} from "./api/client";
import { WSClient } from "./api/wsClient";
import { useSendMessage } from "./hooks/useSendMessage";
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
  };
}

function App() {
  const {
    currentSessionId, messages, isStreaming, streamingError,
    artifacts,
    setCurrentSessionId, setMessages,
    setArtifacts,
    appendStreamingToken,
    setStreamingError,
    setIsStreaming,
    setReplyTarget,
    updateMessage,
    replaceMessageContent,
    collabSnapshots, clearCollab,
  } = useChatStore();

  const {
    sessions, agents, providers, sidebarTab,
    setSessions, setAgents, setProviders, setSidebarTab, updateSession,
  } = useSessionStore();

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

  const wsRef = useRef<WSClient | null>(null);
  const [showGroupCreator, setShowGroupCreator] = useState(false);
  const [sessionMembers, setSessionMembers] = useState<AgentConfig[]>([]);
  const handleSend = useSendMessage();

  useEffect(() => {
    if (!currentSessionId) return;
    const ws = new WSClient();
    wsRef.current = ws;

    ws.on("token", (data) => {
      if (data.token && typeof data.token === "string") {
        appendStreamingToken(data.token);
      }
    });
    ws.on("message.completed", () => {
      fetchMessages(currentSessionId).then(setMessages);
      fetchArtifacts(currentSessionId).then(setArtifacts).catch(() => {});
    });
    ws.on("agent.changed", (data) => {
      if (typeof data.agentConfigId === "string") {
        const sess = sessions.find((s) => s.id === currentSessionId);
        if (sess) {
          updateSession({ ...sess, agentConfigId: data.agentConfigId });
        }
      }
    });

    ws.connect(currentSessionId);

    return () => { ws.disconnect(); };
  }, [currentSessionId]);

  const loadData = useCallback(async () => {
    try { setSessions(await fetchSessions()); } catch { /* */ }
    try { setAgents(await fetchAgents()); } catch { /* */ }
    try { setProviders(await fetchProviders()); } catch { /* */ }
  }, [setSessions, setAgents, setProviders]);

  useEffect(() => { loadData(); }, [loadData]);

  // === 会话切换 (协作状态持久化) ===
  const handleSelectSession = async (id: string) => {
    setCurrentSessionId(id);
    // 协作状态不清零 —— 由 store 按 sessionId 自动恢复
    // 切换到目标会话后，collab 会自动从 collabSnapshots[id] 读取
    setMessages([]);
    setArtifacts([]);
    setStreamingError(null);
    try { setMessages(await fetchMessages(id)); } catch { /* */ }
    try { setArtifacts(await fetchArtifacts(id)); } catch { /* */ }
    // 加载群成员
    const sess = sessions.find((s) => s.id === id);
    if (sess?.mode === "group") {
      try {
        const members = await fetchSessionMembers(id);
        setSessionMembers(members.map((m: { agentConfigId: string; agentName: string }) => ({
          id: m.agentConfigId, name: m.agentName,
        } as AgentConfig)));
      } catch { setSessionMembers([]); }
    } else {
      setSessionMembers([]);
    }
  };

  const handleNewSession = async () => {
    const s = await createSession();
    setSessions([s, ...sessions]);
    setCurrentSessionId(s.id);
    setMessages([]);
    setArtifacts([]);
    setStreamingError(null);
  };

  const handleCreateGroup = async (title: string, selectedIds: string[]) => {
    setShowGroupCreator(false);
    const s = await createGroupSession(title || "群聊", selectedIds);
    setSessions([s, ...sessions]);
    setCurrentSessionId(s.id);
    setMessages([]);
    setArtifacts([]);
    setStreamingError(null);
    clearCollab(s.id); // 新会话无协作历史
  };

  const handleDeleteSession = async (id: string) => {
    await deleteSession(id);
    setSessions(sessions.filter((s) => s.id !== id));
    if (currentSessionId === id) {
      setCurrentSessionId(null);
      setMessages([]);
      setArtifacts([]);
    }
    clearCollab(id);
  };

  const handleRenameSession = async (id: string, title: string) => {
    const updated = await renameSession(id, title);
    updateSession(updated);
  };

  const handleSummarizeSession = async (id: string) => {
    const updated = await summarizeSession(id);
    updateSession(updated);
  };

  const handleSwitchAgent = async (agentId: string) => {
    if (!currentSessionId) return;
    try { updateSession(await updateSessionAgent(currentSessionId, agentId)); } catch { /* */ }
  };

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
        try { setMessages(await fetchMessages(currentSessionId)); } catch { /* */ }
        try { setArtifacts(await fetchArtifacts(currentSessionId)); } catch { /* */ }
      },
    });
  };

  const handleArtifactsChanged = async () => {
    if (!currentSessionId) return;
    try { setArtifacts(await fetchArtifacts(currentSessionId)); } catch { /* */ }
  };

  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const currentAgent = agents.find((a) => a.id === currentSession?.agentConfigId) ?? null;
  const currentMode = currentSession?.mode ?? "single";

  const tabs = [
    { key: "sessions" as const, label: "会话" },
    { key: "agents" as const, label: "Agent" },
    { key: "debug" as const, label: "调试" },
    { key: "settings" as const, label: "设置" },
  ];

  return (
    <div className="h-[100dvh] w-screen flex flex-col md:flex-row overflow-hidden">
      <div className="w-full md:w-72 h-[42dvh] md:h-full bg-gray-50 border-r border-gray-200 flex flex-col shrink-0">
        <div className="flex border-b border-gray-200">
          {tabs.map((t) => (
            <button key={t.key} onClick={() => setSidebarTab(t.key)}
              className={`flex-1 py-3 text-sm font-medium transition-colors ${
                sidebarTab === t.key ? "text-blue-600 border-b-2 border-blue-600 bg-white" : "text-gray-500 hover:text-gray-700"
              }`}
            >{t.label}</button>
          ))}
        </div>

        {sidebarTab === "sessions" && (
          <SessionList
            sessions={sessions} currentSessionId={currentSessionId}
            agents={agents} onSelectSession={handleSelectSession}
            onNewSession={handleNewSession}
            onNewGroupSession={() => setShowGroupCreator(true)}
            onDeleteSession={handleDeleteSession}
            onRenameSession={handleRenameSession}
            onSummarizeSession={handleSummarizeSession}
          />
        )}
        {sidebarTab === "agents" && (
          <div className="flex-1 overflow-y-auto">
            <AgentPanel providers={providers} onChanged={loadData} />
          </div>
        )}
        {sidebarTab === "debug" && (
          <div className="flex-1 overflow-y-auto bg-gray-50 p-3">
            <div className="space-y-3">
              <button
                type="button"
                className="w-full border border-blue-200 bg-white px-3 py-3 text-left shadow-sm"
              >
                <span className="block text-sm font-semibold text-blue-700">调度器调试台</span>
                <span className="mt-1 block text-xs leading-5 text-gray-500">
                  输入需求，查看意图、选人、执行计划和调度图。
                </span>
              </button>
              <div className="border border-dashed border-gray-200 bg-white px-3 py-3 text-xs leading-5 text-gray-500">
                后续可以继续添加 Prompt 调试、Agent 评分调试、上下文预算调试等工具。
              </div>
            </div>
          </div>
        )}
        {sidebarTab === "settings" && (
          <div className="flex-1 overflow-y-auto">
            <SettingsPanel providers={providers} onSaved={loadData} />
          </div>
        )}
      </div>

      {sidebarTab === "debug" ? (
        <div className="flex-1 min-h-0">
          <OrchestratorDebugPanel agents={agents} />
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
          onSend={handleSend}
          onDismissError={() => setStreamingError(null)}
          onSwitchAgent={handleSwitchAgent}
          onReply={setReplyTarget}
          onRegenerate={handleRegenerate}
          onTogglePin={handleTogglePin}
          onArtifactsChanged={handleArtifactsChanged}
        />
      ) : (
        <div className="flex-1 min-h-0 flex items-center justify-center text-gray-500 text-lg px-6 text-center">
          点击左侧"新建对话"开始
        </div>
      )}

      {showGroupCreator && (
        <GroupChatCreator
          agents={agents}
          onConfirm={handleCreateGroup}
          onCancel={() => setShowGroupCreator(false)}
        />
      )}
    </div>
  );
}

export default App;
