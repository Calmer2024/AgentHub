import { useEffect, useMemo, useState } from "react";
import { FileCode2, FileImage, FileText, Files, Globe2, LayoutPanelTop, Search, X } from "lucide-react";
import { createPortal } from "react-dom";
import type { Artifact } from "../types";
import { ArtifactCard } from "./ArtifactCard";
import { getArtifactPreviewInfo } from "../utils/artifactPreview";

interface Props {
  open: boolean;
  artifacts: Artifact[];
  onClose: () => void;
  onChanged?: () => void;
}

function typeIcon(artifact: Artifact) {
  const props = { size: 15, "aria-hidden": true };
  const preview = getArtifactPreviewInfo(artifact);
  if (preview.kind === "html") return <Globe2 {...props} />;
  if (preview.kind === "diff") return <FileCode2 {...props} />;
  if (preview.kind === "file_tree") return <Files {...props} />;
  if (preview.kind === "image") return <FileImage {...props} />;
  return <FileText {...props} />;
}

function typeLabel(artifact: Artifact) {
  return getArtifactPreviewInfo(artifact).shortLabel;
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
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, open]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="agenthub-backdrop fixed inset-0 z-[1250] flex items-center justify-center p-3 md:p-5"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="agenthub-artifact-modal agenthub-modal-pop flex min-h-0 w-full max-w-6xl flex-col overflow-hidden rounded-[24px] border"
        role="dialog"
        aria-modal="true"
        aria-label="会话文件与产物"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="agenthub-header flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3 md:px-5">
          <div className="min-w-0">
            <div className="agenthub-muted flex items-center gap-2 text-[11px]">
              <LayoutPanelTop size={15} aria-hidden="true" />
              <span>会话产物</span>
              <span>{artifacts.length} 个</span>
            </div>
            <h3 className="agenthub-strong mt-1 truncate text-base font-semibold">文件、资产与变更</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
            aria-label="关闭会话产物"
            title="关闭"
          >
            <X size={15} />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 overflow-hidden lg:grid-cols-[220px_minmax(0,1fr)]">
          <aside className="agenthub-artifact-index flex min-h-0 flex-col border-b lg:border-b-0 lg:border-r">
            <div className="border-b p-3" style={{ borderColor: "var(--ah-border)" }}>
              <label className="agenthub-composer agenthub-focus-ring flex h-9 items-center gap-2 rounded-full border px-2.5 text-sm">
                <Search size={14} className="agenthub-muted" aria-hidden="true" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索文件"
                  className="agenthub-textarea min-w-0 flex-1 bg-transparent text-sm outline-none"
                />
              </label>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {filtered.length === 0 ? (
                <div className="agenthub-soft rounded-md border px-3 py-6 text-center text-sm agenthub-muted">
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
                        className={`flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left transition ${
                          active
                            ? "agenthub-nav-active border-[color:var(--ah-accent)]"
                            : "agenthub-nav-idle border-[color:var(--ah-border)]"
                        }`}
                      >
                        <span className="agenthub-soft inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border">
                          {typeIcon(artifact)}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">
                            {artifact.title || artifact.filePath || "产物"}
                          </span>
                          <span className="agenthub-faint mt-0.5 block truncate text-[11px]">
                            {typeLabel(artifact)} · v{artifact.version}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </aside>

          <main className="agenthub-artifact-preview min-h-0 overflow-y-auto p-3">
            {selected ? (
              <ArtifactCard artifact={selected} onChanged={onChanged} />
            ) : (
              <div className="agenthub-soft flex h-full items-center justify-center rounded-md border text-sm agenthub-muted">
                当前会话还没有产物
              </div>
            )}
          </main>
        </div>
      </section>
    </div>,
    document.body,
  );
}
