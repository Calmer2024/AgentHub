import { useEffect, useRef } from "react";
import type { Message, Agent } from "../types";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";

interface Props {
  messages: Message[];
  isStreaming: boolean;
  streamingError: string | null;
  currentAgentName: string;
  agents: Agent[];
  onSend: (content: string) => void;
  onDismissError: () => void;
  onSwitchAgent: (agentName: string) => void;
  onOpenSettings: () => void;
}

export function ChatWindow({
  messages, isStreaming, streamingError,
  currentAgentName, agents,
  onSend, onDismissError, onSwitchAgent, onOpenSettings,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const currentAgent = agents.find((a) => a.name === currentAgentName);
  const agentAvailable = currentAgent?.isAvailable ?? false;
  const availableAgents = agents.filter((a) => a.isAvailable);

  return (
    <div className="flex-1 h-full flex flex-col">
      <div className="px-6 py-3 border-b border-gray-200 bg-white flex items-center justify-between">
        <div className="flex items-center gap-2">
          {agentAvailable ? (
            <select
              value={currentAgentName}
              onChange={(e) => onSwitchAgent(e.target.value)}
              className="text-lg font-semibold text-gray-900 bg-transparent border-none focus:outline-none cursor-pointer"
            >
              {agents.map((a) => (
                <option key={a.name} value={a.name} disabled={!a.isAvailable}>
                  {a.displayName}
                </option>
              ))}
            </select>
          ) : (
            <div>
              <h1 className="text-lg font-semibold text-red-600">
                {currentAgent?.displayName ?? currentAgentName} 不可用
              </h1>
              {availableAgents.length > 0 && (
                <select
                  value={availableAgents[0].name}
                  onChange={(e) => onSwitchAgent(e.target.value)}
                  className="text-sm text-blue-600 bg-transparent border-none focus:outline-none cursor-pointer mt-0.5"
                >
                  {availableAgents.map((a) => (
                    <option key={a.name} value={a.name}>{a.displayName}</option>
                  ))}
                </select>
              )}
            </div>
          )}
        </div>
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
          <button
            onClick={onOpenSettings}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            title="设置 API Key"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>
      </div>

      {!agentAvailable && (
        <div className="mx-6 mt-3 px-4 py-3 bg-red-50 border border-red-200 rounded-xl">
          <p className="text-sm text-red-700">
            {currentAgent?.displayName ?? currentAgentName} 的 API Key 未配置或无效，
            {availableAgents.length > 0 ? " 请从上方下拉菜单切换 Agent" : " 请在设置中配置 API Key"}
          </p>
        </div>
      )}

      {streamingError && (
        <div className="mx-6 mt-3 px-4 py-3 bg-red-50 border border-red-200 rounded-xl flex items-center justify-between">
          <span className="text-sm text-red-700">{streamingError}</span>
          <button onClick={onDismissError} className="ml-2 text-red-400 hover:text-red-600 text-sm">
            x
          </button>
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

      <ChatInput onSubmit={onSend} disabled={isStreaming || !agentAvailable} />
    </div>
  );
}
