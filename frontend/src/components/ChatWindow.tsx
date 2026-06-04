import { useEffect, useMemo, useRef, useState } from "react";
import type { Message, AgentConfig, CollabTask, ChainStep, DAGPhase, Artifact } from "../types";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { CollaborationPanel } from "./CollaborationPanel";
import { SearchPanel } from "./SearchPanel";
import { ArtifactCard } from "./ArtifactCard";

interface Props {
  messages: Message[];
  artifacts: Artifact[];
  isStreaming: boolean;
  streamingError: string | null;
  currentAgent: AgentConfig | null;
  currentSessionId: string;
  agents: AgentConfig[];
  mode: string;
  routeAgents: Array<{ id: string; name: string }> | null;
  orchestratorIntent: string | null;
  planSummary: string | null;
  mentionableAgents: AgentConfig[];
  // CollaborationView props (inline in message flow)
  collabTasks: CollabTask[];
  dagPhases: DAGPhase[];
  chainSteps: ChainStep[];
  collabCompleted: boolean;
  collabSummary: string | null;
  onSend: (content: string, mentions: string[]) => void;
  onDismissError: () => void;
  onSwitchAgent: (agentId: string) => void;
  onReply: (message: Message) => void;
  onRegenerate: (message: Message) => void;
  onTogglePin: (message: Message) => void;
  onArtifactsChanged: () => void;
}

const INTENT_LABELS: Record<string, string> = {
  code_gen: "代码生成",
  research: "调研分析",
  design_ui: "UI 设计",
  general_qa: "通用问答",
};

export function ChatWindow({
  messages, artifacts, isStreaming, streamingError,
  currentAgent, currentSessionId, agents, mode, routeAgents, orchestratorIntent, planSummary, mentionableAgents,
  collabTasks, dagPhases, collabCompleted, collabSummary,
  onSend, onDismissError, onSwitchAgent, onReply, onRegenerate, onTogglePin, onArtifactsChanged,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [searchOpen, setSearchOpen] = useState(false);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, collabTasks, dagPhases]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const isGroup = mode === "group";
  const messageById = useMemo(() => new Map(messages.map((m) => [m.id, m])), [messages]);

  const jumpToMessage = (messageId: string) => {
    const el = messageRefs.current[messageId];
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightedMessageId(messageId);
    window.setTimeout(() => setHighlightedMessageId((id) => (id === messageId ? null : id)), 2000);
  };

  return (
    <div className="relative flex-1 h-full min-h-0 flex flex-col overflow-hidden bg-[#171717] text-[#ececf1]">
      {/* Header */}
      <div className="px-6 py-3 border-b border-white/[0.08] bg-[#171717] flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isGroup && <span className="text-sm">👥</span>}
          <h1 className="text-lg font-semibold text-white">
            {isGroup ? "群聊" : currentAgent?.name ?? "未选择 Agent"}
          </h1>
          {isGroup && <span className="text-xs text-[#8f8f98] bg-white/[0.06] px-2 py-0.5 rounded">@提及 Agent</span>}
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-sm text-[#d8d8df] hover:bg-white/[0.07]"
          >
            搜索
          </button>
          {isStreaming && (
            <span className="inline-flex items-center gap-2 text-sm text-[#d8d8df]">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#ececf1] opacity-50" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#ececf1]" />
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
          {planSummary && (
            <p className="mt-2 text-xs text-blue-700 leading-relaxed">{planSummary}</p>
          )}
        </div>
      )}

      {/* CollaborationPanel — inline in natural flow, below route banner */}
      {collabTasks.length > 0 && (
        <CollaborationPanel
          intent={orchestratorIntent}
          tasks={collabTasks}
          phases={dagPhases}
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

      <div className="relative flex-1 min-h-0 flex overflow-hidden bg-[#171717]">
        {/* Messages area (scrollable) */}
        <div
          ref={scrollRef}
          className={`relative min-h-0 overflow-y-auto p-4 md:p-6 bg-[#171717] ${
            artifacts.length > 0 ? "flex-1" : "w-full"
          }`}
        >
          {messages.length === 0 && collabTasks.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center text-[#ececf1]">
              <p className="text-2xl font-medium">
                {isGroup ? "我们应该先讨论什么？" : "开始对话吧"}
              </p>
            </div>
          ) : (
            messages.map((msg) => (
              <div key={msg.id} ref={(el) => { messageRefs.current[msg.id] = el; }}>
                <MessageBubble
                  message={msg}
                  isStreaming={isStreaming}
                  parentMessage={msg.parentMessageId ? messageById.get(msg.parentMessageId) ?? null : null}
                  highlighted={highlightedMessageId === msg.id}
                  onReply={onReply}
                  onRegenerate={onRegenerate}
                  onTogglePin={onTogglePin}
                  onCopy={(content) => navigator.clipboard?.writeText(content)}
                  onJumpToMessage={jumpToMessage}
                />
              </div>
            ))
          )}
        </div>

        {artifacts.length > 0 && (
          <aside className="hidden w-[420px] shrink-0 border-l border-white/[0.08] bg-[#202123] md:flex md:flex-col">
            <div className="border-b border-white/[0.08] px-4 py-3">
              <div className="text-sm font-semibold text-white">产物工作台</div>
              <div className="mt-0.5 text-xs text-[#8f8f98]">{artifacts.length} 个当前产物</div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {artifacts.map((artifact) => (
                <ArtifactCard
                  key={artifact.id}
                  artifact={artifact}
                  onChanged={onArtifactsChanged}
                />
              ))}
            </div>
          </aside>
        )}

        {artifacts.length > 0 && (
          <div className="fixed bottom-24 right-4 z-20 md:hidden">
            <button
              type="button"
              onClick={() => document.getElementById("mobile-artifacts")?.scrollIntoView({ behavior: "smooth" })}
              className="rounded-lg bg-[#ececf1] px-3 py-2 text-sm font-medium text-[#171717] shadow-lg"
            >
              产物
            </button>
          </div>
        )}
      </div>

      {artifacts.length > 0 && (
        <div id="mobile-artifacts" className="max-h-[36dvh] overflow-y-auto border-t border-white/[0.08] bg-[#202123] p-3 md:hidden">
          {artifacts.map((artifact) => (
            <ArtifactCard
              key={artifact.id}
              artifact={artifact}
              onChanged={onArtifactsChanged}
            />
          ))}
        </div>
      )}

      <SearchPanel
        sessionId={currentSessionId}
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        onJump={(_, messageId) => jumpToMessage(messageId)}
      />

      {/* Agent selector (single chat only) */}
      {!isGroup && (
        <div className="border-t border-white/[0.08] px-4 py-2 flex items-center gap-3">
          <span className="text-xs text-[#8f8f98]">Agent:</span>
          <select value={currentAgent?.id ?? ""} onChange={(e) => onSwitchAgent(e.target.value)} disabled={isStreaming}
            className="text-xs px-2 py-1 border border-white/10 rounded-lg bg-[#2b2b2f] text-[#ececf1] focus:outline-none focus:ring-2 focus:ring-white/20 max-w-[200px]">
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
