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
    <div className="mt-3 overflow-hidden rounded-lg border border-amber-300/25 bg-amber-300/[0.06] text-[#ececf1]">
      <div className="flex items-center gap-2 border-b border-amber-300/15 bg-amber-300/[0.08] px-3 py-2 text-xs font-medium text-amber-100">
        {iconFor(approval.status)}
        <span>{approval.title}</span>
        <span className="ml-auto text-[11px] text-amber-100/75">{labelFor(approval.status)}</span>
      </div>
      <div className="space-y-3 px-3 py-3">
        {approval.summary && (
          <p className="text-xs leading-relaxed text-[#d8d8df]">{approval.summary}</p>
        )}
        {artifact ? (
          <button
            type="button"
            onClick={() => onOpenArtifact?.(artifact)}
            className="flex w-full items-center gap-2 rounded-md border border-white/10 bg-[#0d1117]/60 px-2.5 py-2 text-left text-xs text-[#d8d8df] transition hover:border-sky-300/35 hover:bg-sky-300/[0.08]"
          >
            <FileSearch size={14} className="shrink-0 text-sky-200" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-sky-100">
                {artifact.title || artifact.filePath || "关联产物"}
              </span>
              <span className="mt-0.5 block truncate text-[11px] text-[#9aa5b1]">
                {artifact.type} · v{artifact.version}{artifact.filePath ? ` · ${artifact.filePath}` : ""}
              </span>
            </span>
          </button>
        ) : (
          <div className="inline-flex items-center gap-2 rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-2 text-xs text-[#9aa5b1]">
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
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-white/10 px-2.5 text-xs text-[#d8d8df] transition hover:bg-white/[0.07] disabled:opacity-50"
            >
              <Undo2 size={13} aria-hidden="true" />
              驳回修改
            </button>
            <button
              type="button"
              onClick={() => onApprove(approval)}
              disabled={busy}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-emerald-300/25 bg-emerald-300/10 px-2.5 text-xs font-medium text-emerald-100 transition hover:bg-emerald-300/15 disabled:opacity-50"
            >
              {busy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
              确认继续
            </button>
          </div>
        ) : approval.reason ? (
          <div className="rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-2 text-xs text-[#d8d8df]">
            {approval.reason}
          </div>
        ) : null}
      </div>
    </div>
  );
}
