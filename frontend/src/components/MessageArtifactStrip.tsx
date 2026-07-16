import { AlertTriangle, Loader2 } from "lucide-react";
import type { AgentConfig, Artifact, Message } from "../types";
import { ArtifactCard } from "./ArtifactCard";
import { AgentAvatar } from "./AgentAvatar";
import { formatChinaDateTime } from "../utils/time";

interface Props {
  message: Message;
  artifacts: Artifact[];
  relatedArtifacts?: Artifact[];
  onChanged?: () => void;
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

export function MessageArtifactStrip({ message, artifacts, relatedArtifacts }: Props) {
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

  return null;
}

export function ArtifactMessage({
  artifact,
  agent,
  agentName,
  onChanged,
}: {
  artifact: Artifact;
  agent?: AgentConfig | null;
  agentName?: string | null;
  onChanged?: () => void;
}) {
  const author = agentName || agent?.name || "Agent";
  return (
    <article className="agenthub-message-row agenthub-message-enter" aria-label={`产物消息：${artifact.title}`}>
      <AgentAvatar agent={agent} name={author} kind="agent" size="md" />
      <div className="min-w-0 max-w-[min(82%,860px)] flex-1">
        <div className="agenthub-message-head mb-1.5 flex items-center gap-2 px-1 text-xs">
          <span className="agenthub-message-author font-semibold">{author}</span>
          <span className="agenthub-ai-badge">AI</span>
          <time className="agenthub-message-time ml-auto" dateTime={artifact.createdAt}>
            {formatChinaDateTime(artifact.createdAt)}
          </time>
        </div>
        <div className="agenthub-artifact-message-bubble min-w-0 overflow-hidden rounded-[20px] p-1.5">
          <ArtifactCard artifact={artifact} onChanged={onChanged} />
        </div>
      </div>
    </article>
  );
}
