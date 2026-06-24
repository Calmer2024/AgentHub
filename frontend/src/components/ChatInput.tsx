import { useState, useRef, useEffect, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";
import { Code2, FileCode2, Loader2, Paperclip, SendHorizontal, X } from "lucide-react";
import type { AgentConfig, Attachment } from "../types";
import { useChatStore } from "../stores/chatStore";
import { ReplyPreview } from "./ReplyPreview";
import { AgentAvatar } from "./AgentAvatar";
import { uploadAttachment } from "../api/client";

interface Props {
  onSubmit: (content: string, mentions: string[], attachmentIds?: string[]) => void;
  disabled?: boolean;
  busy?: boolean;
  mentionableAgents: AgentConfig[];
  mentionLoading?: boolean;
  currentProjectId?: string | null;
  currentSessionId?: string | null;
}

export function ChatInput({
  onSubmit,
  disabled,
  busy,
  mentionableAgents,
  mentionLoading = false,
  currentProjectId,
  currentSessionId,
}: Props) {
  const [content, setContent] = useState("");
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);
  const [mentionPos, setMentionPos] = useState(0);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const replyTarget = useChatStore((state) => state.replyTarget);
  const setReplyTarget = useChatStore((state) => state.setReplyTarget);
  const codeReference = useChatStore((state) => state.codeReference);
  const setCodeReference = useChatStore((state) => state.setCodeReference);

  useEffect(() => {
    if (showMentions && listRef.current) {
      const active = listRef.current.children[mentionIndex] as HTMLElement | undefined;
      if (typeof active?.scrollIntoView === "function") {
        active.scrollIntoView({ block: "nearest" });
      }
    }
  }, [mentionIndex, showMentions]);

  useEffect(() => {
    const focusInput = () => inputRef.current?.focus();
    window.addEventListener("agenthub:focus-chat-input", focusInput);
    return () => window.removeEventListener("agenthub:focus-chat-input", focusInput);
  }, []);

  useEffect(() => {
    const prefillInput = (event: Event) => {
      const detail = (event as CustomEvent<{ content?: string; mode?: "replace" | "append" }>).detail;
      const nextContent = detail?.content?.trim();
      if (!nextContent) return;
      setContent((current) => {
        if (detail?.mode === "append" && current.trim()) {
          return `${current.trimEnd()}\n${nextContent}`;
        }
        return nextContent;
      });
      setShowMentions(false);
      window.requestAnimationFrame(() => {
        const input = inputRef.current;
        if (!input) return;
        input.focus();
        const end = input.value.length;
        input.setSelectionRange(end, end);
      });
    };
    window.addEventListener("agenthub:prefill-chat-input", prefillInput);
    return () => window.removeEventListener("agenthub:prefill-chat-input", prefillInput);
  }, []);

  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 176)}px`;
  }, [content]);

  const filteredAgents = mentionableAgents.filter((a) =>
    a.name.toLowerCase().includes(mentionFilter.toLowerCase())
  );
  const canAttach = Boolean(currentProjectId && currentSessionId);

  const handleInput = (value: string) => {
    setContent(value);
    const cursorPos = inputRef.current?.selectionStart ?? value.length;
    const beforeCursor = value.slice(0, cursorPos);
    const atMatch = beforeCursor.match(/@([^\s@]*)$/);

    if (atMatch) {
      setMentionFilter(atMatch[1]);
      setMentionPos(atMatch.index!);
      setMentionIndex(0);
      setShowMentions(true);
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
      if (!content.trim() || disabled || uploadingAttachment) return;
      const attachmentIds = attachments.map((item) => item.id);
      const submittedContent = buildSubmittedContent(content.trim());
      const mentions = extractMentions(content);
      if (attachmentIds.length > 0) onSubmit(submittedContent, mentions, attachmentIds);
      else onSubmit(submittedContent, mentions);
      setContent("");
      setCodeReference(null);
      setAttachments([]);
      setAttachmentError(null);
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
    if (!content.trim() || disabled || uploadingAttachment) return;
    const mentions = extractMentions(content);
    const attachmentIds = attachments.map((item) => item.id);
    const submittedContent = buildSubmittedContent(content.trim());
    if (attachmentIds.length > 0) onSubmit(submittedContent, mentions, attachmentIds);
    else onSubmit(submittedContent, mentions);
    setContent("");
    setCodeReference(null);
    setAttachments([]);
    setAttachmentError(null);
  };

  const handleFilesSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length === 0) return;
    if (!currentProjectId || !currentSessionId) {
      setAttachmentError("当前会话未绑定 Project，无法添加附件。");
      return;
    }
    setUploadingAttachment(true);
    setAttachmentError(null);
    try {
      const uploaded: Attachment[] = [];
      for (const file of files) {
        uploaded.push(await uploadAttachment({
          projectId: currentProjectId,
          sessionId: currentSessionId,
          file,
        }));
      }
      setAttachments((current) => [...current, ...uploaded]);
    } catch (error) {
      setAttachmentError(error instanceof Error ? error.message : "附件上传失败");
    } finally {
      setUploadingAttachment(false);
    }
  };

  const buildSubmittedContent = (text: string) => {
    if (!codeReference) return text;
    const range = codeReference.startLine && codeReference.endLine
      ? `:${codeReference.startLine}-${codeReference.endLine}`
      : "";
    const label = codeReference.filePath ?? codeReference.title ?? "产物";
    const language = codeReference.language || "text";
    return [
      `[代码引用：${label}${range}]`,
      `\`\`\`${language}`,
      codeReference.content,
      "```",
      "",
      text,
    ].join("\n");
  };

  return (
    <form onSubmit={handleSubmit} className="agenthub-inputbar relative px-4 pb-4 pt-2">
      {showMentions && (
        <div ref={listRef} className="agenthub-menu absolute bottom-full left-4 z-40 mb-2 max-h-56 w-72 overflow-y-auto rounded-2xl border p-1.5">
          {mentionableAgents.length === 0 ? (
            <div className="agenthub-muted px-3 py-2 text-xs">
              {mentionLoading ? "正在加载可提及智能体..." : "暂无可提及智能体"}
            </div>
          ) : filteredAgents.length === 0 ? (
            <div className="agenthub-muted px-3 py-2 text-xs">无匹配智能体</div>
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
        <div className="agenthub-reference-card mx-auto mb-3 max-w-4xl rounded-2xl border px-3 py-2 text-sm">
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
      {(attachments.length > 0 || attachmentError || uploadingAttachment) && (
        <div className="agenthub-soft mx-auto mb-3 max-w-4xl rounded-2xl border px-3 py-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            {uploadingAttachment && (
              <span className="agenthub-muted inline-flex items-center gap-1.5 text-xs">
                <Loader2 size={13} className="animate-spin" aria-hidden="true" />
                正在上传附件
              </span>
            )}
            {attachments.map((item) => (
              <span key={item.id} className="agenthub-code-surface inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-1 text-xs">
                <Paperclip size={12} className="shrink-0" aria-hidden="true" />
                <span className="max-w-48 truncate">{item.filename}</span>
                <button
                  type="button"
                  onClick={() => setAttachments((current) => current.filter((attachment) => attachment.id !== item.id))}
                  className="agenthub-icon-button inline-flex h-5 w-5 items-center justify-center rounded-full"
                  aria-label={`移除附件 ${item.filename}`}
                  title="移除附件"
                >
                  <X size={11} aria-hidden="true" />
                </button>
              </span>
            ))}
            {attachmentError && <span className="agenthub-status-error rounded-full px-2 py-1 text-xs">{attachmentError}</span>}
          </div>
        </div>
      )}
      <div className="agenthub-chat-composer agenthub-focus-ring mx-auto flex max-w-4xl items-end gap-2 rounded-[24px] border p-2">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFilesSelected}
        />
        <button
          type="button"
          disabled={disabled || uploadingAttachment || !canAttach}
          onClick={() => fileInputRef.current?.click()}
          aria-label="添加附件"
          title={canAttach ? "添加附件" : "当前会话无法添加附件"}
          className="agenthub-icon-button inline-flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-full transition disabled:cursor-not-allowed disabled:opacity-40"
        >
          {uploadingAttachment ? <Loader2 size={17} className="animate-spin" aria-hidden="true" /> : <Paperclip size={17} aria-hidden="true" />}
        </button>
        <textarea
          ref={inputRef}
          value={content}
          onChange={(e) => handleInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={busy ? "当前对话正在输出..." : disabled ? "请选择可用智能体" : "输入消息，@ 提及智能体"}
          rows={1}
          className="agenthub-textarea max-h-44 min-h-[42px] flex-1 resize-none overflow-y-auto bg-transparent px-3 py-2.5 text-sm leading-6 focus:outline-none"
        />
        <button
          type="submit"
          disabled={disabled || uploadingAttachment || !content.trim()}
          aria-label="发送"
          title="发送"
          className="agenthub-primary-button inline-flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-full transition disabled:cursor-not-allowed disabled:opacity-40"
        >
          <SendHorizontal size={18} />
        </button>
      </div>
    </form>
  );
}
