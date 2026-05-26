import { useEffect, useCallback, useRef } from "react";
import { useChatStore } from "./stores/chat";
import { SessionList } from "./components/SessionList";
import { ChatWindow } from "./components/ChatWindow";
import { AgentPanel } from "./components/AgentPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { createSession, fetchSessions, fetchMessages, fetchAgents, fetchProviders, createChatStream, updateSessionAgent } from "./api/client";
import { WSClient } from "./api/wsClient";
import type { Message } from "./types";

function App() {
  const {
    sessions, currentSessionId, messages,
    isStreaming, streamingError,
    sidebarTab,
    setSessions, setCurrentSessionId, setMessages,
    appendMessage, appendStreamingToken,
    setIsStreaming, setStreamingError,
    setSidebarTab, updateSession,
    agents, setAgents, providers, setProviders,
  } = useChatStore();

  const wsRef = useRef<WSClient | null>(null);

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
        updateSession({ ...sessions.find((s) => s.id === currentSessionId)!, agentConfigId: data.agentConfigId });
      }
    });

    ws.connect(currentSessionId);

    return () => { ws.disconnect(); };
  }, [currentSessionId]); // 切换会话时自动断开旧连接 + 建立新连接

  const loadData = useCallback(async () => {
    try { setSessions(await fetchSessions()); } catch { /* */ }
    try { setAgents(await fetchAgents()); } catch { /* */ }
    try { setProviders(await fetchProviders()); } catch { /* */ }
  }, [setSessions, setAgents, setProviders]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSelectSession = async (id: string) => {
    setCurrentSessionId(id);
    setStreamingError(null);
    try { setMessages(await fetchMessages(id)); } catch { /* */ }
  };

  const handleNewSession = async () => {
    const s = await createSession();
    setSessions([s, ...sessions]);
    setCurrentSessionId(s.id);
    setMessages([]);
    setStreamingError(null);
  };

  const handleSwitchAgent = async (agentId: string) => {
    if (!currentSessionId) return;
    try { updateSession(await updateSessionAgent(currentSessionId, agentId)); } catch { /* */ }
  };

  const handleSend = async (content: string) => {
    if (!currentSessionId) return;
    setStreamingError(null);

    const userMsg: Message = {
      id: `local-${Date.now()}`, sessionId: currentSessionId,
      role: "user", content, createdAt: new Date().toISOString(),
    };
    appendMessage(userMsg);

    appendMessage({
      id: `local-ai-${Date.now()}`, sessionId: currentSessionId,
      role: "assistant", content: "", createdAt: new Date().toISOString(),
    });
    setIsStreaming(true);

    createChatStream(currentSessionId, content,
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
    );
  };

  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const currentAgent = agents.find((a) => a.id === currentSession?.agentConfigId) ?? null;

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
          currentAgent={currentAgent} agents={agents}
          onSend={handleSend}
          onDismissError={() => setStreamingError(null)}
          onSwitchAgent={handleSwitchAgent}
        />
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-lg">
          点击左侧"新建对话"开始
        </div>
      )}
    </div>
  );
}

export default App;
