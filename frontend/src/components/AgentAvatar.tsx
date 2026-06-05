import {
  BrainCircuit,
  Braces,
  Code2,
  Cpu,
  Sparkles,
  TerminalSquare,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { AgentConfig } from "../types";

type AvatarSize = "sm" | "md" | "lg";

interface Props {
  agent?: Pick<AgentConfig, "name" | "cliTool" | "status"> | null;
  name?: string | null;
  kind?: "agent" | "user" | "group" | "system";
  size?: AvatarSize;
  active?: boolean;
  className?: string;
}

const SIZE_CLASS: Record<AvatarSize, string> = {
  sm: "h-8 w-8",
  md: "h-10 w-10",
  lg: "h-12 w-12",
};

const ICON_SIZE: Record<AvatarSize, number> = {
  sm: 15,
  md: 18,
  lg: 21,
};

const TOOL_LOOK: Record<string, { icon: LucideIcon; className: string }> = {
  claude_code: {
    icon: BrainCircuit,
    className: "border-amber-300/25 bg-amber-400/15 text-amber-100",
  },
  codex: {
    icon: TerminalSquare,
    className: "border-sky-300/25 bg-sky-400/15 text-sky-100",
  },
  opencode: {
    icon: Braces,
    className: "border-emerald-300/25 bg-emerald-400/15 text-emerald-100",
  },
  custom: {
    icon: Cpu,
    className: "border-fuchsia-300/25 bg-fuchsia-400/15 text-fuchsia-100",
  },
};

export function AgentAvatar({
  agent,
  name,
  kind = "agent",
  size = "md",
  active,
  className = "",
}: Props) {
  const displayName = agent?.name ?? name ?? "";
  const look = resolveLook(agent?.cliTool, displayName, kind);
  const Icon = look.icon;
  const showActive = active ?? agent?.status === "ready";

  return (
    <span className={`relative inline-flex shrink-0 ${SIZE_CLASS[size]} ${className}`}>
      <span
        className={`flex h-full w-full items-center justify-center rounded-full border shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] ${look.className}`}
        title={displayName || look.label}
        aria-label={displayName || look.label}
      >
        <Icon size={ICON_SIZE[size]} strokeWidth={1.8} aria-hidden="true" />
      </span>
      {kind === "agent" && (
        <span
          className={`absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-[#171717] ${
            showActive ? "bg-emerald-300" : "bg-zinc-500"
          }`}
          aria-hidden="true"
        />
      )}
    </span>
  );
}

function resolveLook(
  cliTool: string | undefined,
  name: string,
  kind: Props["kind"],
): { icon: LucideIcon; className: string; label: string } {
  if (kind === "user") {
    return {
      icon: UserRound,
      className: "border-blue-300/20 bg-blue-500 text-white",
      label: "用户",
    };
  }
  if (kind === "group") {
    return {
      icon: Users,
      className: "border-violet-300/25 bg-violet-400/15 text-violet-100",
      label: "群聊",
    };
  }
  if (kind === "system") {
    return {
      icon: Sparkles,
      className: "border-indigo-300/25 bg-indigo-400/15 text-indigo-100",
      label: "系统",
    };
  }

  const normalizedName = name.toLowerCase();
  if (cliTool && TOOL_LOOK[cliTool]) {
    return { ...TOOL_LOOK[cliTool], label: name || cliTool };
  }
  if (normalizedName.includes("claude")) {
    return { ...TOOL_LOOK.claude_code, label: name || "Claude Code" };
  }
  if (normalizedName.includes("codex")) {
    return { ...TOOL_LOOK.codex, label: name || "Codex" };
  }
  if (normalizedName.includes("open")) {
    return { ...TOOL_LOOK.opencode, label: name || "OpenCode" };
  }
  return {
    icon: Code2,
    className: "border-zinc-300/20 bg-zinc-700/70 text-zinc-100",
    label: name || "CLI Agent",
  };
}
