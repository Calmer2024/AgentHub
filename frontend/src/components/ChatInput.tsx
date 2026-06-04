import { useState, useRef, useEffect, type FormEvent, type KeyboardEvent } from "react";
import type { AgentConfig } from "../types";
import { useChatStore } from "../stores/chatStore";
import { ReplyPreview } from "./ReplyPreview";

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
  const inputRef = useRef<HTMLInputElement>(null);
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

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!showMentions || filteredAgents.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setMentionIndex((i) => (i + 1) % filteredAgents.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setMentionIndex((i) => (i - 1 + filteredAgents.length) % filteredAgents.length);
    } else if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      insertMention(filteredAgents[mentionIndex]);
    } else if (e.key === "Escape") {
      setShowMentions(false);
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
    <form onSubmit={handleSubmit} className="p-4 border-t border-white/[0.08] bg-[#171717] relative">
      {showMentions && (
        <div ref={listRef} className="absolute bottom-full left-4 mb-1 w-64 max-h-40 overflow-y-auto bg-[#2b2b2f] border border-white/10 rounded-xl shadow-lg z-10">
          {filteredAgents.length === 0 ? (
            <div className="px-3 py-2 text-xs text-[#8f8f98]">无匹配 Agent</div>
          ) : (
            filteredAgents.map((a, i) => (
              <button
                key={a.id}
                type="button"
                onMouseDown={(e) => { e.preventDefault(); insertMention(a); }}
                className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 ${
                  i === mentionIndex ? "bg-white/10 text-white" : "text-[#d8d8df] hover:bg-white/[0.08]"
                }`}
              >
                <span className="truncate">@{a.name}</span>
                <span className="text-xs text-[#8f8f98] ml-auto">{a.provider}</span>
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
      <div className="flex gap-3 rounded-2xl bg-[#2b2b2f] border border-white/10 p-2 shadow-2xl">
        <input
          ref={inputRef}
          type="text"
          value={content}
          onChange={(e) => handleInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={disabled ? "AI 正在回复..." : "输入消息...（输入 @ 提及 Agent）"}
          className="flex-1 px-3 py-2 bg-transparent text-[#ececf1] placeholder:text-[#8f8f98] focus:outline-none"
        />
        <button
          type="submit"
          disabled={disabled || !content.trim()}
          className="px-5 py-2 bg-[#ececf1] text-[#171717] rounded-xl hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed font-medium"
        >
          发送
        </button>
      </div>
    </form>
  );
}
