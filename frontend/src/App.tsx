import { useEffect, useState, useCallback } from "react";
import { useChatStore } from "./stores/chat";
import { SessionList } from "./components/SessionList";
import { ChatWindow } from "./components/ChatWindow";
import { SettingsModal } from "./components/SettingsModal";
import { createSession, fetchSessions, fetchMessages, fetchAgents, createChatStream, updateSessionAgent } from "./api/client";
import type { Message } from "./types";

function App() {
  const {
    sessions,
    currentSessionId,
    messages,
    isStreaming,
    streamingError,
    agents,
    setSessions,
    setCurrentSessionId,
    setMessages,
    appendMessage,
    appendStreamingToken,
    setIsStreaming,
    setStreamingError,
    setAgents,
    settingsOpen,
    setSettingsOpen,
    updateSession,
  } = useChatStore();

  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    setAgentsLoading(true);
    setAgentsError(null);
    try {
      const a = await fetchAgents();
      setAgents(a);
    } catch {
      setAgentsError("无法加载 Agent 列表");
    } finally {
      setAgentsLoading(false);
    }
  }, [setAgents]);

  useEffect(() => {
    (async () => {
      try {
        const s = await fetchSessions();
        setSessions(s);
      } catch { /* sessions 加载失败不影响页面使用 */ }
    })();
    loadAgents();
  }, [setSessions, loadAgents]);

  const handleSelectSession = async (id: string) => {
    setCurrentSessionId(id);
    setStreamingError(null);
    try {
      const msgs = await fetchMessages(id);
      setMessages(msgs);
    } catch { /* 消息加载失败 */ }
  };

  const handleNewSession = async (title: string, agentName: string) => {
    const newSess = await createSession(title, agentName);
    setSessions([newSess, ...sessions]);
    setCurrentSessionId(newSess.id);
    setMessages([]);
    setStreamingError(null);
  };

  const handleSwitchAgent = async (agentName: string) => {
    if (!currentSessionId) return;
    try {
      const updated = await updateSessionAgent(currentSessionId, agentName);
      updateSession(updated);
    } catch { /* 切换失败 */ }
  };

  const handleSend = async (content: string) => {
    if (!currentSessionId) return;

    setStreamingError(null);

    const userMsg: Message = {
      id: `local-${Date.now()}`,
      sessionId: currentSessionId,
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    };
    appendMessage(userMsg);

    const assistantPlaceholder: Message = {
      id: `local-ai-${Date.now()}`,
      sessionId: currentSessionId,
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
    };
    appendMessage(assistantPlaceholder);
    setIsStreaming(true);

    createChatStream(
      currentSessionId,
      content,
      (token) => appendStreamingToken(token),
      (messageId, error) => {
        setIsStreaming(false);
        if (error) {
          setStreamingError(error === "Stream ended unexpectedly"
            ? "连接中断，请检查网络后重试"
            : `请求失败：${error}`);
          return;
        }
        if (messageId) {
          fetchMessages(currentSessionId).then(setMessages);
        }
      },
    );
  };

  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const currentAgentName = currentSession?.agentName ?? "";

  return (
    <div className="h-screen w-screen flex overflow-hidden">
      <SessionList
        sessions={sessions}
        currentSessionId={currentSessionId}
        agents={agents}
        agentsLoading={agentsLoading}
        agentsError={agentsError}
        onRetryAgents={loadAgents}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      {currentSessionId ? (
        <ChatWindow
          messages={messages}
          isStreaming={isStreaming}
          streamingError={streamingError}
          currentAgentName={currentAgentName}
          agents={agents}
          onSend={handleSend}
          onDismissError={() => setStreamingError(null)}
          onSwitchAgent={handleSwitchAgent}
          onOpenSettings={() => setSettingsOpen(true)}
        />
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-lg">
          选择 Agent 后点击"新建对话"开始
        </div>
      )}
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => { setSettingsOpen(false); loadAgents(); }}
      />
    </div>
  );
}

export default App;
