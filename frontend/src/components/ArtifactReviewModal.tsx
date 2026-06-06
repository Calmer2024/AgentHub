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
      className="agenthub-backdrop fixed inset-0 z-[1060] flex items-center justify-center p-3 md:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="审批产物审阅"
      onClick={onClose}
    >
      <div
        className="agenthub-modal flex max-h-[90dvh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="agenthub-header flex items-center justify-between gap-3 border-b px-4 py-3">
          <div className="min-w-0">
            <div className="agenthub-muted text-[11px]">审批审阅</div>
            <h3 className="agenthub-strong mt-1 truncate text-base font-semibold">
              {artifact.title || artifact.filePath || "关联产物"}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-full"
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
