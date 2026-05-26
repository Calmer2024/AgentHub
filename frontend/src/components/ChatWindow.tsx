import { useEffect, useRef } from "react";
import type { Message } from "../types";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";

interface Props {
  messages: Message[];
  isStreaming: boolean;
  streamingError: string | null;
  onSend: (content: string) => void;
  onDismissError: () => void;
}

export function ChatWindow({ messages, isStreaming, streamingError, onSend, onDismissError }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="flex-1 h-full flex flex-col">
      <div className="px-6 py-4 border-b border-gray-200 bg-white flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">AgentHub 聊天</h1>
        {isStreaming && (
          <span className="inline-flex items-center gap-2 text-sm text-blue-600">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
            </span>
            AI 正在回复...
          </span>
        )}
      </div>

      {streamingError && (
        <div className="mx-6 mt-3 px-4 py-3 bg-red-50 border border-red-200 rounded-xl flex items-center justify-between">
          <span className="text-sm text-red-700">{streamingError}</span>
          <button
            onClick={onDismissError}
            className="ml-2 text-red-400 hover:text-red-600 text-sm"
          >
            x
          </button>
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 bg-white">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <p className="text-lg">开始和 Claude 对话吧</p>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} isStreaming={isStreaming} />
          ))
        )}
      </div>

      <ChatInput onSubmit={onSend} disabled={isStreaming} />
    </div>
  );
}
