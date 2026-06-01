import { useEffect, useCallback, useRef, useState } from "react";
import { useChatStore, type CollabSnapshot } from "./stores/chatStore";
import { useSessionStore } from "./stores/sessionStore";
import { SessionList } from "./components/SessionList";
import { ChatWindow } from "./components/ChatWindow";
import { AgentPanel } from "./components/AgentPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { GroupChatCreator } from "./components/GroupChatCreator";
import { createSession, createGroupSession, fetchSessions, fetchMessages, fetchAgents, fetchProviders, createChatStream, updateSessionAgent, deleteSession, renameSession, summarizeSession, fetchSessionMembers } from "./api/client";
import { WSClient } from "./api/wsClient";
import type { Message, AgentConfig } from "./types";

/** 从 store 读取当前会话的协作状态（零值 = 空快照）。 */
function emptyCollab(): CollabSnapshot {
  return { routeAgents: null, collabTasks: [], chainSteps: [], orchestratorIntent: null, collabCompleted: false, collabSummary: null };
}

function App() {
  const {
    currentSessionId, messages, isStreaming, streamingError,
    setCurrentSessionId, setMessages,
    appendMessage, appendStreamingToken, appendAgentStreamingToken,
    setIsStreaming, setStreamingError,
    collabSnapshots, getCollab, saveCollab, clearCollab,
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
  const chainSteps = collab.chainSteps;
  const orchestratorIntent = collab.orchestratorIntent;
  const collabCompleted = collab.collabCompleted;
  const collabSummary = collab.collabSummary;

  const wsRef = useRef<WSClient | null>(null);
  const [showGroupCreator, setShowGroupCreator] = useState(false);
  const [sessionMembers, setSessionMembers] = useState<AgentConfig[]>([]);

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
    setStreamingError(null);
    try { setMessages(await fetchMessages(id)); } catch { /* */ }
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
    setStreamingError(null);
  };

  const handleCreateGroup = async (title: string, selectedIds: string[]) => {
    setShowGroupCreator(false);
    const s = await createGroupSession(title || "群聊", selectedIds);
    setSessions([s, ...sessions]);
    setCurrentSessionId(s.id);
    setMessages([]);
    setStreamingError(null);
    clearCollab(s.id); // 新会话无协作历史
  };

  const handleDeleteSession = async (id: string) => {
    await deleteSession(id);
    setSessions(sessions.filter((s) => s.id !== id));
    if (currentSessionId === id) {
      setCurrentSessionId(null);
      setMessages([]);
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

  // === 发送消息 ===
  const handleSend = async (content: string, mentions: string[]) => {
    if (!currentSessionId) return;
    setStreamingError(null);
    // 重置当前会话的协作状态
    saveCollab(collabKey, emptyCollab());

    const currentMode = sessions.find((s) => s.id === currentSessionId)?.mode ?? "single";

    const userMsg: Message = {
      id: `local-${Date.now()}`, sessionId: currentSessionId,
      role: "user", content, agentName: null, createdAt: new Date().toISOString(),
    };
    appendMessage(userMsg);

    if (currentMode !== "group") {
      const localId = `local-ai-${Date.now()}`;
      appendMessage({
        id: localId, sessionId: currentSessionId!,
        role: "assistant", content: "", agentName: null,
        createdAt: new Date().toISOString(),
      });
    }

    const agentPlaceholders = new Map<string, string>();

    // SSE 回调中通过 saveCollab 持久化协作状态
    createChatStream(currentSessionId, content, mentions, {
      onToken: (token) => appendStreamingToken(token),
      onDone: (messageId, error) => {
        setIsStreaming(false);
        if (error) {
          setStreamingError(error === "Stream ended unexpectedly"
            ? "连接中断，请检查网络后重试" : `请求失败：${error}`);
          return;
        }
        if (messageId) fetchMessages(currentSessionId).then(setMessages);
      },
      onRoute: (agents) => {
        saveCollab(collabKey, { ...emptyCollab(), routeAgents: agents });
        setIsStreaming(true);
      },
      onTaskStarted: (tasks, intent) => {
        const snap = getCollab(collabKey);
        saveCollab(collabKey, {
          ...(snap ?? emptyCollab()),
          collabTasks: tasks,
          orchestratorIntent: intent,
        });
        tasks.forEach((t) => {
          const agent = agents.find((a) => a.name === t.agent);
          if (agent) {
            const localId = `local-agent-${agent.id}-${Date.now()}`;
            agentPlaceholders.set(agent.id, localId);
            appendMessage({
              id: localId, sessionId: currentSessionId!,
              role: "assistant", content: "", agentName: t.agent,
              createdAt: new Date().toISOString(),
            });
          }
        });
      },
      onChainStep: (step) => {
        const snap = getCollab(collabKey);
        const existing = (snap?.chainSteps ?? []).filter((s) => s.step !== step.step);
        const updatedSteps = [...existing, step].sort((a, b) => a.step - b.step);
        const updatedTasks = (snap?.collabTasks ?? []).map((t, i) => {
          if (i === step.step) {
            return {
              ...t,
              status: step.status === "interrupted" ? "error" as const
                : step.status === "completed" ? "completed" as const
                : "running" as const,
            };
          }
          return t;
        });
        saveCollab(collabKey, {
          ...(snap ?? emptyCollab()),
          chainSteps: updatedSteps,
          collabTasks: updatedTasks,
        });
      },
      onTaskCompleted: (summary) => {
        const snap = getCollab(collabKey);
        saveCollab(collabKey, {
          ...(snap ?? emptyCollab()),
          collabCompleted: true,
          collabSummary: summary,
          collabTasks: (snap?.collabTasks ?? []).map((t) => ({ ...t, status: "completed" as const })),
        });
      },
      onAgentToken: (agentId, agentName, token) => {
        const localId = agentPlaceholders.get(agentId);
        if (localId) appendAgentStreamingToken(localId, agentName, token);
      },
    });

    if (currentMode !== "group") {
      setIsStreaming(true);
    }
  };

  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const currentAgent = agents.find((a) => a.id === currentSession?.agentConfigId) ?? null;
  const currentMode = currentSession?.mode ?? "single";

  const tabs = [
    { key: "sessions" as const, label: "会话" },
    { key: "agents" as const, label: "Agent" },
    { key: "settings" as const, label: "设置" },
  ];

  return (
    <div className="h-screen w-screen flex overflow-hidden">
      <div className="w-72 h-full bg-gray-50 border-r border-gray-200 flex flex-col">
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
        {sidebarTab === "settings" && (
          <div className="flex-1 overflow-y-auto">
            <SettingsPanel providers={providers} onSaved={loadData} />
          </div>
        )}
      </div>

      {currentSessionId ? (
        <ChatWindow
          messages={messages} isStreaming={isStreaming}
          streamingError={streamingError}
          currentAgent={currentAgent} agents={agents} mode={currentMode}
          routeAgents={routeAgents} orchestratorIntent={orchestratorIntent}
          mentionableAgents={currentMode === "group" ? sessionMembers : agents}
          collabTasks={collabTasks}
          chainSteps={chainSteps}
          collabCompleted={collabCompleted}
          collabSummary={collabSummary}
          onSend={handleSend}
          onDismissError={() => setStreamingError(null)}
          onSwitchAgent={handleSwitchAgent}
        />
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-lg">
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
