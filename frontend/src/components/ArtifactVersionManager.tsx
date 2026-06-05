import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, GitBranch, History, Loader2, RotateCcw, X } from "lucide-react";
import type { Artifact, ArtifactVersion } from "../types";
import { fetchArtifactVersions, restoreArtifactVersion } from "../api/client";

interface Props {
  artifact: Artifact;
  open: boolean;
  onClose: () => void;
  onChanged?: () => void;
}

export function ArtifactVersionManager({ artifact, open, onClose, onChanged }: Props) {
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setLoading(true);
    setError(null);
    fetchArtifactVersions(artifact.id)
      .then((items) => {
        if (!alive) return;
        const ordered = [...items].sort((left, right) => left.version - right.version);
        setVersions(ordered);
        setSelectedVersion(ordered[ordered.length - 1]?.version ?? artifact.version);
      })
      .catch(() => {
        if (alive) setError("版本加载失败");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => { alive = false; };
  }, [artifact.id, artifact.version, open]);

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

  const latest = versions[versions.length - 1] ?? null;
  const previous = versions.length >= 2 ? versions[versions.length - 2] : null;
  const selected = useMemo(() => (
    versions.find((item) => item.version === selectedVersion) ?? latest
  ), [latest, selectedVersion, versions]);

  const restore = async (version: number) => {
    setRestoring(true);
    setError(null);
    try {
      await restoreArtifactVersion(artifact.id, version);
      await onChanged?.();
      onClose();
    } catch {
      setError("版本恢复失败");
    } finally {
      setRestoring(false);
    }
  };

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/72 p-3 md:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={`版本管理：${artifact.title || artifact.filePath || "产物"}`}
      onClick={onClose}
    >
      <div
        className="flex max-h-[92dvh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-[#30363d] bg-[#0d1117] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#30363d] bg-[#161b22] px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] text-[#8b949e]">
              <History size={15} aria-hidden="true" />
              <span>版本管理</span>
              <span className="font-mono">v{latest?.version ?? artifact.version}</span>
            </div>
            <h3 className="mt-1 truncate text-base font-semibold text-[#f0f6fc]">{artifact.title || artifact.filePath || "产物"}</h3>
            {artifact.filePath && <p className="mt-0.5 truncate font-mono text-xs text-[#7d8590]">{artifact.filePath}</p>}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!previous || restoring}
              onClick={() => previous && restore(previous.version)}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#30363d] bg-[#0d1117] px-3 text-sm text-[#c9d1d9] hover:bg-[#21262d] disabled:cursor-not-allowed disabled:text-[#6e7681]"
            >
              {restoring ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <RotateCcw size={14} aria-hidden="true" />}
              撤销本次修改
            </button>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[#30363d] text-[#8b949e] hover:bg-[#21262d] hover:text-[#f0f6fc]"
              aria-label="关闭版本管理"
              title="关闭"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {error && (
          <div className="border-b border-amber-400/20 bg-amber-400/10 px-4 py-2 text-xs text-amber-100">
            {error}
          </div>
        )}

        <div className="grid min-h-0 flex-1 overflow-hidden md:grid-cols-[260px_minmax(0,1fr)]">
          <div className="min-h-0 overflow-y-auto border-b border-[#30363d] bg-[#111820] p-3 md:border-b-0 md:border-r">
            {loading ? (
              <div className="flex items-center gap-2 rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#c9d1d9]">
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                正在加载版本
              </div>
            ) : versions.length === 0 ? (
              <div className="rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#8b949e]">
                暂无版本记录
              </div>
            ) : (
              <div className="space-y-1.5">
                {versions.map((version) => {
                  const active = selected?.version === version.version;
                  const isLatest = latest?.version === version.version;
                  return (
                    <button
                      key={version.id}
                      type="button"
                      onClick={() => setSelectedVersion(version.version)}
                      className={`flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition ${
                        active
                          ? "border-sky-300/35 bg-sky-300/10 text-sky-100"
                          : "border-[#30363d] bg-[#0d1117] text-[#c9d1d9] hover:bg-[#161b22]"
                      }`}
                    >
                      <GitBranch size={14} className="shrink-0" aria-hidden="true" />
                      <span className="min-w-0 flex-1">
                        <span className="block font-mono">v{version.version}</span>
                        <span className="mt-0.5 block truncate text-[11px] text-[#7d8590]">
                          {isLatest ? "当前版本" : version.createdAt || "历史版本"}
                        </span>
                      </span>
                      {active && <CheckCircle2 size={14} className="text-sky-200" aria-hidden="true" />}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="flex min-h-0 flex-col overflow-hidden">
            <div className="flex items-center justify-between gap-3 border-b border-[#30363d] bg-[#111820] px-4 py-2">
              <div className="font-mono text-xs text-[#8b949e]">
                {selected ? `v${selected.version}` : "未选择版本"}
              </div>
              <button
                type="button"
                disabled={!selected || selected.version === latest?.version || restoring}
                onClick={() => selected && restore(selected.version)}
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-[#2f7cf6] px-3 text-sm font-medium text-white hover:bg-[#3d88ff] disabled:cursor-not-allowed disabled:bg-[#30363d] disabled:text-[#8b949e]"
              >
                {restoring ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <RotateCcw size={14} aria-hidden="true" />}
                跳转到此版本
              </button>
            </div>
            <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap bg-[#0d1117] p-4 font-mono text-[12px] leading-6 text-[#d6deeb]">
              {selected?.content ?? ""}
            </pre>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
