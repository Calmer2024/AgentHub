import { AlertTriangle, FileCode2, FileText, Files, Globe2, Loader2 } from "lucide-react";
import type { Artifact, Message } from "../types";
import { ArtifactCard } from "./ArtifactCard";

interface Props {
  message: Message;
  artifacts: Artifact[];
  relatedArtifacts?: Artifact[];
  onChanged?: () => void;
}

function iconFor(type: Artifact["type"]) {
  const props = { size: 14, "aria-hidden": true };
  if (type === "web_preview") return <Globe2 {...props} />;
  if (type === "code_diff") return <FileCode2 {...props} />;
  if (type === "file_tree") return <Files {...props} />;
  return <FileText {...props} />;
}

function bridgeStatus(message: Message): string | null {
  const status = message.metadata?.artifactBridge;
  if (!status || typeof status !== "object") return null;
  const raw = (status as Record<string, unknown>).status;
  return typeof raw === "string" ? raw : null;
}

function candidateCount(message: Message): number {
  const candidates = message.metadata?.artifactCandidates;
  return Array.isArray(candidates) ? candidates.length : 0;
}

export function MessageArtifactStrip({ message, artifacts, relatedArtifacts, onChanged }: Props) {
  const related = relatedArtifacts ?? artifacts.filter((artifact) => artifact.messageId === message.id);
  const status = bridgeStatus(message);
  const lowConfidenceCount = candidateCount(message);

  if (status === "scanning" && related.length === 0) {
    return (
      <div className="agenthub-status mt-3 inline-flex h-7 items-center gap-2 rounded-full px-2.5 text-xs">
        <Loader2 size={13} className="animate-spin" aria-hidden="true" />
        <span>分析产物中</span>
      </div>
    );
  }

  if (status === "failed" && related.length === 0) {
    return (
      <div className="agenthub-status-warning mt-3 inline-flex h-7 items-center gap-2 rounded-full border px-2.5 text-xs">
        <AlertTriangle size={13} aria-hidden="true" />
        <span>产物分析失败</span>
      </div>
    );
  }

  if (related.length === 0 && lowConfidenceCount > 0) {
    return (
      <div className="agenthub-muted mt-3 text-xs">
        有 {lowConfidenceCount} 个低置信产物候选
      </div>
    );
  }

  if (related.length === 0) return null;

  return (
    <div className="mt-3 min-w-0 max-w-full space-y-2">
      <div className="agenthub-muted flex min-w-0 items-center gap-2 text-[11px] font-medium">
        <span className="inline-flex items-center gap-1.5">
          {iconFor(related[0].type)}
          本轮产物
        </span>
        <span className="h-px flex-1 bg-[color:var(--ah-border)]" />
        <span>{related.length} 个</span>
      </div>
      <div className="grid min-w-0 gap-2">
        {related.map((artifact) => (
          <ArtifactCard
            key={artifact.id}
            artifact={artifact}
            onChanged={onChanged}
          />
        ))}
      </div>
    </div>
  );
}
