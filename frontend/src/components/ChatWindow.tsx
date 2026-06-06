import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Files, Search, X } from "lucide-react";
import type { Message, AgentConfig, CollabTask, ChainStep, DAGPhase, Artifact, ApprovalCheckpoint, TaskRead } from "../types";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { CollaborationPanel } from "./CollaborationPanel";
import { SearchPanel } from "./SearchPanel";
import {
  approveCheckpoint,
  cancelRun,
  fetchApprovals,
  fetchArtifacts,
  fetchMessages,
  fetchRuns,
  fetchSystemHealth,
  rejectCheckpoint,
  replyToInteractivePrompt,
} from "../api/client";
import { useChatStore } from "../stores/chatStore";
import { InteractivePromptCard } from "./InteractivePromptCard";
import { AgentAvatar } from "./AgentAvatar";
import { SessionArtifactManager } from "./SessionArtifactManager";
import { HealthCheckCard } from "./HealthCheckCard";
import { ArtifactReviewModal } from "./ArtifactReviewModal";

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

const ACTIVE_RUN_STATUSES = new Set(["queued", "running", "pausing", "cancelling"]);
const EMPTY_TASKS: TaskRead[] = [];
const EMPTY_ARTIFACTS: Artifact[] = [];
const EMPTY_APPROVALS: ApprovalCheckpoint[] = [];

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
  const [artifactManagerOpen, setArtifactManagerOpen] = useState(false);
  const [reviewArtifact, setReviewArtifact] = useState<Artifact | null>(null);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [cancellingRunId, setCancellingRunId] = useState<string | null>(null);
  const [busyApprovalId, setBusyApprovalId] = useState<string | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const interactivePrompts = useChatStore((state) => state.interactivePrompts);
  const removeInteractivePrompt = useChatStore((state) => state.removeInteractivePrompt);
  const runs = useChatStore((state) => state.runs);
  const tasksByRun = useChatStore((state) => state.tasksByRun);
  const approvals = useChatStore((state) => state.approvals);
  const systemHealth = useChatStore((state) => state.systemHealth);
  const setApprovalsForSession = useChatStore((state) => state.setApprovalsForSession);
  const setArtifactsForSession = useChatStore((state) => state.setArtifactsForSession);
  const setMessagesForSession = useChatStore((state) => state.setMessagesForSession);
  const setRunsForSession = useChatStore((state) => state.setRunsForSession);
  const setSystemHealth = useChatStore((state) => state.setSystemHealth);
  const setStreamingError = useChatStore((state) => state.setStreamingError);
  const setReplyTarget = useChatStore((state) => state.setReplyTarget);
  const setCodeReference = useChatStore((state) => state.setCodeReference);
  const cancelRunLocally = useChatStore((state) => state.cancelRunLocally);
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
  const sessionPrompts = useMemo(
    () => interactivePrompts.filter((prompt) => prompt.sessionId === currentSessionId),
    [currentSessionId, interactivePrompts],
  );
  const promptsByMessageId = useMemo(() => {
    const map = new Map<string, typeof sessionPrompts>();
    sessionPrompts.forEach((prompt) => {
      const list = map.get(prompt.messageId) ?? [];
      list.push(prompt);
      map.set(prompt.messageId, list);
    });
    return map;
  }, [sessionPrompts]);
  const messageIds = useMemo(() => new Set(messages.map((message) => message.id)), [messages]);
  const detachedPrompts = useMemo(
    () => sessionPrompts.filter((prompt) => !messageIds.has(prompt.messageId)),
    [messageIds, sessionPrompts],
  );
  const messageById = useMemo(() => new Map(messages.map((m) => [m.id, m])), [messages]);
  const agentByName = useMemo(() => {
    const map = new Map<string, AgentConfig>();
    agents.forEach((agent) => map.set(agent.name, agent));
    return map;
  }, [agents]);
  const artifactById = useMemo(() => new Map(artifacts.map((artifact) => [artifact.id, artifact])), [artifacts]);
  const artifactsByMessageId = useMemo(() => {
    const map = new Map<string, Artifact[]>();
    artifacts.forEach((artifact) => {
      const list = map.get(artifact.messageId) ?? [];
      list.push(artifact);
      map.set(artifact.messageId, list);
    });
    return map;
  }, [artifacts]);
  const approvalsByMessageId = useMemo(() => {
    const map = new Map<string, ApprovalCheckpoint[]>();
    approvals.forEach((approval) => {
      if (!approval.messageId) return;
      const list = map.get(approval.messageId) ?? [];
      list.push(approval);
      map.set(approval.messageId, list);
    });
    return map;
  }, [approvals]);
  const latestRunByMessageId = useMemo(() => {
    const map = new Map<string, typeof runs[number]>();
    runs.forEach((run) => {
      if (!run.currentMessageId) return;
      const existing = map.get(run.currentMessageId);
      if (!existing || Date.parse(run.updatedAt) > Date.parse(existing.updatedAt)) {
        map.set(run.currentMessageId, run);
      }
    });
    return map;
  }, [runs]);
  const hasActiveRun = useMemo(() => runs.some((run) => ACTIVE_RUN_STATUSES.has(run.status)), [runs]);
  const headerStatus = isStreaming || hasActiveRun
    ? "对方正在输入"
    : isGroup ? "多人 Agent 协作" : currentAgent?.cliTool ?? "CLI Agent";

  const refreshRuntime = useCallback(async () => {
    try {
      setMessagesForSession(currentSessionId, await fetchMessages(currentSessionId));
    } catch { /* 保留已有消息 */ }
    try {
      setArtifactsForSession(currentSessionId, await fetchArtifacts(currentSessionId));
    } catch { /* 保留已有产物 */ }
    try {
      setRunsForSession(currentSessionId, await fetchRuns(currentSessionId));
    } catch { /* 保留已有运行状态 */ }
    try {
      setApprovalsForSession(currentSessionId, await fetchApprovals(currentSessionId));
    } catch { /* 保留已有审批状态 */ }
  }, [
    currentSessionId,
    setApprovalsForSession,
    setArtifactsForSession,
    setMessagesForSession,
    setRunsForSession,
  ]);

  const refreshHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      setSystemHealth(await fetchSystemHealth({ sessionId: currentSessionId }));
    } catch {
      setSystemHealth(null);
      setStreamingError("环境体检暂不可用，请稍后重试", currentSessionId);
    } finally {
      setHealthLoading(false);
    }
  }, [currentSessionId, setStreamingError, setSystemHealth]);

  const handleCancelRun = useCallback(async (runId: string) => {
    setCancellingRunId(runId);
    const reason = "用户在界面中停止运行";
    cancelRunLocally(runId, reason);
    try {
      await cancelRun(runId, reason);
      await refreshRuntime();
    } catch {
      setStreamingError("本地输出已停止，但后端取消运行失败，请稍后刷新状态", currentSessionId);
    } finally {
      setCancellingRunId(null);
    }
  }, [cancelRunLocally, refreshRuntime, setStreamingError]);

  const handleApprove = useCallback(async (approvalId: string) => {
    setBusyApprovalId(approvalId);
    try {
      await approveCheckpoint(approvalId);
      await refreshRuntime();
    } catch {
      setStreamingError("审批确认失败，请刷新后重试", currentSessionId);
    } finally {
      setBusyApprovalId(null);
    }
  }, [refreshRuntime, setStreamingError]);

  const handleReject = useCallback(async (approvalId: string) => {
    const approval = approvals.find((item) => item.id === approvalId);
    if (!approval) return;
    const reason = window.prompt("请输入修改原因");
    if (!reason?.trim()) return;
    setBusyApprovalId(approvalId);
    try {
      const artifact = approval.artifactId ? artifactById.get(approval.artifactId) : null;
      const codeReference = artifact ? {
        artifactId: artifact.id,
        projectId: artifact.projectId ?? null,
        filePath: artifact.filePath ?? null,
        title: artifact.title,
        language: artifact.type === "code_diff" ? "diff" : "text",
        content: artifact.content.slice(0, 4000),
      } : null;
      await rejectCheckpoint(approvalId, {
        reason: reason.trim(),
        artifactId: approval.artifactId ?? undefined,
        artifactVersion: approval.artifactVersion ?? undefined,
        codeReference,
      });
      if (codeReference) setCodeReference(codeReference);
      const sourceMessage = approval.messageId ? messageById.get(approval.messageId) : null;
      if (sourceMessage) setReplyTarget(sourceMessage);
      window.dispatchEvent(new Event("agenthub:focus-chat-input"));
      await refreshRuntime();
    } catch {
      setStreamingError("审批驳回失败，请刷新后重试", currentSessionId);
    } finally {
      setBusyApprovalId(null);
    }
  }, [
    approvals,
    artifactById,
    messageById,
    refreshRuntime,
    setCodeReference,
    setReplyTarget,
    setStreamingError,
  ]);

  const copyContent = useCallback((content: string) => {
    void navigator.clipboard?.writeText(content);
  }, []);

  const cancelMessageRun = useCallback((runId: string) => {
    void handleCancelRun(runId);
  }, [handleCancelRun]);

  const approveMessageCheckpoint = useCallback((approval: ApprovalCheckpoint) => {
    void handleApprove(approval.id);
  }, [handleApprove]);

  const rejectMessageCheckpoint = useCallback((approval: ApprovalCheckpoint) => {
    void handleReject(approval.id);
  }, [handleReject]);

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

  const jumpToMessage = useCallback((messageId: string) => {
    const el = messageRefs.current[messageId];
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightedMessageId(messageId);
    window.setTimeout(() => setHighlightedMessageId((id) => (id === messageId ? null : id)), 2000);
  }, []);

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
              {headerStatus}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden w-40 sm:block">
            <HealthCheckCard
              health={systemHealth}
              loading={healthLoading}
              compact
              onRefresh={() => void refreshHealth()}
            />
          </div>
          <button
            type="button"
            onClick={() => setArtifactManagerOpen(true)}
            disabled={artifacts.length === 0}
            className="relative inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 text-[#d8d8df] transition hover:bg-white/[0.07] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45"
            aria-label={`会话文件，${artifacts.length} 个产物`}
            title={artifacts.length > 0 ? "会话文件" : "暂无会话文件"}
          >
            <Files size={15} />
            {artifacts.length > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full border border-[#17212b] bg-[#2f7cf6] px-1 text-[10px] font-semibold text-white">
                {artifacts.length > 9 ? "9+" : artifacts.length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 text-[#d8d8df] transition hover:bg-white/[0.07] active:translate-y-px"
            aria-label="搜索"
            title="搜索"
          >
            <Search size={15} />
          </button>
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
          className="relative min-h-0 w-full overflow-y-auto bg-[radial-gradient(circle_at_top_left,rgba(47,124,246,0.12),transparent_32%),linear-gradient(180deg,#0f141a_0%,#111820_100%)] p-4 md:p-6"
        >
          {messages.length === 0 && collabTasks.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center text-[#ececf1]">
              <p className="text-2xl font-medium">
                {isGroup ? "我们应该先讨论什么？" : "开始对话吧"}
              </p>
            </div>
          ) : (
            messages.map((msg) => {
              const prompts = promptsByMessageId.get(msg.id) ?? [];
              const messageRun = latestRunByMessageId.get(msg.id) ?? null;
              const relatedApprovals = approvalsByMessageId.get(msg.id) ?? EMPTY_APPROVALS;
              return (
                <div key={msg.id} ref={(el) => { messageRefs.current[msg.id] = el; }}>
                  <MessageBubble
                    message={msg}
                    relatedArtifacts={artifactsByMessageId.get(msg.id) ?? EMPTY_ARTIFACTS}
                    run={messageRun}
                    tasks={messageRun ? tasksByRun[messageRun.id] ?? EMPTY_TASKS : EMPTY_TASKS}
                    relatedApprovals={relatedApprovals}
                    artifactById={relatedApprovals.length > 0 ? artifactById : undefined}
                    agent={msg.agentName ? agentByName.get(msg.agentName) ?? null : null}
                    parentMessage={msg.parentMessageId ? messageById.get(msg.parentMessageId) ?? null : null}
                    highlighted={highlightedMessageId === msg.id}
                    onReply={onReply}
                    onRegenerate={onRegenerate}
                    onTogglePin={onTogglePin}
                    onCopy={copyContent}
                    onJumpToMessage={jumpToMessage}
                    onArtifactsChanged={onArtifactsChanged}
                    onCancelRun={cancelMessageRun}
                    cancellingRunId={cancellingRunId}
                    onApprove={approveMessageCheckpoint}
                    onReject={rejectMessageCheckpoint}
                    onOpenApprovalArtifact={setReviewArtifact}
                    busyApprovalId={busyApprovalId}
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
                              setStreamingError("确认回复失败，CLI 进程可能已经退出", currentSessionId);
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
      </div>

      {detachedPrompts.length > 0 && (
        <div className="mx-6 mt-3 space-y-2">
          {detachedPrompts.map((prompt) => (
            <InteractivePromptCard
              key={prompt.processId}
              content={prompt.content}
              onReply={async (reply) => {
                try {
                  await replyToInteractivePrompt(prompt.sessionId, prompt.processId, reply);
                  removeInteractivePrompt(prompt.processId);
                } catch {
                  setStreamingError("确认回复失败，CLI 进程可能已经退出", currentSessionId);
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
      <SessionArtifactManager
        open={artifactManagerOpen}
        artifacts={artifacts}
        onClose={() => setArtifactManagerOpen(false)}
        onChanged={onArtifactsChanged}
      />
      <ArtifactReviewModal
        artifact={reviewArtifact}
        onClose={() => setReviewArtifact(null)}
        onChanged={onArtifactsChanged}
      />

      {/* Chat input */}
      <ChatInput
        onSubmit={onSend}
        disabled={isStreaming || hasActiveRun || (!isGroup && !currentAgent)}
        busy={isStreaming || hasActiveRun}
        mentionableAgents={isGroup ? mentionableAgents : agents}
      />
    </div>
  );
}

export const MemoChatWindow = memo(ChatWindow);
