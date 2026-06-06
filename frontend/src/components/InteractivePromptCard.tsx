import { useState } from "react";
import { Check, Loader2, ShieldAlert, X } from "lucide-react";

export function InteractivePromptCard({
  content,
  onReply,
}: {
  content: string;
  onReply: (reply: "y" | "n") => Promise<void>;
}) {
  const [busy, setBusy] = useState<"y" | "n" | null>(null);

  const submit = async (reply: "y" | "n") => {
    setBusy(reply);
    try { await onReply(reply); }
    finally { setBusy(null); }
  };

  return (
    <div className="agenthub-status-warning rounded-2xl border px-3 py-2">
      <div className="flex items-start gap-2 text-sm">
        <ShieldAlert size={16} className="mt-0.5 shrink-0" />
        <span>{content}</span>
      </div>
      <div className="mt-2 flex gap-2">
        <button type="button" onClick={() => submit("y")} disabled={busy !== null}
          aria-label="同意"
          title="同意"
          className="agenthub-primary-button inline-flex h-8 w-8 items-center justify-center rounded-full disabled:opacity-50">
          {busy === "y" ? <Loader2 size={15} className="animate-spin" /> : <Check size={16} />}
        </button>
        <button type="button" onClick={() => submit("n")} disabled={busy !== null}
          aria-label="拒绝"
          title="拒绝"
          className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-full disabled:opacity-50">
          {busy === "n" ? <Loader2 size={15} className="animate-spin" /> : <X size={16} />}
        </button>
      </div>
    </div>
  );
}
