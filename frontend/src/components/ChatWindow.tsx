import { useEffect, useRef } from "react";
import type { Message, AgentConfig, CollabTask, ChainStep } from "../types";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { CollaborationView } from "./CollaborationView";

interface Props {
  messages: Message[];
  isStreaming: boolean;
  streamingError: string | null;
  currentAgent: AgentConfig | null;
  agents: AgentConfig[];
  mode: string;
  routeAgents: Array<{ id: string; name: string }> | null;
  orchestratorIntent: string | null;
  mentionableAgents: AgentConfig[];
  // CollaborationView props (inline in message flow)
  collabTasks: CollabTask[];
  chainSteps: ChainStep[];
  collabCompleted: boolean;
  collabSummary: string | null;
  onSend: (content: string, mentions: string[]) => void;
  onDismissError: () => void;
  onSwitchAgent: (agentId: string) => void;
}

const INTENT_LABELS: Record<string, string> = {
  code_gen: "代码生成",
  research: "调研分析",
  design_ui: "UI 设计",
  general_qa: "通用问答",
};

export function ChatWindow({
  messages, isStreaming, streamingError,
  currentAgent, agents, mode, routeAgents, orchestratorIntent, mentionableAgents,
  collabTasks, chainSteps, collabCompleted, collabSummary,
  onSend, onDismissError, onSwitchAgent,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, collabTasks, chainSteps]);

  const isGroup = mode === "group";

  return (
    <div className="flex-1 h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-3 border-b border-gray-200 bg-white flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isGroup && <span className="text-sm">👥</span>}
          <h1 className="text-lg font-semibold text-gray-900">
            {isGroup ? "群聊" : currentAgent?.name ?? "未选择 Agent"}
          </h1>
          {isGroup && <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">@提及 Agent</span>}
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
        </div>
      </div>

      {/* Alerts area (non-scrollable, stacks naturally) */}
      {!isGroup && !currentAgent && (
        <div className="mx-6 mt-3 px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl">
          <p className="text-sm text-amber-700">请先在 Agent 管理页面创建或选择一个 Agent</p>
        </div>
      )}

      {/* Orchestrator route banner */}
      {routeAgents && routeAgents.length > 0 && (
        <div className="mx-6 mt-3 px-4 py-3 bg-blue-50 border border-blue-200 rounded-xl">
          <p className="text-xs text-blue-600 font-medium mb-1">
            Orchestrator 已路由
            {orchestratorIntent && (
              <span className="ml-1.5 px-1.5 py-0.5 bg-blue-100 text-blue-500 rounded text-[10px]">
                {INTENT_LABELS[orchestratorIntent] ?? orchestratorIntent}
              </span>
            )}
            :
          </p>
          <div className="flex flex-wrap gap-1.5">
            {routeAgents.map((a) => (
              <span key={a.id} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full text-xs font-medium">
                @{a.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* CollaborationView — inline in natural flow, below route banner */}
      {collabTasks.length > 0 && (
        <CollaborationView
          intent={orchestratorIntent}
          tasks={collabTasks}
          chainSteps={chainSteps}
          isCompleted={collabCompleted}
          completedSummary={collabSummary}
        />
      )}

      {/* Error banner */}
      {streamingError && (
        <div className="mx-6 mt-3 px-4 py-3 bg-red-50 border border-red-200 rounded-xl flex items-center justify-between">
          <span className="text-sm text-red-700">{streamingError}</span>
          <button onClick={onDismissError} className="ml-2 text-red-400 hover:text-red-600 text-sm">x</button>
        </div>
      )}

      {/* Messages area (scrollable) */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 bg-white">
        {messages.length === 0 && collabTasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <p className="text-lg">{isGroup ? "群聊开始，输入 @ 提及 Agent" : "开始对话吧"}</p>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} isStreaming={isStreaming} />
          ))
        )}
      </div>

      {/* Agent selector (single chat only) */}
      {!isGroup && (
        <div className="border-t border-gray-200 px-4 py-2 flex items-center gap-3">
          <span className="text-xs text-gray-500">Agent:</span>
          <select value={currentAgent?.id ?? ""} onChange={(e) => onSwitchAgent(e.target.value)} disabled={isStreaming}
            className="text-xs px-2 py-1 border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 max-w-[200px]">
            {agents.length === 0 && <option value="">无可用 Agent</option>}
            {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
      )}

      {/* Chat input */}
      <ChatInput onSubmit={onSend} disabled={isStreaming || (!isGroup && !currentAgent)} mentionableAgents={isGroup ? mentionableAgents : agents} />
    </div>
  );
}
