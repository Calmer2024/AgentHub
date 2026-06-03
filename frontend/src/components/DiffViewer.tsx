import ReactDiffViewer from "react-diff-viewer-continued";
import type { ArtifactDiff } from "../types";

interface Props {
  diff: ArtifactDiff | null;
  viewMode: "split" | "unified";
  onViewModeChange: (mode: "split" | "unified") => void;
}

export function DiffViewer({ diff, viewMode, onViewModeChange }: Props) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-3 py-2">
        <div className="text-xs font-medium text-slate-700">
          {diff ? `v${diff.fromVersion} -> v${diff.toVersion}` : "Diff"}
        </div>
        <div className="inline-flex rounded-md border border-slate-200 bg-slate-50 p-0.5">
          <button
            type="button"
            onClick={() => onViewModeChange("split")}
            className={`rounded px-2 py-1 text-xs ${
              viewMode === "split" ? "bg-white text-blue-600 shadow-sm" : "text-slate-500"
            }`}
          >
            左右
          </button>
          <button
            type="button"
            onClick={() => onViewModeChange("unified")}
            className={`rounded px-2 py-1 text-xs ${
              viewMode === "unified" ? "bg-white text-blue-600 shadow-sm" : "text-slate-500"
            }`}
          >
            上下
          </button>
        </div>
      </div>
      <div className="max-h-[50vh] overflow-auto text-xs">
        {diff ? (
          <ReactDiffViewer
            oldValue={diff.oldContent}
            newValue={diff.newContent}
            splitView={viewMode === "split"}
            useDarkTheme={false}
            showDiffOnly={false}
            leftTitle={`v${diff.fromVersion}`}
            rightTitle={`v${diff.toVersion}`}
          />
        ) : (
          <div className="px-3 py-4 text-sm text-slate-500">选择两个版本查看差异</div>
        )}
      </div>
    </div>
  );
}
