import {
  Code2,
  Cpu,
  Database,
  MessagesSquare,
  Palette,
  Sparkles,
  Target,
  Terminal,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { siClaudecode } from "simple-icons";
import type { AgentConfig } from "../types";

type AvatarSize = "sm" | "md" | "lg";

interface Props {
  agent?: Pick<AgentConfig, "name" | "cliTool" | "status" | "avatar"> | null;
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

const BRAND_LOGOS: Record<string, { label: string; className: string; src: string }> = {
  claude_code: {
    label: "Claude Code",
    className: "border-amber-300/25 bg-amber-400/15 text-amber-100",
    src: simpleIconDataUri(siClaudecode.path, "#D97757", "#191714"),
  },
  codex: {
    label: "OpenAI Codex",
    className: "border-sky-300/25 bg-sky-400/15 text-sky-100",
    src: svgDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="18" fill="#0b1220"/><path fill="none" stroke="#38bdf8" stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="m24 20-9 12 9 12M40 20l9 12-9 12"/><path fill="none" stroke="#f8fafc" stroke-linecap="round" stroke-width="4" d="m36 16-8 32"/></svg>`),
  },
  opencode: {
    label: "OpenCode",
    className: "border-emerald-300/25 bg-emerald-400/15 text-emerald-100",
    src: svgDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="18" fill="#071b14"/><circle cx="32" cy="32" r="18" fill="none" stroke="#34d399" stroke-width="4"/><path fill="none" stroke="#d1fae5" stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="M27 23 18 32l9 9M37 23l9 9-9 9"/></svg>`),
  },
};

export const AGENT_AVATAR_PRESETS: Array<{
  id: string;
  label: string;
  icon: LucideIcon;
  className: string;
}> = [
  {
    id: "preset:custom",
    label: "自定义",
    icon: Sparkles,
    className: "border-teal-100/35 bg-[linear-gradient(135deg,#0f766e,#334155,#f59e0b)] text-white",
  },
  {
    id: "preset:blue",
    label: "蓝图",
    icon: Code2,
    className: "border-sky-200/35 bg-[linear-gradient(135deg,#0ea5e9,#2563eb)] text-white",
  },
  {
    id: "preset:violet",
    label: "灵感",
    icon: Palette,
    className: "border-violet-200/35 bg-[linear-gradient(135deg,#8b5cf6,#d946ef)] text-white",
  },
  {
    id: "preset:amber",
    label: "终端",
    icon: Terminal,
    className: "border-amber-200/35 bg-[linear-gradient(135deg,#f59e0b,#ef4444)] text-white",
  },
  {
    id: "preset:green",
    label: "数据",
    icon: Database,
    className: "border-emerald-200/35 bg-[linear-gradient(135deg,#10b981,#0f766e)] text-white",
  },
  {
    id: "preset:rose",
    label: "目标",
    icon: Target,
    className: "border-rose-200/35 bg-[linear-gradient(135deg,#f43f5e,#fb7185)] text-white",
  },
  {
    id: "preset:slate",
    label: "系统",
    icon: Cpu,
    className: "border-slate-200/35 bg-[linear-gradient(135deg,#475569,#111827)] text-white",
  },
];

export const CUSTOM_AGENT_DEFAULT_AVATAR = "preset:custom";

type ResolvedCustomAvatar = {
  label: string;
  icon: LucideIcon;
  className: string;
  src?: string;
};

const TOOL_LOOK: Record<string, { icon: LucideIcon; className: string }> = {
  custom: {
    icon: Sparkles,
    className: "border-teal-100/35 bg-[linear-gradient(135deg,#0f766e,#334155,#f59e0b)] text-white",
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
  const customAvatar = kind === "agent" ? resolveCustomAvatar(agent?.avatar) : null;
  const brand = resolveBrand(agent?.cliTool, displayName, kind);
  const look = resolveLook(agent?.cliTool, displayName, kind);
  const Icon = customAvatar?.icon ?? look.icon;
  const showActive = active ?? agent?.status === "ready";

  return (
    <span className={`relative inline-flex shrink-0 ${SIZE_CLASS[size]} ${className}`}>
      <span
        className={`flex h-full w-full items-center justify-center overflow-hidden rounded-full border shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] ${customAvatar?.className ?? look.className}`}
        title={displayName || customAvatar?.label || look.label}
        aria-label={displayName || customAvatar?.label || look.label}
      >
        {customAvatar?.src ? (
          <img src={customAvatar.src} alt="" className="h-full w-full object-cover" />
        ) : brand && !customAvatar ? (
          <img src={brand.src} alt="" className="h-[72%] w-[72%] rounded-[35%] object-cover" />
        ) : (
          <Icon size={ICON_SIZE[size]} strokeWidth={1.9} aria-hidden="true" />
        )}
      </span>
      {kind === "agent" && (
        <span
          className={`absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 ${
            showActive ? "bg-emerald-300" : "bg-zinc-500"
          }`}
          style={{ borderColor: "var(--ah-sidebar-bg)" }}
          aria-hidden="true"
        />
      )}
    </span>
  );
}

function resolveCustomAvatar(value: string | undefined): ResolvedCustomAvatar | null {
  const avatar = (value ?? "").trim();
  if (!avatar) return null;
  if (avatar.startsWith("data:image/")) {
    return {
      label: "自定义头像",
      src: avatar,
      icon: Code2,
      className: "border-[color:var(--ah-border-strong)] bg-[color:var(--ah-card-soft)]",
    };
  }
  return AGENT_AVATAR_PRESETS.find((preset) => preset.id === avatar) ?? null;
}

function svgDataUri(svg: string) {
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function simpleIconDataUri(path: string, fill: string, background: string) {
  return svgDataUri(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">` +
    `<rect width="64" height="64" rx="18" fill="${background}"/>` +
    `<svg x="14" y="14" width="36" height="36" viewBox="0 0 24 24">` +
    `<path fill="${fill}" d="${path}"/>` +
    `</svg></svg>`,
  );
}

function resolveBrand(
  cliTool: string | undefined,
  name: string,
  kind: Props["kind"],
) {
  if (kind !== "agent") return null;
  const normalizedName = name.toLowerCase();
  if (cliTool && BRAND_LOGOS[cliTool]) return BRAND_LOGOS[cliTool];
  if (normalizedName.includes("claude")) return BRAND_LOGOS.claude_code;
  if (normalizedName.includes("codex")) return BRAND_LOGOS.codex;
  if (normalizedName.includes("open")) return BRAND_LOGOS.opencode;
  return null;
}

function resolveLook(
  cliTool: string | undefined,
  name: string,
  kind: Props["kind"],
): { icon: LucideIcon; className: string; label: string } {
  if (kind === "user") {
    return {
      icon: UserRound,
      className: "agenthub-primary-button border-[color:var(--ah-border-strong)]",
      label: "用户",
    };
  }
  if (kind === "group") {
    return {
      icon: MessagesSquare,
      className: "border-[color:var(--ah-border-strong)] bg-[color:var(--ah-card-soft)] text-[color:var(--ah-text-strong)]",
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
  if (cliTool && BRAND_LOGOS[cliTool]) {
    return { icon: Code2, className: BRAND_LOGOS[cliTool].className, label: BRAND_LOGOS[cliTool].label };
  }
  if (normalizedName.includes("claude")) {
    return { icon: Code2, className: BRAND_LOGOS.claude_code.className, label: name || BRAND_LOGOS.claude_code.label };
  }
  if (normalizedName.includes("codex")) {
    return { icon: Code2, className: BRAND_LOGOS.codex.className, label: name || BRAND_LOGOS.codex.label };
  }
  if (normalizedName.includes("open")) {
    return { icon: Code2, className: BRAND_LOGOS.opencode.className, label: name || BRAND_LOGOS.opencode.label };
  }
  if (cliTool && TOOL_LOOK[cliTool]) {
    return { ...TOOL_LOOK[cliTool], label: name || cliTool };
  }
  return {
    icon: Code2,
    className: "border-zinc-300/20 bg-zinc-700/70 text-zinc-100",
    label: name || "CLI Agent",
  };
}
