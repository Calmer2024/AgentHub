import { useEffect, useRef } from "react";
import type { Message, AgentConfig } from "../types";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";

interface Props {
  messages: Message[];
  isStreaming: boolean;
  streamingError: string | null;
  currentAgent: AgentConfig | null;
  agents: AgentConfig[];
  onSend: (content: string, mentions: string[]) => void;
  onDismissError: () => void;
  onSwitchAgent: (agentId: string) => void;
}

export function ChatWindow({
  messages, isStreaming, streamingError,
  currentAgent, agents,
  onSend, onDismissError, onSwitchAgent,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  return (
    <div className="flex-1 h-full flex flex-col">
      <div className="px-6 py-3 border-b border-gray-200 bg-white flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-900">
          {currentAgent?.name ?? "未选择 Agent"}
        </h1>
        <div className="flex items-center gap-3">
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
      </div>

      {!currentAgent && (
        <div className="mx-6 mt-3 px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl">
          <p className="text-sm text-amber-700">请先在 Agent 管理页面创建或选择一个 Agent</p>
        </div>
      )}

      {streamingError && (
        <div className="mx-6 mt-3 px-4 py-3 bg-red-50 border border-red-200 rounded-xl flex items-center justify-between">
          <span className="text-sm text-red-700">{streamingError}</span>
          <button onClick={onDismissError} className="ml-2 text-red-400 hover:text-red-600 text-sm">x</button>
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 bg-white">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <p className="text-lg">开始对话吧</p>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} isStreaming={isStreaming} />
          ))
        )}
      </div>

      <div className="border-t border-gray-200 px-4 py-2 flex items-center gap-3">
        <span className="text-xs text-gray-500">Agent:</span>
        <select
          value={currentAgent?.id ?? ""}
          onChange={(e) => onSwitchAgent(e.target.value)}
          disabled={isStreaming}
          className="text-xs px-2 py-1 border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 max-w-[200px]"
        >
          {agents.length === 0 && <option value="">无可用 Agent</option>}
          {agents.map((a) => (
            <option key={a.id} value={a.id}>{a.name} ({a.provider}/{a.model})</option>
          ))}
        </select>
      </div>

      <ChatInput onSubmit={onSend} disabled={isStreaming || !currentAgent} agents={agents} />
    </div>
  );
}
