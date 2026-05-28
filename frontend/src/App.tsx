import { useEffect, useCallback, useRef, useState } from "react";
import { useChatStore } from "./stores/chatStore";
import { useSessionStore } from "./stores/sessionStore";
import { SessionList } from "./components/SessionList";
import { ChatWindow } from "./components/ChatWindow";
import { AgentPanel } from "./components/AgentPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { GroupChatCreator } from "./components/GroupChatCreator";
import { CollabProgressCard } from "./components/CollabProgressCard";
import type { CollabTask } from "./components/CollabProgressCard";
import { createSession, createGroupSession, fetchSessions, fetchMessages, fetchAgents, fetchProviders, createChatStream, updateSessionAgent, deleteSession, renameSession, summarizeSession, fetchSessionMembers } from "./api/client";
import { WSClient } from "./api/wsClient";
import type { Message, AgentConfig } from "./types";

function App() {
  const {
    currentSessionId, messages, isStreaming, streamingError,
    setCurrentSessionId, setMessages,
    appendMessage, appendStreamingToken, appendAgentStreamingToken,
    setIsStreaming, setStreamingError,
  } = useChatStore();

  const {
    sessions, agents, providers, sidebarTab,
    setSessions, setAgents, setProviders, setSidebarTab, updateSession,
  } = useSessionStore();

  const wsRef = useRef<WSClient | null>(null);
  const [showGroupCreator, setShowGroupCreator] = useState(false);
  const [routeAgents, setRouteAgents] = useState<Array<{ id: string; name: string }> | null>(null);
  const [sessionMembers, setSessionMembers] = useState<AgentConfig[]>([]);
  const [collabTasks, setCollabTasks] = useState<CollabTask[]>([]);
  const [orchestratorIntent, setOrchestratorIntent] = useState<string | null>(null);

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

  const handleSelectSession = async (id: string) => {
    const sess = sessions.find((s) => s.id === id);
    setCurrentSessionId(id);
    setMessages([]);
    setStreamingError(null);
    setRouteAgents(null);
    setCollabTasks([]);
    setOrchestratorIntent(null);
    try { setMessages(await fetchMessages(id)); } catch { /* */ }
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
  };

  const handleDeleteSession = async (id: string) => {
    await deleteSession(id);
    setSessions(sessions.filter((s) => s.id !== id));
    if (currentSessionId === id) { setCurrentSessionId(null); setMessages([]); }
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

  const handleSend = async (content: string, mentions: string[]) => {
    if (!currentSessionId) return;
    setStreamingError(null);
    setRouteAgents(null);
    setCollabTasks([]);
    setOrchestratorIntent(null);

    const userMsg: Message = {
      id: `local-${Date.now()}`, sessionId: currentSessionId,
      role: "user", content, agentName: null, createdAt: new Date().toISOString(),
    };
    appendMessage(userMsg);

    const agentPlaceholders = new Map<string, string>();

    const cleanup = createChatStream(currentSessionId, content, mentions,
      (token) => appendStreamingToken(token),
      (messageId, error) => {
        setIsStreaming(false);
        if (error) {
          setStreamingError(error === "Stream ended unexpectedly"
            ? "连接中断，请检查网络后重试" : `请求失败：${error}`);
          return;
        }
        if (messageId) fetchMessages(currentSessionId).then(setMessages);
      },
      (agents) => {
        setRouteAgents(agents);
        const tasks: CollabTask[] = agents.map((a) => ({
          task: "协作中",
          agentName: a.name,
          status: "running" as const,
        }));
        setCollabTasks(tasks);
        agents.forEach((a) => {
          const localId = `local-agent-${a.id}-${Date.now()}`;
          agentPlaceholders.set(a.id, localId);
          appendMessage({
            id: localId, sessionId: currentSessionId!,
            role: "assistant", content: "", agentName: a.name,
            createdAt: new Date().toISOString(),
          });
        });
        setIsStreaming(true);
      },
      (agentId, agentName, token) => {
        const localId = agentPlaceholders.get(agentId);
        if (localId) appendAgentStreamingToken(localId, agentName, token);
      },
    );
    cleanup;

    const currentMode = sessions.find((s) => s.id === currentSessionId)?.mode ?? "single";
    if (currentMode !== "group") {
      const localId = `local-ai-${Date.now()}`;
      appendMessage({
        id: localId, sessionId: currentSessionId!,
        role: "assistant", content: "", agentName: null,
        createdAt: new Date().toISOString(),
      });
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
          routeAgents={routeAgents} mentionableAgents={currentMode === "group" ? sessionMembers : agents}
          onSend={handleSend}
          onDismissError={() => setStreamingError(null)}
          onSwitchAgent={handleSwitchAgent}
        />
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-lg">
          点击左侧"新建对话"开始
        </div>
      )}

      {collabTasks.length > 0 && (
        <div className="absolute top-16 left-96 right-0 z-10">
          <CollabProgressCard
            title={orchestratorIntent ? `智能协作 — ${orchestratorIntent}` : "Agent 协作进行中"}
            tasks={collabTasks}
          />
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
