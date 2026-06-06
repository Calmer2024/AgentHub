import { useState, useRef, useEffect, type FormEvent, type KeyboardEvent } from "react";
import { Code2, FileCode2, SendHorizontal, X } from "lucide-react";
import type { AgentConfig } from "../types";
import { useChatStore } from "../stores/chatStore";
import { ReplyPreview } from "./ReplyPreview";
import { AgentAvatar } from "./AgentAvatar";

interface Props {
  onSubmit: (content: string, mentions: string[]) => void;
  disabled?: boolean;
  busy?: boolean;
  mentionableAgents: AgentConfig[];
}

export function ChatInput({ onSubmit, disabled, busy, mentionableAgents }: Props) {
  const [content, setContent] = useState("");
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);
  const [mentionPos, setMentionPos] = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const replyTarget = useChatStore((state) => state.replyTarget);
  const setReplyTarget = useChatStore((state) => state.setReplyTarget);
  const codeReference = useChatStore((state) => state.codeReference);
  const setCodeReference = useChatStore((state) => state.setCodeReference);

  useEffect(() => {
    if (showMentions && listRef.current) {
      const active = listRef.current.children[mentionIndex] as HTMLElement | undefined;
      active?.scrollIntoView({ block: "nearest" });
    }
  }, [mentionIndex, showMentions]);

  useEffect(() => {
    const focusInput = () => inputRef.current?.focus();
    window.addEventListener("agenthub:focus-chat-input", focusInput);
    return () => window.removeEventListener("agenthub:focus-chat-input", focusInput);
  }, []);

  const filteredAgents = mentionableAgents.filter((a) =>
    a.name.toLowerCase().includes(mentionFilter.toLowerCase())
  );

  const handleInput = (value: string) => {
    setContent(value);
    const cursorPos = inputRef.current?.selectionStart ?? value.length;
    const beforeCursor = value.slice(0, cursorPos);
    const atMatch = beforeCursor.match(/@([^\s@]*)$/);

    if (atMatch) {
      setMentionFilter(atMatch[1]);
      setMentionPos(atMatch.index!);
      setMentionIndex(0);
      setShowMentions(mentionableAgents.length > 0);
    } else {
      setShowMentions(false);
    }
  };

  const insertMention = (agent: AgentConfig) => {
    const before = content.slice(0, mentionPos);
    const after = content.slice(inputRef.current?.selectionStart ?? mentionPos);
    const newContent = `${before}@${agent.name} ${after}`;
    setContent(newContent);
    setShowMentions(false);
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (showMentions && filteredAgents.length > 0 && e.key === "ArrowDown") {
      e.preventDefault();
      setMentionIndex((i) => (i + 1) % filteredAgents.length);
      return;
    }
    if (showMentions && filteredAgents.length > 0 && e.key === "ArrowUp") {
      e.preventDefault();
      setMentionIndex((i) => (i - 1 + filteredAgents.length) % filteredAgents.length);
      return;
    }
    if (showMentions && filteredAgents.length > 0 && e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      insertMention(filteredAgents[mentionIndex]);
      return;
    }
    if (showMentions && e.key === "Escape") {
      setShowMentions(false);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!content.trim() || disabled) return;
      onSubmit(buildSubmittedContent(content.trim()), extractMentions(content));
      setContent("");
      setCodeReference(null);
    }
  };

  const extractMentions = (text: string): string[] => {
    const mentions: string[] = [];
    const seen = new Set<string>();
    const sortedAgents = [...mentionableAgents].sort((a, b) => b.name.length - a.name.length);
    for (const agent of sortedAgents) {
      const marker = `@${agent.name}`;
      if (text.includes(marker) && !seen.has(agent.id)) {
        mentions.push(agent.id);
        seen.add(agent.id);
      }
    }
    return mentions;
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!content.trim() || disabled) return;
    const mentions = extractMentions(content);
    onSubmit(buildSubmittedContent(content.trim()), mentions);
    setContent("");
    setCodeReference(null);
  };

  const buildSubmittedContent = (text: string) => {
    if (!codeReference) return text;
    const range = codeReference.startLine && codeReference.endLine
      ? `:${codeReference.startLine}-${codeReference.endLine}`
      : "";
    const label = codeReference.filePath ?? codeReference.title ?? "artifact";
    const language = codeReference.language || "text";
    return [
      `[Code reference: ${label}${range}]`,
      `\`\`\`${language}`,
      codeReference.content,
      "```",
      "",
      text,
    ].join("\n");
  };

  return (
    <form onSubmit={handleSubmit} className="agenthub-inputbar relative border-t px-4 py-3">
      {showMentions && (
        <div ref={listRef} className="agenthub-menu absolute bottom-full left-4 z-10 mb-2 max-h-56 w-72 overflow-y-auto rounded-2xl border p-1.5">
          {filteredAgents.length === 0 ? (
            <div className="agenthub-muted px-3 py-2 text-xs">无匹配 Agent</div>
          ) : (
            filteredAgents.map((a, i) => (
              <button
                key={a.id}
                type="button"
                onMouseDown={(e) => { e.preventDefault(); insertMention(a); }}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition ${
                  i === mentionIndex ? "agenthub-nav-active" : "agenthub-nav-idle"
                }`}
              >
                <AgentAvatar agent={a} size="sm" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate">@{a.name}</span>
                  <span className="agenthub-muted mt-0.5 block truncate text-xs">{a.cliTool}</span>
                </span>
              </button>
            ))
          )}
        </div>
      )}
      {replyTarget && (
        <div className="mb-3">
          <ReplyPreview message={replyTarget} onClear={() => setReplyTarget(null)} />
        </div>
      )}
      {codeReference && (
        <div className="mx-auto mb-3 max-w-4xl rounded-2xl border px-3 py-2 text-sm agenthub-soft">
          <div className="flex items-center gap-2">
            <FileCode2 size={15} className="agenthub-accent shrink-0" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <div className="agenthub-strong truncate font-medium">
                {codeReference.filePath ?? codeReference.title ?? "代码片段"}
              </div>
              <div className="agenthub-muted mt-0.5 flex items-center gap-1.5 text-xs">
                <Code2 size={12} aria-hidden="true" />
                <span>{codeReference.content.length} 字符</span>
                {codeReference.startLine && codeReference.endLine && (
                  <span>行 {codeReference.startLine}-{codeReference.endLine}</span>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setCodeReference(null)}
              className="agenthub-icon-button inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
              aria-label="取消代码引用"
              title="取消代码引用"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      )}
      <div className="agenthub-composer mx-auto flex max-w-4xl items-end gap-2 rounded-[24px] border p-2 transition focus-within:border-[color:var(--ah-accent)] focus-within:ring-2 focus-within:ring-[color:var(--ah-accent-soft)]">
        <textarea
          ref={inputRef}
          value={content}
          onChange={(e) => handleInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={busy ? "当前对话正在输出..." : disabled ? "请选择可用 Agent" : "输入消息，@ 提及 Agent"}
          rows={1}
          className="agenthub-textarea max-h-36 min-h-[42px] flex-1 resize-none bg-transparent px-3 py-2.5 text-sm leading-6 focus:outline-none"
        />
        <button
          type="submit"
          disabled={disabled || !content.trim()}
          aria-label="发送"
          title="发送"
          className="inline-flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-full text-white shadow-[0_10px_22px_rgba(91,121,111,0.24)] transition hover:brightness-105 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
          style={{ background: "var(--ah-accent-strong)" }}
        >
          <SendHorizontal size={18} />
        </button>
      </div>
    </form>
  );
}
