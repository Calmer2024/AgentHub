import { CheckCircle2, FileSearch, Loader2, ShieldAlert, ShieldCheck, ShieldX, Undo2 } from "lucide-react";
import type { ApprovalCheckpoint, Artifact } from "../types";

interface Props {
  approval: ApprovalCheckpoint;
  artifact?: Artifact | null;
  busy?: boolean;
  onApprove: (approval: ApprovalCheckpoint) => void;
  onReject: (approval: ApprovalCheckpoint) => void;
  onOpenArtifact?: (artifact: Artifact) => void;
}

function iconFor(status: ApprovalCheckpoint["status"]) {
  if (status === "approved") return <ShieldCheck size={15} aria-hidden="true" />;
  if (status === "rejected") return <ShieldX size={15} aria-hidden="true" />;
  return <ShieldAlert size={15} aria-hidden="true" />;
}

function labelFor(status: ApprovalCheckpoint["status"]) {
  if (status === "approved") return "已确认继续";
  if (status === "rejected") return "已驳回";
  return "等待人工确认";
}

export function ApprovalCard({
  approval,
  artifact,
  busy,
  onApprove,
  onReject,
  onOpenArtifact,
}: Props) {
  const pending = approval.status === "pending_review";
  return (
    <div className="agenthub-status-warning mt-3 overflow-hidden rounded-2xl border">
      <div className="flex items-center gap-2 border-b px-3 py-2 text-xs font-medium" style={{ borderColor: "var(--ah-border)" }}>
        {iconFor(approval.status)}
        <span>{approval.title}</span>
        <span className="agenthub-muted ml-auto text-[11px]">{labelFor(approval.status)}</span>
      </div>
      <div className="space-y-3 px-3 py-3">
        {approval.summary && (
          <p className="text-xs leading-relaxed">{approval.summary}</p>
        )}
        {artifact ? (
          <button
            type="button"
            onClick={() => onOpenArtifact?.(artifact)}
            className="agenthub-soft flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left text-xs transition hover:border-[color:var(--ah-border-hover)]"
          >
            <FileSearch size={14} className="agenthub-muted shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="agenthub-strong block truncate font-medium">
                {artifact.title || artifact.filePath || "关联产物"}
              </span>
              <span className="agenthub-muted mt-0.5 block truncate text-[11px]">
                {artifact.type} · v{artifact.version}{artifact.filePath ? ` · ${artifact.filePath}` : ""}
              </span>
            </span>
          </button>
        ) : (
          <div className="agenthub-soft inline-flex items-center gap-2 rounded-md border px-2.5 py-2 text-xs agenthub-muted">
            <FileSearch size={14} aria-hidden="true" />
            <span>无关联产物，可基于摘要审批</span>
          </div>
        )}
        {pending ? (
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={() => onReject(approval)}
              disabled={busy}
              className="agenthub-icon-button inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs disabled:opacity-50"
            >
              <Undo2 size={13} aria-hidden="true" />
              驳回修改
            </button>
            <button
              type="button"
              onClick={() => onApprove(approval)}
              disabled={busy}
              className="agenthub-primary-button inline-flex h-8 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium transition disabled:opacity-50"
            >
              {busy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
              确认继续
            </button>
          </div>
        ) : approval.reason ? (
          <div className="agenthub-soft rounded-md border px-2.5 py-2 text-xs">
            {approval.reason}
          </div>
        ) : null}
      </div>
    </div>
  );
}
