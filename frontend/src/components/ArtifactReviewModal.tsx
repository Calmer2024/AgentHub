import { createPortal } from "react-dom";
import { X } from "lucide-react";
import type { Artifact } from "../types";
import { ArtifactCard } from "./ArtifactCard";

interface Props {
  artifact: Artifact | null;
  onClose: () => void;
  onChanged?: () => void;
}

export function ArtifactReviewModal({ artifact, onClose, onChanged }: Props) {
  if (!artifact || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[1060] flex items-center justify-center bg-black/70 p-3 md:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="审批产物审阅"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90dvh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-[#30363d] bg-[#0d1117] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[#30363d] bg-[#161b22] px-4 py-3">
          <div className="min-w-0">
            <div className="text-[11px] text-[#8b949e]">审批审阅</div>
            <h3 className="mt-1 truncate text-base font-semibold text-[#f0f6fc]">
              {artifact.title || artifact.filePath || "关联产物"}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[#30363d] text-[#8b949e] hover:bg-[#21262d] hover:text-[#f0f6fc]"
            aria-label="关闭审批审阅"
            title="关闭"
          >
            <X size={15} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <ArtifactCard artifact={artifact} onChanged={onChanged} />
        </div>
      </div>
    </div>,
    document.body,
  );
}
