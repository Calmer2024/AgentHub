import { useEffect } from "react";
import { useChatStore } from "./stores/chat";
import { SessionList } from "./components/SessionList";
import { ChatWindow } from "./components/ChatWindow";
import { createSession, fetchSessions, fetchMessages, createChatStream } from "./api/client";
import type { Message } from "./types";

function App() {
  const {
    sessions,
    currentSessionId,
    messages,
    isStreaming,
    streamingError,
    setSessions,
    setCurrentSessionId,
    setMessages,
    appendMessage,
    appendStreamingToken,
    setIsStreaming,
    setStreamingError,
  } = useChatStore();

  useEffect(() => {
    (async () => {
      const s = await fetchSessions();
      setSessions(s);
    })();
  }, [setSessions]);

  const handleSelectSession = async (id: string) => {
    setCurrentSessionId(id);
    setStreamingError(null);
    const msgs = await fetchMessages(id);
    setMessages(msgs);
  };

  const handleNewSession = async () => {
    const newSess = await createSession();
    setSessions([newSess, ...sessions]);
    setCurrentSessionId(newSess.id);
    setMessages([]);
    setStreamingError(null);
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

  return (
    <div className="h-screen w-screen flex overflow-hidden">
      <SessionList
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
      />
      {currentSessionId ? (
        <ChatWindow
          messages={messages}
          isStreaming={isStreaming}
          streamingError={streamingError}
          onSend={handleSend}
          onDismissError={() => setStreamingError(null)}
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
