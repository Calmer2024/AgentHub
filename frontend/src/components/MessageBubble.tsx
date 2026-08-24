import { memo, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { Check, Copy, Info, Pin } from "lucide-react";
import type {
  AgentConfig, ApprovalCheckpoint, Artifact, CurrentUser, Message, ReplyReference, RunRead, TaskRead,
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
  currentUser?: CurrentUser | null;
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
  onOpenAgentSettings?: (agentId: string) => void;
}

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
          pre({ children }) {
            // react-markdown 默认会再包一层 <pre>；代码块自身已经提供完整表面，避免双卡片嵌套。
            return <>{children}</>;
          },
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const codeStr = String(children).replace(/\n$/, "");
            const isInline = !match && !codeStr.includes("\n");
            if (isInline) {
              return <code className="agenthub-inline-code" {...props}>{children}</code>;
            }
            return <MessageCodeBlock code={codeStr} language={match?.[1]} className={className} />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function MessageCodeBlock({ code, language, className }: { code: string; language?: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch { /* clipboard unavailable */ }
  };
  return (
    <div className="agenthub-message-code-block">
      <div className="agenthub-message-code-banner">
        <span>{language ?? ""}</span>
        <button type="button" onClick={() => void copy()} aria-label={copied ? "复制成功" : "复制代码"}>
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || "text"}
        PreTag="div"
        style={{}}
        className="agenthub-message-code-syntax"
        customStyle={{
          margin: 0,
          padding: "16px 18px",
          background: "transparent",
          color: "var(--ah-code-text)",
          fontFamily: '"SF Mono", "JetBrains Mono", "Fira Code", Consolas, monospace',
          fontSize: "15px",
          lineHeight: 1.8,
          whiteSpace: "pre-wrap",
          overflowX: "auto",
        }}
        codeTagProps={{ className: className ?? "" }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

function messageDisplayTime(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const hour = `${date.getHours()}`.padStart(2, "0");
  const minute = `${date.getMinutes()}`.padStart(2, "0");
  return `${month}-${day} ${hour}:${minute}`;
}

function MessageBubbleBase({
  message, artifacts = [], relatedArtifacts, run = null, tasks = [],
  approvals = [], relatedApprovals, artifactById,
  isStreaming = false,
  agent, currentUser, parentMessage, highlighted = false, selectionMode = false, selected = false,
  onReply, onRegenerate, onTogglePin, onForward, onMultiSelect, onToggleSelect,
  onCopy, onJumpToMessage, onArtifactsChanged,
  onCancelRun, cancellingRunId, onApprove, onReject, onOpenApprovalArtifact, busyApprovalId,
  onOpenAgentSettings,
}: Props) {
  const [contextMenuPosition, setContextMenuPosition] = useState<{ x: number; y: number } | null>(null);
  const isUser = message.role === "user";
  const isEmpty = message.content === "";
  const orchestratorPlan = message.metadata?.orchestratorPlan;
  const orchestratorPlanError = message.metadata?.orchestratorPlanError;
  const orchestratorExecution = message.metadata?.orchestratorExecution;
  const traceStatus = message.metadata?.executionTrace?.status;
  const traceFinished = traceStatus === "completed" || traceStatus === "error" || traceStatus === "cancelled";
  const runActive = run?.status === "queued" || run?.status === "running" || run?.status === "pausing" || run?.status === "cancelling";
  const suppressEmptyAssistant = !isUser && isEmpty && !traceFinished && (isStreaming || runActive);
  const showEmptyAssistant = !isUser && isEmpty && !suppressEmptyAssistant;
  const isSummary = message.sourceType === "orchestrator" || message.contentType === "orchestrator_summary";
  const bgClass = isUser
    ? "agenthub-bubble-user"
    : "agenthub-bubble-agent";
  const roundClass = "rounded-[14px]";
  const summaryClass = "agenthub-card";
  const bubbleClass = isSummary
    ? summaryClass
    : bgClass;

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
  const currentUserName = currentUser?.displayName || currentUser?.username || currentUser?.email || "你";
  const userDisplayName = message.sourceName || currentUserName;
  const avatarName = isUser
    ? userDisplayName
    : message.agentName ?? message.sourceName ?? "AI";
  const displayName = isUser ? userDisplayName : message.agentName ?? message.sourceName ?? "AI";
  const displayTime = messageDisplayTime(message.createdAt);
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
    const menuWidth = 132;
    const menuHeight = 184;
    setContextMenuPosition({
      x: Math.min(event.clientX, window.innerWidth - menuWidth - 8),
      y: Math.min(event.clientY, window.innerHeight - menuHeight - 8),
    });
  };

  return (
    <div className={`agenthub-message-row group relative mb-6 flex min-w-0 scroll-mt-6 items-start gap-4 transition ${
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
      {!isUser && avatarKind === "agent" && agent ? (
        <button type="button" onClick={() => onOpenAgentSettings?.(agent.id)} className="shrink-0 rounded-full" aria-label={`配置 ${agent.name}`} title="打开智能体配置">
          <AgentAvatar agent={agent} name={avatarName} kind="agent" size="md" className="mt-0.5" />
        </button>
      ) : !isUser ? (
        <AgentAvatar agent={null} name={avatarName} kind={avatarKind} size="md" className="mt-0.5" />
      ) : null}
      <div className={`${isSummary || orchestratorPlan || orchestratorExecution ? "max-w-[min(92%,1080px)]" : isUser ? "max-w-[min(68%,720px)]" : "max-w-[min(88%,1120px)]"} min-w-0 flex flex-col ${
        isUser ? "items-end" : "items-start"
      }`}>
        <div className={`agenthub-message-head mb-1.5 flex min-w-0 items-center gap-2 px-0.5 text-xs ${isUser ? "flex-row-reverse text-right" : ""}`}>
          {!isUser && <span className="agenthub-message-author truncate">{displayName}</span>}
          {!isUser && <span className="agenthub-message-ai-badge">AI</span>}
          <time className="agenthub-message-time">{displayTime}</time>
        </div>
        <div
          className={`agenthub-message-bubble relative min-w-0 max-w-full overflow-hidden ${
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
            <div className="agenthub-agent-namebar sticky top-0 z-10 rounded-t-[12px] px-3 pb-1.5 pt-2.5 text-xs font-semibold">
              <span>系统整理</span>
              <span className="agenthub-muted ml-2">{message.sourceName ?? "编排器中枢"}</span>
            </div>
          )}
          <div className={isUser ? "min-w-0 max-w-full px-4 py-3" : "min-w-0 max-w-full px-4 py-3.5 md:px-5"}>
          {message.isPinned && (
            <div className={`mb-2 text-xs font-medium ${isUser ? "text-current/80" : "agenthub-accent"}`}>
              <Pin size={13} aria-label="已 Pin" />
            </div>
          )}
          {message.parentMessageId && (
            <ReplyPreview
              message={referencedMessage}
              compact
              currentUserName={currentUserName}
              onJump={onJumpToMessage}
            />
          )}
          {orchestratorPlan ? (
            <OrchestratorPlanPanel plan={orchestratorPlan} rawJson={message.content} />
          ) : orchestratorPlanError ? (
            <div className="agenthub-status-error rounded-lg border p-3 text-sm">
              <p className="font-semibold">调度计划解析失败</p>
              <p className="mt-1 text-xs opacity-80">{orchestratorPlanError}</p>
              {message.content && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs font-semibold">查看原始输出</summary>
                  <pre className="agenthub-code-block mt-2 max-h-72 overflow-auto rounded-md p-2 text-[11px] leading-5">
                    {message.content}
                  </pre>
                </details>
              )}
            </div>
          ) : isUser ? (
            <MarkdownContent content={message.content} />
          ) : showEmptyAssistant ? (
            <EmptyAssistantReply />
          ) : suppressEmptyAssistant ? null : (
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
        {!isUser && (
          <div className="agenthub-message-execution w-full">
            <RuntimeControlStrip
              run={run}
              tasks={tasks}
              onCancel={(runId) => onCancelRun?.(runId)}
              cancelling={cancellingRunId === run?.id}
            />
            <ExecutionTracePanel trace={message.metadata?.executionTrace} />
          </div>
        )}
      </div>
    </div>
  );
}

export const MessageBubble = memo(MessageBubbleBase);
