import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Message, ReplyReference } from "../types";
import { MessageActions } from "./MessageActions";
import { ReplyPreview } from "./ReplyPreview";

interface Props {
  message: Message;
  isStreaming: boolean;
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

export function MessageBubble({
  message, isStreaming, parentMessage, highlighted = false,
  onReply, onRegenerate, onTogglePin, onCopy, onJumpToMessage,
}: Props) {
  const isUser = message.role === "user";
  const isEmpty = message.content === "";
  const showTyping = !isUser && isEmpty && isStreaming;
  const isSummary = message.sourceType === "orchestrator" || message.contentType === "orchestrator_summary";
  const isCollaborating = Boolean(message.isCollaborating || message.agentRole);
  const roleStyle = message.agentRole
    ? ROLE_STYLES[message.agentRole] ?? ROLE_STYLES.executor
    : ROLE_STYLES.executor;

  const bgClass = isUser
    ? "bg-blue-600 text-white justify-end"
    : "bg-gray-100 text-gray-900 justify-start";
  const roundClass = isUser ? "rounded-2xl rounded-tr-none" : "rounded-2xl rounded-tl-none";
  const summaryClass = "border border-indigo-200 bg-indigo-50 text-slate-900 shadow-sm";

  const agentColors = ["bg-green-100 text-green-700", "bg-orange-100 text-orange-700", "bg-purple-100 text-purple-700", "bg-pink-100 text-pink-700", "bg-teal-100 text-teal-700", "bg-indigo-100 text-indigo-700", "bg-cyan-100 text-cyan-700", "bg-amber-100 text-amber-700"];
  const colorIdx = message.agentName ? [...message.agentName].reduce((s, c) => s + c.charCodeAt(0), 0) % agentColors.length : 0;
  const agentColor = agentColors[colorIdx];
  const hasPreviousVersion = Array.isArray(message.metadata?.versions)
    && message.metadata.versions.length > 0;
  const versions = (message.metadata?.versions ?? []) as Array<{ content?: string }>;
  const previousVersion = hasPreviousVersion
    ? String(versions[versions.length - 1]?.content ?? "")
    : "";
  const referencedMessage = parentMessage ?? replyReference(message);

  return (
    <div className={`group relative flex mb-4 scroll-mt-6 ${isUser ? "justify-end" : "justify-start"} ${
      highlighted ? "rounded-xl bg-yellow-100/70 ring-2 ring-yellow-300" : ""
    }`}>
      <div className={`${isSummary ? "max-w-[92%]" : "max-w-[80%]"} relative ${
        isSummary ? summaryClass : isCollaborating && !isUser ? `border-l-4 ${roleStyle}` : bgClass
      } ${roundClass}`}>
        <MessageActions
          message={message}
          onReply={onReply}
          onRegenerate={onRegenerate}
          onTogglePin={onTogglePin}
          onCopy={onCopy}
        />
        {!isUser && isSummary && (
          <div className="sticky top-0 z-10 px-3 py-2 text-xs font-semibold rounded-t-2xl bg-indigo-100/95 text-indigo-900 border-b border-indigo-200 shadow-sm">
            <span>系统整理</span>
            <span className="ml-2 text-indigo-600">{message.sourceName ?? "Orchestrator 中枢"}</span>
          </div>
        )}
        {!isUser && !isSummary && message.agentName && (
          <div className={`px-3 py-1 text-xs font-medium rounded-t-2xl ${isCollaborating ? "bg-white/70 text-slate-700" : agentColor}`}>
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
          <div className={`mb-2 text-xs font-medium ${isUser ? "text-blue-100" : "text-blue-600"}`}>
            Pin
          </div>
        )}
        {message.parentMessageId && (
          <ReplyPreview
            message={referencedMessage}
            compact
            onJump={onJumpToMessage}
          />
        )}
        {showTyping ? (
          <TypingIndicator />
        ) : isEmpty ? (
          <p className="text-gray-400 italic">...</p>
        ) : isUser ? (
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
        ) : (
          <div className="prose prose-sm max-w-none dark:prose-invert [&_pre]:!bg-[#282c34] [&_pre]:!rounded-xl [&_pre]:!p-4 [&_code]:text-sm [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_h1]:text-lg [&_h2]:text-base [&_h3]:text-sm [&_blockquote]:border-l-2 [&_blockquote]:border-gray-300 [&_blockquote]:pl-3 [&_blockquote]:text-gray-500 [&_a]:text-blue-500 [&_a]:underline [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-gray-300 [&_th]:px-2 [&_th]:py-1 [&_th]:bg-gray-50 [&_td]:border [&_td]:border-gray-300 [&_td]:px-2 [&_td]:py-1">
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
          <details className="mt-3 rounded-md bg-white/70 px-3 py-2 text-xs text-slate-600">
            <summary className="cursor-pointer font-medium">查看原版</summary>
            <p className="mt-2 whitespace-pre-wrap">{previousVersion}</p>
          </details>
        )}
        </div>
      </div>
    </div>
  );
}
