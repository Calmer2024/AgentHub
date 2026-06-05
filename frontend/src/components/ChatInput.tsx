import { useState, useRef, useEffect, type FormEvent, type KeyboardEvent } from "react";
import { SendHorizontal } from "lucide-react";
import type { AgentConfig } from "../types";
import { useChatStore } from "../stores/chatStore";
import { ReplyPreview } from "./ReplyPreview";
import { AgentAvatar } from "./AgentAvatar";

interface Props {
  onSubmit: (content: string, mentions: string[]) => void;
  disabled?: boolean;
  mentionableAgents: AgentConfig[];
}

export function ChatInput({ onSubmit, disabled, mentionableAgents }: Props) {
  const [content, setContent] = useState("");
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);
  const [mentionPos, setMentionPos] = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const { replyTarget, setReplyTarget } = useChatStore();

  useEffect(() => {
    if (showMentions && listRef.current) {
      const active = listRef.current.children[mentionIndex] as HTMLElement | undefined;
      active?.scrollIntoView({ block: "nearest" });
    }
  }, [mentionIndex, showMentions]);

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
      onSubmit(content.trim(), extractMentions(content));
      setContent("");
    }
  };

  const extractMentions = (text: string): string[] => {
    const mentions: string[] = [];
    const regex = /@(\S+)/g;
    let match;
    while ((match = regex.exec(text)) !== null) {
      const agent = mentionableAgents.find((a) => a.name === match![1]);
      if (agent) mentions.push(agent.id);
    }
    return mentions;
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!content.trim() || disabled) return;
    const mentions = extractMentions(content);
    onSubmit(content.trim(), mentions);
    setContent("");
  };

  return (
    <form onSubmit={handleSubmit} className="relative border-t border-white/[0.08] bg-[#17212b] px-4 py-3">
      {showMentions && (
        <div ref={listRef} className="absolute bottom-full left-4 z-10 mb-2 max-h-56 w-72 overflow-y-auto rounded-2xl border border-white/10 bg-[#242528]/95 p-1.5 shadow-2xl backdrop-blur">
          {filteredAgents.length === 0 ? (
            <div className="px-3 py-2 text-xs text-[#8f8f98]">无匹配 Agent</div>
          ) : (
            filteredAgents.map((a, i) => (
              <button
                key={a.id}
                type="button"
                onMouseDown={(e) => { e.preventDefault(); insertMention(a); }}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm ${
                  i === mentionIndex ? "bg-white/10 text-white" : "text-[#d8d8df] hover:bg-white/[0.08]"
                }`}
              >
                <AgentAvatar agent={a} size="sm" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate">@{a.name}</span>
                  <span className="mt-0.5 block truncate text-xs text-[#8f8f98]">{a.cliTool}</span>
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
      <div className="mx-auto flex max-w-4xl items-end gap-2 rounded-[24px] border border-white/10 bg-[#0f141a] p-2 shadow-[0_18px_48px_rgba(0,0,0,0.28)] transition focus-within:border-sky-400/45 focus-within:ring-2 focus-within:ring-sky-400/15">
        <textarea
          ref={inputRef}
          value={content}
          onChange={(e) => handleInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={disabled ? "AI 正在回复..." : "输入消息，@ 提及 Agent"}
          rows={1}
          className="max-h-36 min-h-[42px] flex-1 resize-none bg-transparent px-3 py-2.5 text-sm leading-6 text-[#ececf1] placeholder:text-[#8f8f98] focus:outline-none"
        />
        <button
          type="submit"
          disabled={disabled || !content.trim()}
          aria-label="发送"
          title="发送"
          className="inline-flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-full bg-[#2f7cf6] text-white shadow-[0_10px_22px_rgba(47,124,246,0.28)] transition hover:bg-[#3d88ff] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
        >
          <SendHorizontal size={18} />
        </button>
      </div>
    </form>
  );
}
