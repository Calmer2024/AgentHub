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
  hydrating?: boolean;
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
  hydrating = false,
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
    : isGroup ? "多智能体协作" : currentAgent?.cliTool ?? "命令行智能体";

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
    <div className="agenthub-chat relative flex-1 h-full min-h-0 flex flex-col overflow-hidden transition-colors duration-300">
      {/* Header */}
      <div className="agenthub-header flex items-center justify-between border-b px-4 py-3 md:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <AgentAvatar
            agent={!isGroup ? currentAgent : undefined}
            name={isGroup ? "群聊" : currentAgent?.name ?? "未选择智能体"}
            kind={isGroup ? "group" : "agent"}
            size="md"
          />
          <div className="min-w-0">
            <h1 className="agenthub-strong truncate text-base font-semibold">
              {isGroup ? "群聊" : currentAgent?.name ?? "未选择智能体"}
            </h1>
            <p className="agenthub-muted mt-0.5 truncate text-xs">
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
            className="agenthub-icon-button relative inline-flex h-9 w-9 items-center justify-center rounded-full disabled:cursor-not-allowed disabled:opacity-45"
            aria-label={`会话文件，${artifacts.length} 个产物`}
            title={artifacts.length > 0 ? "会话文件" : "暂无会话文件"}
          >
            <Files size={15} />
            {artifacts.length > 0 && (
              <span className="agenthub-primary-button absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full border px-1 text-[10px] font-semibold"
                style={{ borderColor: "var(--ah-header-bg)" }}>
                {artifacts.length > 9 ? "9+" : artifacts.length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            className="agenthub-icon-button inline-flex h-9 w-9 items-center justify-center rounded-full"
            aria-label="搜索"
            title="搜索"
          >
            <Search size={15} />
          </button>
        </div>
      </div>
      {hydrating && (
        <div className="h-0.5 overflow-hidden bg-transparent" aria-label="正在同步当前对话">
          <div className="h-full w-1/2 animate-[agenthub-progress_920ms_ease-in-out_infinite] rounded-full bg-[color:var(--ah-accent-strong)]" />
        </div>
      )}

      {/* Alerts area (non-scrollable, stacks naturally) */}
      {!isGroup && !currentAgent && (
        <div className="agenthub-status-warning mx-6 mt-3 rounded-xl border px-4 py-3">
          <p className="text-sm">请先在智能体管理中创建或选择一个智能体</p>
        </div>
      )}

      {/* Orchestrator route banner */}
      {routeAgents && routeAgents.length > 0 && (
        <div className="agenthub-status-info mx-6 mt-3 rounded-xl border px-4 py-3">
          <p className="mb-1 text-xs font-medium">
            编排器已路由
            {orchestratorIntent && (
              <span className="agenthub-status ml-1.5 rounded px-1.5 py-0.5 text-[10px]">
                {INTENT_LABELS[orchestratorIntent] ?? orchestratorIntent}
              </span>
            )}
            :
          </p>
          <div className="flex flex-wrap gap-1.5">
            {routeAgents.map((a) => (
              <span key={a.id} className="agenthub-status inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium">
                @{a.name}
              </span>
            ))}
          </div>
          {planSummary && (
            <p className="mt-2 text-xs leading-relaxed">{planSummary}</p>
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
        <div className="agenthub-status-error mx-6 mt-3 flex items-center justify-between rounded-xl border px-4 py-3">
          <span className="text-sm">{streamingError}</span>
          <button
            type="button"
            onClick={onDismissError}
            className="ml-2 inline-flex h-7 w-7 items-center justify-center rounded-lg hover:bg-[color:var(--ah-danger-soft)]"
            aria-label="关闭错误提示"
            title="关闭错误提示"
          >
            <X size={15} />
          </button>
        </div>
      )}

      <div className="relative flex-1 min-h-0 flex overflow-hidden">
        {/* Messages area (scrollable) */}
        <div
          ref={scrollRef}
          className="agenthub-message-area relative min-h-0 w-full overflow-y-auto p-4 pb-28 md:p-6 md:pb-28"
        >
          {messages.length === 0 && collabTasks.length === 0 && hydrating ? (
            <MessageListSkeleton />
          ) : messages.length === 0 && collabTasks.length === 0 ? (
            <div className="agenthub-strong flex flex-col items-center justify-center h-full text-center">
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

function MessageListSkeleton() {
  return (
    <div className="flex h-full flex-col justify-end gap-4 pb-6" aria-label="正在加载消息">
      {Array.from({ length: 5 }).map((_, index) => {
        const user = index % 3 === 1;
        return (
          <div
            key={index}
            className={`flex items-end gap-2.5 ${user ? "flex-row-reverse" : ""}`}
          >
            <div className="h-10 w-10 shrink-0 animate-pulse rounded-full bg-[color:var(--ah-panel-muted)]" />
            <div
              className={`animate-pulse rounded-[20px] bg-[color:var(--ah-card-soft)] ${
                user ? "h-16 w-[min(58%,520px)] rounded-br-md" : "h-24 w-[min(76%,720px)] rounded-bl-md"
              }`}
            />
          </div>
        );
      })}
    </div>
  );
}

export const MemoChatWindow = memo(ChatWindow);
