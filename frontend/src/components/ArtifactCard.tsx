import { useEffect, useMemo, useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Artifact, ArtifactDiff, ArtifactEditResult, ArtifactVersion } from "../types";
import {
  createProjectPreview,
  editArtifact,
  fetchArtifactDiff,
  fetchArtifactVersions,
} from "../api/client";
import { Check, ExternalLink, FileCode2, FileText, Globe2, Loader2, Maximize2, X } from "lucide-react";
import { CodeSelector } from "./CodeSelector";
import { DiffViewer } from "./DiffViewer";
import { VersionHistory } from "./VersionHistory";

interface Props {
  artifact: Artifact;
  onChanged?: () => void;
}

function artifactLabel(artifact: Artifact) {
  if (artifact.type === "code_diff") return "代码";
  if (artifact.type === "web_preview") return "网页";
  return "文档";
}

function artifactIcon(artifact: Artifact) {
  if (artifact.type === "code_diff") return <FileCode2 size={15} className="shrink-0 text-slate-500" />;
  if (artifact.type === "web_preview") return <Globe2 size={15} className="shrink-0 text-slate-500" />;
  return <FileText size={15} className="shrink-0 text-slate-500" />;
}

function statusDot(status: Artifact["status"]) {
  if (status === "rendering") return "bg-yellow-400 animate-pulse";
  if (status === "error") return "bg-red-500";
  return "bg-green-500";
}

export function ArtifactCard({ artifact, onChanged }: Props) {
  const [fullscreen, setFullscreen] = useState(false);
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [fromVersion, setFromVersion] = useState(artifact.version > 1 ? artifact.version - 1 : 1);
  const [toVersion, setToVersion] = useState(artifact.version);
  const [diff, setDiff] = useState<ArtifactDiff | null>(null);
  const [viewMode, setViewMode] = useState<"split" | "unified">("split");
  const [selectedVersion, setSelectedVersion] = useState(artifact.version);
  const [editResult, setEditResult] = useState<ArtifactEditResult | null>(null);
  const [selection, setSelection] = useState("");
  const [instruction, setInstruction] = useState("");
  const [editType, setEditType] = useState<"replace" | "insert_after" | "insert_before" | "delete">("replace");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchArtifactVersions(artifact.id)
      .then((items) => {
        if (!alive) return;
        setVersions(items);
        const latest = items[items.length - 1]?.version ?? artifact.version;
        setSelectedVersion(latest);
        setToVersion(latest);
        setFromVersion(latest > 1 ? latest - 1 : 1);
      })
      .catch(() => {
        if (alive) setVersions([]);
      });
    return () => { alive = false; };
  }, [artifact.id, artifact.version]);

  useEffect(() => {
    if (versions.length < 2 || fromVersion === toVersion) {
      setDiff(null);
      return;
    }
    let alive = true;
    fetchArtifactDiff(artifact.id, fromVersion, toVersion)
      .then((result) => { if (alive) setDiff(result); })
      .catch(() => { if (alive) setDiff(null); });
    return () => { alive = false; };
  }, [artifact.id, versions.length, fromVersion, toVersion]);

  useEffect(() => {
    if (artifact.type !== "web_preview" || !artifact.projectId) {
      setPreviewUrl(null);
      setPreviewError(null);
      setPreviewLoading(false);
      return;
    }
    let alive = true;
    setPreviewLoading(true);
    setPreviewError(null);
    createProjectPreview(artifact.projectId, artifact.filePath)
      .then((result) => {
        if (!alive) return;
        setPreviewUrl(result.previewUrl);
      })
      .catch((err) => {
        if (!alive) return;
        setPreviewUrl(null);
        setPreviewError(err instanceof Error ? err.message : "预览加载失败");
      })
      .finally(() => {
        if (alive) setPreviewLoading(false);
      });
    return () => { alive = false; };
  }, [artifact.filePath, artifact.projectId, artifact.type]);

  const displayedContent = useMemo(() => {
    return versions.find((version) => version.version === selectedVersion)?.content ?? artifact.content;
  }, [artifact.content, selectedVersion, versions]);

  const iframeProps = previewUrl
    ? { src: previewUrl }
    : { srcDoc: displayedContent };

  const openExternalPreview = () => {
    if (previewUrl) window.open(previewUrl, "_blank", "noopener,noreferrer");
  };

  const previewEdit = async (
    selectedText: string,
    editInstruction: string,
    nextEditType: typeof editType,
  ) => {
    setLoading(true);
    setError(null);
    setSelection(selectedText);
    setInstruction(editInstruction);
    setEditType(nextEditType);
    try {
      const result = await editArtifact(artifact.id, {
        selection: selectedText,
        instruction: editInstruction,
        editType: nextEditType,
      });
      setEditResult(result);
      setDiff(result.diff);
      setFromVersion(result.diff.fromVersion);
      setToVersion(result.diff.toVersion);
    } catch {
      setError("编辑预览生成失败");
    } finally {
      setLoading(false);
    }
  };

  const confirmEdit = async () => {
    if (!editResult) return;
    setLoading(true);
    setError(null);
    try {
      await editArtifact(artifact.id, {
        selection,
        instruction,
        editType,
        apply: true,
        proposedContent: editResult.proposedContent,
      });
      setEditResult(null);
      await onChanged?.();
    } catch {
      setError("应用编辑失败");
    } finally {
      setLoading(false);
    }
  };

  const rejectEdit = () => {
    setEditResult(null);
    setError(null);
    if (versions.length >= 2 && fromVersion !== toVersion) return;
    setDiff(null);
  };

  const preview = (
    <div className="p-3 max-h-48 overflow-auto">
      {artifact.type === "code_diff" ? (
        <SyntaxHighlighter
          language="python"
          style={oneDark}
          customStyle={{ borderRadius: "0.5rem", fontSize: "0.75rem", margin: 0 }}
          wrapLongLines
        >
          {artifact.content}
        </SyntaxHighlighter>
      ) : artifact.type === "web_preview" ? (
        <div className="relative h-40 overflow-hidden rounded bg-slate-100">
          {previewLoading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/85 text-xs text-slate-500">
              <Loader2 size={14} className="mr-2 animate-spin" />
              正在加载本机预览
            </div>
          )}
          {previewError && (
            <div className="absolute left-2 top-2 z-10 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-700">
              已回退到内容预览
            </div>
          )}
          <iframe {...iframeProps} sandbox="allow-scripts" className="h-full w-full border-0" title="preview" />
        </div>
      ) : (
        <pre className="text-xs whitespace-pre-wrap">{artifact.content}</pre>
      )}
    </div>
  );

  return (
    <>
      <div className="mb-3 overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-3 py-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {artifactIcon(artifact)}
              <span className="text-xs font-medium text-slate-700">{artifactLabel(artifact)}</span>
              <span className={`h-2 w-2 rounded-full ${statusDot(artifact.status)}`} />
              <span className="text-xs text-slate-400">v{artifact.version}</span>
            </div>
            <div className="mt-0.5 truncate text-sm font-medium text-slate-900">
              {artifact.title || "产物预览"}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setFullscreen(true)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
          >
            <Maximize2 size={13} />
            打开
          </button>
        </div>
        {preview}
      </div>

      {fullscreen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3 md:p-8" onClick={() => setFullscreen(false)}>
          <div
            className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div className="min-w-0">
                <h3 className="truncate text-base font-semibold text-slate-900">{artifact.title || "产物预览"}</h3>
                <p className="text-xs text-slate-500">当前版本 v{artifact.version}</p>
              </div>
              <div className="flex items-center gap-2">
                {versions.length > 0 && (
                  <VersionHistory
                    versions={versions}
                    fromVersion={fromVersion}
                    toVersion={toVersion}
                    onFromVersionChange={setFromVersion}
                    onToVersionChange={(version) => {
                      setToVersion(version);
                      setSelectedVersion(version);
                    }}
                  />
                )}
                <button
                  type="button"
                  onClick={() => setFullscreen(false)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50"
                  aria-label="关闭产物预览"
                  title="关闭"
                >
                  <X size={15} />
                </button>
              </div>
            </div>

            <div className="grid min-h-0 flex-1 gap-0 overflow-hidden lg:grid-cols-[minmax(0,1fr)_420px]">
              <div className="min-h-0 overflow-y-auto p-4">
                {artifact.type === "web_preview" ? (
                  <div className="flex h-[70vh] min-h-0 flex-col overflow-hidden rounded-lg border border-slate-200 bg-slate-100">
                    {(previewUrl || previewError || previewLoading) && (
                      <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-3 py-2">
                        <div className="min-w-0 text-xs text-slate-500">
                          {previewLoading
                            ? "正在连接本机预览"
                            : previewUrl
                              ? "本机 workspace 预览"
                              : "真实预览不可用，已显示内容快照"}
                          {artifact.filePath && (
                            <span className="ml-2 text-slate-400">{artifact.filePath}</span>
                          )}
                        </div>
                        {previewUrl && (
                          <button
                            type="button"
                            onClick={openExternalPreview}
                            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50"
                            aria-label="在浏览器中打开"
                            title="在浏览器中打开"
                          >
                            <ExternalLink size={14} />
                          </button>
                        )}
                      </div>
                    )}
                    <iframe
                      {...iframeProps}
                      sandbox="allow-scripts"
                      className="min-h-0 flex-1 border-0 bg-white"
                      title="网页预览"
                    />
                  </div>
                ) : (
                  <SyntaxHighlighter
                    language={artifact.type === "code_diff" ? "python" : "text"}
                    style={oneDark}
                    customStyle={{ borderRadius: "0.5rem", minHeight: "20rem", margin: 0 }}
                    wrapLongLines
                  >
                    {displayedContent}
                  </SyntaxHighlighter>
                )}
              </div>

              <div className="min-h-0 overflow-y-auto border-t border-slate-200 bg-slate-50 p-3 lg:border-l lg:border-t-0">
                {artifact.type === "code_diff" && (
                  <CodeSelector
                    content={displayedContent}
                    loading={loading}
                    error={error}
                    onPreview={previewEdit}
                  />
                )}
                <div className="mt-3">
                  <DiffViewer
                    diff={editResult?.diff ?? diff}
                    viewMode={viewMode}
                    onViewModeChange={setViewMode}
                  />
                </div>
                {editResult && (
                  <div className="mt-3 rounded-lg border border-blue-200 bg-blue-50 p-3">
                    <div className="text-xs font-medium text-blue-800">
                      Diff 已生成，确认后将创建 v{editResult.diff.toVersion}
                    </div>
                    <div className="mt-3 flex gap-2">
                      <button
                        type="button"
                        disabled={loading}
                        onClick={confirmEdit}
                        className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:bg-slate-300"
                      >
                        <Check size={15} />
                        确认应用
                      </button>
                      <button
                        type="button"
                        disabled={loading}
                        onClick={rejectEdit}
                        className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 disabled:text-slate-300"
                      >
                        <X size={15} />
                        拒绝
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
