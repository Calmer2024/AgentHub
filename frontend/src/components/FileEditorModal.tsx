import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Code2, FileCode2, Loader2, MessageSquarePlus, Save, X } from "lucide-react";
import type { ReactCodeMirrorRef } from "@uiw/react-codemirror";
import type { ViewUpdate } from "@codemirror/view";
import type { Artifact, CodeReference } from "../types";
import {
  readProjectFile,
  saveArtifactContent,
  writeProjectFile,
} from "../api/client";
import { useChatStore } from "../stores/chatStore";
import { useToastStore } from "../stores/toastStore";

const CodeMirrorFileEditor = lazy(() => import("./CodeMirrorFileEditor").then((module) => ({
  default: module.CodeMirrorFileEditor,
})));

interface Props {
  open: boolean;
  artifact?: Artifact | null;
  projectId?: string | null;
  filePath?: string | null;
  title?: string | null;
  initialContent?: string | null;
  onClose: () => void;
  onSaved?: () => void;
}

function languageFromPath(path?: string | null) {
  if (!path) return "text";
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext === "ts" || ext === "tsx") return "tsx";
  if (ext === "js" || ext === "jsx") return "jsx";
  if (ext === "html" || ext === "htm") return "html";
  if (ext === "css") return "css";
  if (ext === "json") return "json";
  if (ext === "py") return "python";
  if (ext === "md") return "markdown";
  return ext || "text";
}

function lineRange(content: string, start: number, end: number) {
  const prefix = content.slice(0, start);
  const selection = content.slice(start, end);
  const startLine = prefix.split("\n").length;
  const endLine = startLine + Math.max(selection.split("\n").length - 1, 0);
  return { startLine, endLine };
}

export function FileEditorModal({
  open,
  artifact = null,
  projectId,
  filePath,
  title,
  initialContent,
  onClose,
  onSaved,
}: Props) {
  const editorRef = useRef<ReactCodeMirrorRef | null>(null);
  const setCodeReference = useChatStore((state) => state.setCodeReference);
  const pushToast = useToastStore((state) => state.pushToast);
  const [content, setContent] = useState(initialContent ?? artifact?.content ?? "");
  const [original, setOriginal] = useState(initialContent ?? artifact?.content ?? "");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [selection, setSelection] = useState<{ text: string; start: number; end: number } | null>(null);
  const [cursor, setCursor] = useState({ line: 1, column: 1 });

  const resolvedProjectId = projectId ?? artifact?.projectId ?? null;
  const resolvedFilePath = filePath ?? artifact?.filePath ?? null;
  const label = title ?? resolvedFilePath ?? artifact?.title ?? "代码文件";
  const language = languageFromPath(resolvedFilePath ?? artifact?.title ?? null);
  const dirty = content !== original;

  useEffect(() => {
    if (!open) return;
    setError(null);
    setSaved(false);
    setSelection(null);
    const fallback = initialContent ?? artifact?.content ?? "";
    if (resolvedProjectId && resolvedFilePath) {
      let alive = true;
      setLoading(true);
      readProjectFile(resolvedProjectId, resolvedFilePath)
        .then((file) => {
          if (!alive) return;
          setContent(file.content);
          setOriginal(file.content);
        })
        .catch(() => {
          if (!alive) return;
          setContent(fallback);
          setOriginal(fallback);
          setError("无法读取工作区文件，已显示产物快照");
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
      return () => { alive = false; };
    }
    setContent(fallback);
    setOriginal(fallback);
  }, [artifact?.content, initialContent, open, resolvedFilePath, resolvedProjectId]);

  useEffect(() => {
    if (!open || typeof document === "undefined") return;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    window.setTimeout(() => editorRef.current?.view?.focus(), 50);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, open]);

  const stats = useMemo(() => {
    const lines = content.length === 0 ? 0 : content.split("\n").length;
    return { lines, chars: content.length };
  }, [content]);

  const captureEditorState = (update: ViewUpdate) => {
    const range = update.state.selection.main;
    const selected = update.state.doc.sliceString(range.from, range.to);
    const line = update.state.doc.lineAt(range.head);
    setCursor({
      line: line.number,
      column: range.head - line.from + 1,
    });
    setSelection(selected.trim()
      ? { text: selected, start: range.from, end: range.to }
      : null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      if (artifact && artifact.type !== "file_tree") {
        await saveArtifactContent(artifact.id, content, artifact.title);
      } else if (resolvedProjectId && resolvedFilePath) {
        await writeProjectFile(resolvedProjectId, resolvedFilePath, content);
      } else {
        throw new Error("missing file target");
      }
      setOriginal(content);
      setSaved(true);
      onSaved?.();
      pushToast({ kind: "success", title: "文件已保存" });
    } catch {
      setError("保存失败，请检查文件权限或产物状态");
      pushToast({ kind: "error", title: "保存失败", description: "请检查文件权限或产物状态" });
    } finally {
      setSaving(false);
    }
  };

  const addToChat = () => {
    if (!selection) return;
    const range = lineRange(content, selection.start, selection.end);
    const reference: CodeReference = {
      artifactId: artifact?.id ?? null,
      projectId: resolvedProjectId,
      filePath: resolvedFilePath,
      title: label,
      language,
      startLine: range.startLine,
      endLine: range.endLine,
      content: selection.text,
    };
    setCodeReference(reference);
    onClose();
    window.setTimeout(() => {
      window.dispatchEvent(new CustomEvent("agenthub:focus-chat-input"));
    }, 40);
  };

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="agenthub-backdrop fixed inset-0 z-[1100] flex items-center justify-center p-3 md:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={`编辑文件：${label}`}
      onClick={onClose}
    >
      <div
        className="agenthub-modal agenthub-modal-pop flex h-[88dvh] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="agenthub-header flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div className="min-w-0">
            <div className="agenthub-muted flex items-center gap-2 text-[11px]">
              <FileCode2 size={15} aria-hidden="true" />
              <span>文件编辑器</span>
              <span className="agenthub-faint font-mono">{stats.lines} 行</span>
              <span className="agenthub-faint font-mono">{stats.chars} 字符</span>
            </div>
            <h3 className="agenthub-strong mt-1 truncate text-base font-semibold">{label}</h3>
          </div>
          <div className="flex items-center gap-2">
            {saved && (
              <span className="agenthub-status-success inline-flex h-8 items-center gap-1.5 rounded-full border px-2 text-xs">
                <Check size={14} aria-hidden="true" />
                已保存
              </span>
            )}
            <button
              type="button"
              onClick={save}
              disabled={saving || loading || !dirty}
              className="agenthub-primary-button inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Save size={14} aria-hidden="true" />}
              保存
            </button>
            <button
              type="button"
              onClick={onClose}
              className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
              aria-label="关闭文件编辑器"
              title="关闭"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {error && (
          <div className="agenthub-status-warning border-b px-4 py-2 text-xs">
            {error}
          </div>
        )}

        <div className="agenthub-chat relative min-h-0 flex-1 p-3">
          {selection && (
            <button
              type="button"
              onClick={addToChat}
              className="absolute right-5 top-5 z-10 inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-xs font-medium shadow-xl"
              style={{
                borderColor: "var(--ah-accent)",
                background: "var(--ah-accent-soft)",
                color: "var(--ah-text-strong)",
              }}
            >
              <MessageSquarePlus size={14} aria-hidden="true" />
              添加到对话
            </button>
          )}
          {loading && (
            <div className="agenthub-card absolute inset-3 z-10 flex items-center justify-center rounded-md text-sm">
              <Loader2 size={16} className="mr-2 animate-spin" aria-hidden="true" />
              正在读取文件
            </div>
          )}
          <div className="agenthub-card flex h-full min-h-0 overflow-hidden rounded-md border shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] focus-within:border-[color:var(--ah-accent)] focus-within:ring-2 focus-within:ring-[color:var(--ah-accent-soft)]">
            <div className="agenthub-sidebar agenthub-faint hidden w-11 shrink-0 border-r pt-3 text-center font-mono text-[10px] md:block">
              编辑器
            </div>
            <Suspense
              fallback={(
                <div className="agenthub-muted flex min-h-0 min-w-0 flex-1 items-center justify-center text-sm">
                  <Loader2 size={15} className="mr-2 animate-spin" aria-hidden="true" />
                  正在加载编辑器
                </div>
              )}
            >
              <CodeMirrorFileEditor
                editorRef={editorRef}
                value={content}
                language={language}
                onChange={(value) => {
                  setContent(value);
                  setSaved(false);
                }}
                onUpdate={captureEditorState}
              />
            </Suspense>
          </div>
        </div>

        <div className="agenthub-header flex items-center justify-between gap-3 border-t px-4 py-2 text-[11px] agenthub-muted">
          <span className="inline-flex items-center gap-1.5">
            <Code2 size={13} aria-hidden="true" />
            {selection ? `已选择 ${selection.text.length} 字符` : "选择代码后可添加到对话"}
          </span>
          <span className="flex min-w-0 items-center gap-3 truncate font-mono">
            <span>{language.toUpperCase()}</span>
            <span>第 {cursor.line} 行，第 {cursor.column} 列</span>
            <span>{stats.chars} 字符</span>
            {dirty && <span className="text-[color:var(--ah-warning)]">已修改</span>}
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
