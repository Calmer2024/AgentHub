import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { FileCode2, FileText, Files, Globe2, LayoutPanelTop, Search, X } from "lucide-react";
import type { Artifact } from "../types";
import { ArtifactCard } from "./ArtifactCard";

interface Props {
  open: boolean;
  artifacts: Artifact[];
  onClose: () => void;
  onChanged?: () => void;
}

function typeIcon(type: Artifact["type"]) {
  const props = { size: 15, "aria-hidden": true };
  if (type === "web_preview") return <Globe2 {...props} />;
  if (type === "code_diff") return <FileCode2 {...props} />;
  if (type === "file_tree") return <Files {...props} />;
  return <FileText {...props} />;
}

function typeLabel(type: Artifact["type"]) {
  if (type === "web_preview") return "网页";
  if (type === "code_diff") return "Diff";
  if (type === "file_tree") return "文件";
  return "文档";
}

export function SessionArtifactManager({ open, artifacts, onClose, onChanged }: Props) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(artifacts[0]?.id ?? null);

  const filtered = useMemo(() => {
    const clean = query.trim().toLowerCase();
    if (!clean) return artifacts;
    return artifacts.filter((artifact) => [
      artifact.title,
      artifact.filePath,
      artifact.type,
      artifact.source,
    ].filter(Boolean).some((value) => String(value).toLowerCase().includes(clean)));
  }, [artifacts, query]);

  const selected = filtered.find((artifact) => artifact.id === selectedId)
    ?? filtered[0]
    ?? null;

  useEffect(() => {
    if (!open) return;
    if (selectedId && filtered.some((artifact) => artifact.id === selectedId)) return;
    setSelectedId(filtered[0]?.id ?? null);
  }, [filtered, open, selectedId]);

  useEffect(() => {
    if (!open || typeof document === "undefined") return;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, open]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[1050] flex items-center justify-center bg-black/72 p-3 md:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="会话文件与产物"
      onClick={onClose}
    >
      <div
        className="flex h-[90dvh] w-full max-w-6xl flex-col overflow-hidden rounded-lg border border-[#30363d] bg-[#0d1117] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#30363d] bg-[#161b22] px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] text-[#8b949e]">
              <LayoutPanelTop size={15} aria-hidden="true" />
              <span>会话产物</span>
              <span>{artifacts.length} 个</span>
            </div>
            <h3 className="mt-1 truncate text-base font-semibold text-[#f0f6fc]">文件、资产与变更</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[#30363d] text-[#8b949e] hover:bg-[#21262d] hover:text-[#f0f6fc]"
            aria-label="关闭会话产物"
            title="关闭"
          >
            <X size={15} />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 overflow-hidden lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="flex min-h-0 flex-col border-b border-[#30363d] bg-[#111820] lg:border-b-0 lg:border-r">
            <div className="border-b border-[#30363d] p-3">
              <label className="flex h-9 items-center gap-2 rounded-md border border-[#30363d] bg-[#0d1117] px-2.5 text-sm text-[#c9d1d9] focus-within:border-sky-400/60">
                <Search size={14} className="text-[#8b949e]" aria-hidden="true" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索文件或产物"
                  className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[#6e7681]"
                />
              </label>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {filtered.length === 0 ? (
                <div className="rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-6 text-center text-sm text-[#8b949e]">
                  暂无匹配产物
                </div>
              ) : (
                <div className="space-y-1.5">
                  {filtered.map((artifact) => {
                    const active = selected?.id === artifact.id;
                    return (
                      <button
                        key={artifact.id}
                        type="button"
                        onClick={() => setSelectedId(artifact.id)}
                        className={`flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left transition ${
                          active
                            ? "border-sky-300/35 bg-sky-300/10 text-sky-100"
                            : "border-[#30363d] bg-[#0d1117] text-[#c9d1d9] hover:bg-[#161b22]"
                        }`}
                      >
                        <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-white/10 bg-white/[0.04]">
                          {typeIcon(artifact.type)}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">
                            {artifact.title || artifact.filePath || "产物"}
                          </span>
                          <span className="mt-0.5 block truncate text-[11px] text-[#7d8590]">
                            {typeLabel(artifact.type)} · v{artifact.version}
                            {artifact.filePath ? ` · ${artifact.filePath}` : ""}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </aside>

          <main className="min-h-0 overflow-y-auto bg-[#0d1117] p-4">
            {selected ? (
              <ArtifactCard artifact={selected} onChanged={onChanged} />
            ) : (
              <div className="flex h-full items-center justify-center rounded-md border border-[#30363d] bg-[#111820] text-sm text-[#8b949e]">
                当前会话还没有产物
              </div>
            )}
          </main>
        </div>
      </div>
    </div>,
    document.body,
  );
}
