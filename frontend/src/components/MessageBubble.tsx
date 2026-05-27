import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Message } from "../types";

interface Props {
  message: Message;
  isStreaming: boolean;
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

export function MessageBubble({ message, isStreaming }: Props) {
  const isUser = message.role === "user";
  const isEmpty = message.content === "";
  const showTyping = !isUser && isEmpty && isStreaming;

  const bgClass = isUser
    ? "bg-blue-600 text-white justify-end"
    : "bg-gray-100 text-gray-900 justify-start";
  const roundClass = isUser ? "rounded-2xl rounded-tr-none" : "rounded-2xl rounded-tl-none";

  const agentColors = ["bg-green-100 text-green-700", "bg-orange-100 text-orange-700", "bg-purple-100 text-purple-700", "bg-pink-100 text-pink-700", "bg-teal-100 text-teal-700", "bg-indigo-100 text-indigo-700", "bg-cyan-100 text-cyan-700", "bg-amber-100 text-amber-700"];
  const colorIdx = message.agentName ? [...message.agentName].reduce((s, c) => s + c.charCodeAt(0), 0) % agentColors.length : 0;
  const agentColor = agentColors[colorIdx];

  return (
    <div className={`flex mb-4 ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[80%] ${bgClass} ${roundClass}`}>
        {!isUser && message.agentName && (
          <div className={`px-3 py-1 text-xs font-medium rounded-t-2xl ${agentColor}`}>
            {message.agentName}
          </div>
        )}
        <div className="px-4 py-3">
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
                      customStyle={{ borderRadius: "0.75rem", fontSize: "0.8rem" }}
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
        </div>
      </div>
    </div>
  );
}
