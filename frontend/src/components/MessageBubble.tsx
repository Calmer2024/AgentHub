import { memo, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Info, Pin } from "lucide-react";
import type {
  AgentConfig, ApprovalCheckpoint, Artifact, Message, ReplyReference, RunRead, TaskRead,
} from "../types";
import { MessageActions } from "./MessageActions";
import { ReplyPreview } from "./ReplyPreview";
import { ExecutionTracePanel } from "./ExecutionTracePanel";
import { AgentAvatar } from "./AgentAvatar";
import { OrchestratorPlanPanel } from "./OrchestratorPlanPanel";
import { OrchestratorExecutionPanel } from "./OrchestratorExecutionPanel";
import { MessageArtifactStrip } from "./MessageArtifactStrip";
import { RuntimeControlStrip } from "./RuntimeControlStrip";
import { ApprovalCard } from "./ApprovalCard";
import { formatChinaFullDateTime } from "../utils/time";

interface Props {
  message: Message;
  isStreaming?: boolean;
  artifacts?: Artifact[];
  relatedArtifacts?: Artifact[];
  run?: RunRead | null;
  tasks?: TaskRead[];
  approvals?: ApprovalCheckpoint[];
  relatedApprovals?: ApprovalCheckpoint[];
  artifactById?: Map<string, Artifact>;
  agent?: AgentConfig | null;
  parentMessage?: Message | null;
  highlighted?: boolean;
  selectionMode?: boolean;
  selected?: boolean;
  onReply: (message: Message) => void;
  onRegenerate: (message: Message) => void;
  onTogglePin: (message: Message) => void;
  onForward: (message: Message) => void;
  onMultiSelect: (message: Message) => void;
  onToggleSelect?: (message: Message) => void;
  onCopy: (content: string) => void;
  onJumpToMessage: (messageId: string) => void;
  onArtifactsChanged?: () => void;
  onCancelRun?: (runId: string) => void;
  cancellingRunId?: string | null;
  onApprove?: (approval: ApprovalCheckpoint) => void;
  onReject?: (approval: ApprovalCheckpoint) => void;
  onOpenApprovalArtifact?: (artifact: Artifact) => void;
  busyApprovalId?: string | null;
}

const ROLE_LABELS: Record<string, string> = {
  planner: "规划者",
  executor: "执行者",
  reviewer: "审查者",
  researcher: "研究员",
  synthesizer: "综合者",
  critic: "批判者",
};

const ROLE_STYLES: Record<string, string> = {
  planner: "border-indigo-300/40 bg-indigo-50 text-indigo-700",
  executor: "border-sky-300/40 bg-sky-50 text-sky-700",
  reviewer: "border-amber-300/50 bg-amber-50 text-amber-700",
  researcher: "border-emerald-300/45 bg-emerald-50 text-emerald-700",
  synthesizer: "border-cyan-300/45 bg-cyan-50 text-cyan-700",
  critic: "border-rose-300/45 bg-rose-50 text-rose-700",
};

function replyReference(message: Message): ReplyReference | null {
  const ref = message.metadata?.replyReference;
  if (!ref || typeof ref !== "object") return null;
  const data = ref as Record<string, unknown>;
  if (typeof data.id !== "string" || typeof data.content !== "string") return null;
  const role = data.role === "user" || data.role === "assistant" || data.role === "system"
    ? data.role
    : undefined;
  return {
    id: data.id,
    role,
    content: data.content,
    agentName: typeof data.agentName === "string" ? data.agentName : null,
    sourceName: typeof data.sourceName === "string" ? data.sourceName : null,
    createdAt: typeof data.createdAt === "string" ? data.createdAt : undefined,
  };
}

function EmptyAssistantReply() {
  return (
    <p className="agenthub-muted inline-flex items-center gap-2 text-sm">
      <Info size={14} aria-hidden="true" />
      <span>未返回可见回复</span>
    </p>
  );
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="agent-markdown min-w-0 max-w-full">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const codeStr = String(children).replace(/\n$/, "");
            const isInline = !match && !codeStr.includes("\n");
            if (isInline) {
              return <code className="agenthub-inline-code" {...props}>{children}</code>;
            }
            return (
              <pre className="agenthub-code-block min-w-0 max-w-full overflow-x-auto rounded-2xl border p-0 text-xs leading-5">
                <code className={match ? `language-${match[1]}` : undefined} {...props}>
                  {codeStr}
                </code>
              </pre>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function MessageBubbleBase({
  message, artifacts = [], relatedArtifacts, run = null, tasks = [],
  approvals = [], relatedApprovals, artifactById,
  agent, parentMessage, highlighted = false, selectionMode = false, selected = false,
  onReply, onRegenerate, onTogglePin, onForward, onMultiSelect, onToggleSelect,
  onCopy, onJumpToMessage, onArtifactsChanged,
  onCancelRun, cancellingRunId, onApprove, onReject, onOpenApprovalArtifact, busyApprovalId,
}: Props) {
  const [contextMenuPosition, setContextMenuPosition] = useState<{ x: number; y: number } | null>(null);
  const isUser = message.role === "user";
  const isEmpty = message.content === "";
  const orchestratorPlan = message.metadata?.orchestratorPlan;
  const orchestratorPlanError = message.metadata?.orchestratorPlanError;
  const orchestratorExecution = message.metadata?.orchestratorExecution;
  const showEmptyAssistant = !isUser && isEmpty;
  const isSummary = message.sourceType === "orchestrator" || message.contentType === "orchestrator_summary";
  const isCollaborating = Boolean(message.isCollaborating || message.agentRole);
  const roleStyle = message.agentRole
    ? ROLE_STYLES[message.agentRole] ?? ROLE_STYLES.executor
    : ROLE_STYLES.executor;

  const bgClass = isUser
    ? "agenthub-bubble-user"
    : "agenthub-bubble-agent border";
  const roundClass = isUser ? "rounded-[22px] rounded-br-lg" : "rounded-[22px] rounded-bl-lg";
  const summaryClass = "agenthub-card border";
  const bubbleClass = isSummary
    ? summaryClass
    : isCollaborating && !isUser ? `border-l-4 ${roleStyle}` : bgClass;

  const hasPreviousVersion = Array.isArray(message.metadata?.versions)
    && message.metadata.versions.length > 0;
  const versions = (message.metadata?.versions ?? []) as Array<{ content?: string }>;
  const previousVersion = hasPreviousVersion
    ? String(versions[versions.length - 1]?.content ?? "")
    : "";
  const referencedMessage = parentMessage ?? replyReference(message);
  const avatarKind = isUser
    ? "user"
    : isSummary
      ? "system"
      : "agent";
  const avatarName = isUser
    ? "用户"
    : message.agentName ?? message.sourceName ?? "AI";
  const messageApprovals = relatedApprovals ?? approvals.filter((approval) => approval.messageId === message.id);
  const artifactsById = artifactById ?? new Map(artifacts.map((artifact) => [artifact.id, artifact]));

  useEffect(() => {
    if (!contextMenuPosition) return;
    const close = () => setContextMenuPosition(null);
    window.addEventListener("mousedown", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [contextMenuPosition]);

  const openContextMenu = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const menuWidth = 176;
    const menuHeight = 184;
    setContextMenuPosition({
      x: Math.min(event.clientX, window.innerWidth - menuWidth - 8),
      y: Math.min(event.clientY, window.innerHeight - menuHeight - 8),
    });
  };

  return (
    <div className={`group relative mb-4 flex min-w-0 scroll-mt-6 items-end gap-2.5 transition ${
      isUser ? "flex-row-reverse justify-start" : "justify-start"
    } ${highlighted ? "rounded-2xl bg-[color:var(--ah-highlight-bg)] ring-2 ring-[color:var(--ah-border-strong)]" : ""}`}>
      {selectionMode && (
        <button
          type="button"
          onClick={() => onToggleSelect?.(message)}
          className={`agenthub-select-toggle mt-2 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border transition ${
            selected ? "agenthub-select-toggle-active" : ""
          }`}
          aria-label={selected ? "取消选择消息" : "选择消息"}
        >
          {selected && <span className="h-2.5 w-2.5 rounded-full bg-current" />}
        </button>
      )}
      <AgentAvatar
        agent={avatarKind === "agent" ? agent : null}
        name={avatarName}
        kind={avatarKind}
        size="md"
        className="mb-0.5"
      />
      <div className={`${isSummary || orchestratorPlan || orchestratorExecution ? "max-w-[min(92%,1080px)]" : "max-w-[min(78%,860px)]"} min-w-0 flex flex-col ${
        isUser ? "items-end" : "items-start"
      }`}>
        <div
          className={`relative min-w-0 max-w-full overflow-hidden ${
          isSummary ? `${summaryClass} w-full` : bubbleClass
        } ${roundClass}`}
          onContextMenu={openContextMenu}
        >
          <MessageActions
            message={message}
            open={Boolean(contextMenuPosition)}
            position={contextMenuPosition}
            onReply={onReply}
            onRegenerate={onRegenerate}
            onTogglePin={onTogglePin}
            onForward={onForward}
            onMultiSelect={onMultiSelect}
            onCopy={onCopy}
            onClose={() => setContextMenuPosition(null)}
          />
          {!isUser && isSummary && (
            <div className="agenthub-agent-namebar sticky top-0 z-10 rounded-t-[20px] px-3 pb-1.5 pt-2.5 text-xs font-semibold">
              <span>系统整理</span>
              <span className="agenthub-muted ml-2">{message.sourceName ?? "编排器中枢"}</span>
            </div>
          )}
          {!isUser && !isSummary && message.agentName && (
            <div className="agenthub-agent-namebar flex items-center gap-2 rounded-t-[20px] px-3 pb-1.5 pt-2.5 text-xs font-medium">
              <span className="agenthub-agent-name inline-flex min-w-0 items-center rounded-full px-2.5 py-0.5">
                <span className="truncate">@{message.agentName}</span>
              </span>
              {message.agentRole && (
                <span className={`rounded border px-1.5 py-0.5 ${roleStyle}`}>
                  {ROLE_LABELS[message.agentRole] ?? message.agentRole}
                </span>
              )}
              {typeof message.phase === "number" && (
                <span className="agenthub-muted">阶段 {message.phase}</span>
              )}
              {message.taskName && (
                <span className="agenthub-muted inline-block max-w-full truncate align-bottom">
                  {message.taskName}
                </span>
              )}
            </div>
          )}
          <div className={isUser ? "min-w-0 max-w-full px-5 py-3.5" : "min-w-0 max-w-full px-4 py-3.5"}>
          {message.isPinned && (
            <div className={`mb-2 text-xs font-medium ${isUser ? "text-current/80" : "agenthub-accent"}`}>
              <Pin size={13} aria-label="已 Pin" />
            </div>
          )}
          {message.parentMessageId && (
            <ReplyPreview
              message={referencedMessage}
              compact
              onJump={onJumpToMessage}
            />
          )}
          {orchestratorPlan ? (
            <OrchestratorPlanPanel plan={orchestratorPlan} rawJson={message.content} />
          ) : orchestratorPlanError ? (
            <div className="rounded-lg border border-red-300/25 bg-red-950/25 p-3 text-sm text-red-100">
              <p className="font-semibold">调度计划解析失败</p>
              <p className="mt-1 text-xs text-red-100/80">{orchestratorPlanError}</p>
              {message.content && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs font-semibold">查看原始输出</summary>
                  <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-black/35 p-2 text-[11px] leading-5 text-red-50">
                    {message.content}
                  </pre>
                </details>
              )}
            </div>
          ) : isUser ? (
            <MarkdownContent content={message.content} />
          ) : showEmptyAssistant ? (
            <EmptyAssistantReply />
          ) : (
            <MarkdownContent content={message.content} />
          )}
          {!isUser && orchestratorExecution && (
            <OrchestratorExecutionPanel initialExecution={orchestratorExecution} />
          )}
          {hasPreviousVersion && previousVersion && (
            <details className="agenthub-soft mt-3 rounded-md px-3 py-2 text-xs">
              <summary className="cursor-pointer font-medium">查看原版</summary>
              <p className="mt-2 whitespace-pre-wrap">{previousVersion}</p>
            </details>
          )}
          {!isUser && (
            <RuntimeControlStrip
              run={run}
              tasks={tasks}
              onCancel={(runId) => onCancelRun?.(runId)}
              cancelling={cancellingRunId === run?.id}
            />
          )}
          {!isUser && (
            <ExecutionTracePanel trace={message.metadata?.executionTrace} />
          )}
          {!isUser && (
            <MessageArtifactStrip
              message={message}
              artifacts={artifacts}
              relatedArtifacts={relatedArtifacts}
              onChanged={onArtifactsChanged}
            />
          )}
          {!isUser && messageApprovals.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              artifact={approval.artifactId ? artifactsById.get(approval.artifactId) ?? null : null}
              busy={busyApprovalId === approval.id}
              onApprove={(item) => onApprove?.(item)}
              onReject={(item) => onReject?.(item)}
              onOpenArtifact={(artifact) => onOpenApprovalArtifact?.(artifact)}
            />
          ))}
          </div>
        </div>
        <time className={`agenthub-message-meta mt-1.5 block px-1 text-[11px] ${isUser ? "text-right" : "text-left"}`}>
          {formatChinaFullDateTime(message.createdAt)}
        </time>
      </div>
    </div>
  );
}

export const MessageBubble = memo(MessageBubbleBase);
