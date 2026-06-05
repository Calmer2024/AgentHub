import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Info, Loader2, Pin } from "lucide-react";
import type { AgentConfig, Message, ReplyReference } from "../types";
import { MessageActions } from "./MessageActions";
import { ReplyPreview } from "./ReplyPreview";
import { ExecutionTracePanel } from "./ExecutionTracePanel";
import { AgentAvatar } from "./AgentAvatar";
import { OrchestratorPlanPanel } from "./OrchestratorPlanPanel";

interface Props {
  message: Message;
  isStreaming: boolean;
  agent?: AgentConfig | null;
  parentMessage?: Message | null;
  highlighted?: boolean;
  onReply: (message: Message) => void;
  onRegenerate: (message: Message) => void;
  onTogglePin: (message: Message) => void;
  onCopy: (content: string) => void;
  onJumpToMessage: (messageId: string) => void;
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
  planner: "border-violet-400 bg-violet-50 text-violet-700",
  executor: "border-blue-400 bg-blue-50 text-blue-700",
  reviewer: "border-amber-400 bg-amber-50 text-amber-700",
  researcher: "border-emerald-400 bg-emerald-50 text-emerald-700",
  synthesizer: "border-cyan-400 bg-cyan-50 text-cyan-700",
  critic: "border-red-400 bg-red-50 text-red-700",
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

function TypingIndicator() {
  return (
    <span className="inline-flex items-center gap-1 px-1 py-1">
      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
    </span>
  );
}

function EmptyAssistantReply() {
  return (
    <p className="inline-flex items-center gap-2 text-sm text-zinc-400">
      <Info size={14} aria-hidden="true" />
      <span>未返回可见回复</span>
    </p>
  );
}

function StreamingStatus() {
  return (
    <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-sky-300/15 bg-sky-300/10 px-2 py-1 text-[11px] text-sky-100">
      <Loader2 size={12} className="animate-spin" aria-hidden="true" />
      <span>正在生成</span>
    </div>
  );
}

export function MessageBubble({
  message, isStreaming, agent, parentMessage, highlighted = false,
  onReply, onRegenerate, onTogglePin, onCopy, onJumpToMessage,
}: Props) {
  const isUser = message.role === "user";
  const isEmpty = message.content === "";
  const traceStatus = message.metadata?.executionTrace?.status;
  const orchestratorPlan = message.metadata?.orchestratorPlan;
  const orchestratorPlanError = message.metadata?.orchestratorPlanError;
  const isLocalPending = message.id.startsWith("local-");
  const showTyping = !isUser && isEmpty && (
    traceStatus === "running" || (!traceStatus && isStreaming && isLocalPending)
  );
  const showEmptyAssistant = !isUser && isEmpty;
  const showStreamingStatus = !isUser && !isEmpty && (
    traceStatus === "running" || (!traceStatus && isStreaming && isLocalPending)
  );
  const isSummary = message.sourceType === "orchestrator" || message.contentType === "orchestrator_summary";
  const isCollaborating = Boolean(message.isCollaborating || message.agentRole);
  const roleStyle = message.agentRole
    ? ROLE_STYLES[message.agentRole] ?? ROLE_STYLES.executor
    : ROLE_STYLES.executor;

  const bgClass = isUser
    ? "bg-[#2f7cf6] text-white shadow-[0_12px_28px_rgba(47,124,246,0.28)]"
    : "border border-white/10 bg-[#1d2733]/95 text-[#ececf1] shadow-[0_14px_34px_rgba(0,0,0,0.18)]";
  const roundClass = isUser ? "rounded-[20px] rounded-br-md" : "rounded-[20px] rounded-bl-md";
  const summaryClass = "border border-indigo-300/25 bg-indigo-950/25 text-[#ececf1] shadow-sm";
  const bubbleClass = isSummary
    ? summaryClass
    : isCollaborating && !isUser
      ? `border-l-4 border-white/10 bg-[#1d2733]/95 text-[#ececf1] shadow-[0_14px_34px_rgba(0,0,0,0.18)] ${roleStyle.split(" ")[0]}`
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
  const avatarName = isUser
    ? "用户"
    : message.agentName ?? message.sourceName ?? "AI";

  return (
    <div className={`group relative mb-4 flex scroll-mt-6 items-end gap-2.5 transition ${
      isUser ? "flex-row-reverse justify-start" : "justify-start"
    } ${highlighted ? "rounded-2xl bg-yellow-100/10 ring-2 ring-yellow-300/60" : ""}`}>
      <AgentAvatar
        agent={avatarKind === "agent" ? agent : null}
        name={avatarName}
        kind={avatarKind}
        size="md"
        className="mb-0.5"
      />
      <div className={`${isSummary || orchestratorPlan ? "max-w-[min(92%,1080px)]" : "max-w-[min(78%,860px)]"} relative transition-transform duration-150 group-hover:-translate-y-0.5 ${bubbleClass} ${roundClass}`}>
        <MessageActions
          message={message}
          onReply={onReply}
          onRegenerate={onRegenerate}
          onTogglePin={onTogglePin}
          onCopy={onCopy}
        />
        {!isUser && isSummary && (
          <div className="sticky top-0 z-10 px-3 py-2 text-xs font-semibold rounded-t-[20px] bg-indigo-100/95 text-indigo-900 border-b border-indigo-200 shadow-sm">
            <span>系统整理</span>
            <span className="ml-2 text-indigo-600">{message.sourceName ?? "Orchestrator 中枢"}</span>
          </div>
        )}
        {!isUser && !isSummary && message.agentName && (
          <div className={`px-3 py-1.5 text-xs font-medium rounded-t-[20px] ${isCollaborating ? "bg-white/70 text-slate-700" : "border-b border-white/10 bg-white/[0.04] text-zinc-300"}`}>
            <span>@{message.agentName}</span>
            {message.agentRole && (
              <span className={`ml-2 px-1.5 py-0.5 rounded border ${roleStyle}`}>
                {ROLE_LABELS[message.agentRole] ?? message.agentRole}
              </span>
            )}
            {typeof message.phase === "number" && (
              <span className="ml-2 text-slate-400">Phase {message.phase}</span>
            )}
          </div>
        )}
        <div className="px-4 py-3">
        {message.isPinned && (
          <div className={`mb-2 text-xs font-medium ${isUser ? "text-blue-100" : "text-sky-300"}`}>
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
        ) : showTyping ? (
          <TypingIndicator />
        ) : isUser ? (
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
        ) : showEmptyAssistant ? (
          <EmptyAssistantReply />
        ) : (
          <div className="agent-markdown max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || "");
                  const codeStr = String(children).replace(/\n$/, "");
                  const isInline = !match && !codeStr.includes("\n");
                  if (isInline) {
                    return <code className="bg-black/10 rounded px-1 py-0.5 text-xs" {...props}>{children}</code>;
                  }
                  return (
                    <SyntaxHighlighter
                      style={oneDark}
                      language={match ? match[1] : "text"}
                      PreTag="div"
                      wrapLongLines
                      codeTagProps={{
                        style: {
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                        },
                      }}
                      customStyle={{
                        borderRadius: "0.75rem",
                        fontSize: "0.8rem",
                        maxWidth: "100%",
                        overflowX: "auto",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                      }}
                    >
                      {codeStr}
                    </SyntaxHighlighter>
                  );
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
        {hasPreviousVersion && previousVersion && (
          <details className="mt-3 rounded-md bg-white/[0.06] px-3 py-2 text-xs text-zinc-300">
            <summary className="cursor-pointer font-medium">查看原版</summary>
            <p className="mt-2 whitespace-pre-wrap">{previousVersion}</p>
          </details>
        )}
        {showStreamingStatus && <StreamingStatus />}
        {!isUser && (
          <ExecutionTracePanel trace={message.metadata?.executionTrace} />
        )}
        </div>
      </div>
    </div>
  );
}
