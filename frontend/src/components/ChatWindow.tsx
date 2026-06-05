import { useEffect, useMemo, useRef, useState } from "react";
import { Boxes, Search, X } from "lucide-react";
import type { Message, AgentConfig, CollabTask, ChainStep, DAGPhase, Artifact } from "../types";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { CollaborationPanel } from "./CollaborationPanel";
import { SearchPanel } from "./SearchPanel";
import { ArtifactCard } from "./ArtifactCard";
import { replyToInteractivePrompt } from "../api/client";
import { useChatStore } from "../stores/chatStore";
import { InteractivePromptCard } from "./InteractivePromptCard";
import { AgentAvatar } from "./AgentAvatar";

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
  onSend, onDismissError, onReply, onRegenerate, onTogglePin, onArtifactsChanged,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const autoScrollSessionRef = useRef<string | null>(null);
  const autoScrollUserSignatureRef = useRef<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const { interactivePrompts, removeInteractivePrompt, setStreamingError } = useChatStore();
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
  const agentByName = useMemo(() => {
    const map = new Map<string, AgentConfig>();
    agents.forEach((agent) => map.set(agent.name, agent));
    return map;
  }, [agents]);

  useEffect(() => {
    const userMessages = messages.filter((message) => message.role === "user");
    const latestUser = userMessages[userMessages.length - 1] ?? null;
    const signature = latestUser
      ? `${currentSessionId}:${userMessages.length}:${latestUser.parentMessageId ?? ""}:${latestUser.content}`
      : null;

    if (autoScrollSessionRef.current !== currentSessionId) {
      autoScrollSessionRef.current = currentSessionId;
      autoScrollUserSignatureRef.current = signature;
      return;
    }
    if (!latestUser || !signature || signature === autoScrollUserSignatureRef.current) return;

    autoScrollUserSignatureRef.current = signature;
    window.requestAnimationFrame(() => {
      messageRefs.current[latestUser.id]?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }, [currentSessionId, messages]);

  const jumpToMessage = (messageId: string) => {
    const el = messageRefs.current[messageId];
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightedMessageId(messageId);
    window.setTimeout(() => setHighlightedMessageId((id) => (id === messageId ? null : id)), 2000);
  };

  return (
    <div className="relative flex-1 h-full min-h-0 flex flex-col overflow-hidden bg-[#0f141a] text-[#ececf1]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.08] bg-[#17212b]/95 px-4 py-3 backdrop-blur md:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <AgentAvatar
            agent={!isGroup ? currentAgent : undefined}
            name={isGroup ? "群聊" : currentAgent?.name ?? "未选择 Agent"}
            kind={isGroup ? "group" : "agent"}
            size="md"
          />
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-white">
              {isGroup ? "群聊" : currentAgent?.name ?? "未选择 Agent"}
            </h1>
            <p className="mt-0.5 truncate text-xs text-[#9aa5b1]">
              {isStreaming ? "正在输入" : isGroup ? "多人 Agent 协作" : currentAgent?.cliTool ?? "CLI Agent"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 text-[#d8d8df] transition hover:bg-white/[0.07] active:translate-y-px"
            aria-label="搜索"
            title="搜索"
          >
            <Search size={15} />
          </button>
          {isStreaming && (
            <span className="inline-flex items-center gap-2 text-sm text-[#d8d8df]">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#ececf1] opacity-50" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#ececf1]" />
              </span>
              正在回复
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
          <button
            type="button"
            onClick={onDismissError}
            className="ml-2 inline-flex h-7 w-7 items-center justify-center rounded-lg text-red-400 hover:bg-red-100 hover:text-red-600"
            aria-label="关闭错误提示"
            title="关闭错误提示"
          >
            <X size={15} />
          </button>
        </div>
      )}

      <div className="relative flex-1 min-h-0 flex overflow-hidden bg-[#0f141a]">
        {/* Messages area (scrollable) */}
        <div
          ref={scrollRef}
          className={`relative min-h-0 overflow-y-auto bg-[radial-gradient(circle_at_top_left,rgba(47,124,246,0.12),transparent_32%),linear-gradient(180deg,#0f141a_0%,#111820_100%)] p-4 md:p-6 ${
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
            messages.map((msg) => {
              const prompts = interactivePrompts.filter((prompt) => prompt.messageId === msg.id);
              return (
                <div key={msg.id} ref={(el) => { messageRefs.current[msg.id] = el; }}>
                  <MessageBubble
                    message={msg}
                    isStreaming={isStreaming}
                    agent={msg.agentName ? agentByName.get(msg.agentName) ?? null : null}
                    parentMessage={msg.parentMessageId ? messageById.get(msg.parentMessageId) ?? null : null}
                    highlighted={highlightedMessageId === msg.id}
                    onReply={onReply}
                    onRegenerate={onRegenerate}
                    onTogglePin={onTogglePin}
                    onCopy={(content) => navigator.clipboard?.writeText(content)}
                    onJumpToMessage={jumpToMessage}
                  />
                  {prompts.length > 0 && (
                    <div className="mb-4 ml-3 max-w-[min(82%,860px)] space-y-2">
                      {prompts.map((prompt) => (
                        <InteractivePromptCard
                          key={prompt.processId}
                          content={prompt.content}
                          onReply={async (reply) => {
                            try {
                              await replyToInteractivePrompt(prompt.sessionId, prompt.processId, reply);
                              removeInteractivePrompt(prompt.processId);
                            } catch {
                              setStreamingError("确认回复失败，CLI 进程可能已经退出");
                            }
                          }}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })
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
              className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-[#ececf1] text-[#171717] shadow-lg"
              aria-label="产物"
              title="产物"
            >
              <Boxes size={18} />
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

      {interactivePrompts.some((prompt) => !messages.some((msg) => msg.id === prompt.messageId)) && (
        <div className="mx-6 mt-3 space-y-2">
          {interactivePrompts.filter((prompt) => !messages.some((msg) => msg.id === prompt.messageId)).map((prompt) => (
            <InteractivePromptCard
              key={prompt.processId}
              content={prompt.content}
              onReply={async (reply) => {
                try {
                  await replyToInteractivePrompt(prompt.sessionId, prompt.processId, reply);
                  removeInteractivePrompt(prompt.processId);
                } catch {
                  setStreamingError("确认回复失败，CLI 进程可能已经退出");
                }
              }}
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

      {/* Chat input */}
      <ChatInput onSubmit={onSend} disabled={isStreaming || (!isGroup && !currentAgent)} mentionableAgents={isGroup ? mentionableAgents : agents} />
    </div>
  );
}
