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

const BRAND_LOGOS: Record<string, { label: string; src: string; darkSrc?: string }> = {
  claude_code: {
    label: "Claude Code",
    src: simpleIconDataUri(siClaudecode.path, "#D97757"),
  },
  codex: {
    label: "OpenAI Codex",
    src: "/brands/openai.svg",
  },
  opencode: {
    label: "OpenCode",
    src: "/brands/opencode-light.svg",
    darkSrc: "/brands/opencode-dark.svg",
  },
};

const ROLE_AVATAR_FILES: Record<string, string> = {
  产品经理: "产品经理.png",
  项目经理: "产品经理.png",
  uxui设计师: "UI-UX工程师.png",
  uiux工程师: "UI-UX工程师.png",
  测试工程师: "测试工程师.png",
  前端工程师: "前端工程师.png",
  后端工程师: "后端工程师.png",
  数据库工程师: "数据库工程师.png",
  系统架构师: "系统架构师.png",
  项目leader: "项目Leader.png",
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
    className: "border-teal-100/35 bg-teal-700 text-white",
  },
  {
    id: "preset:blue",
    label: "蓝图",
    icon: Code2,
    className: "border-sky-200/35 bg-blue-600 text-white",
  },
  {
    id: "preset:violet",
    label: "灵感",
    icon: Palette,
    className: "border-violet-200/35 bg-violet-600 text-white",
  },
  {
    id: "preset:amber",
    label: "终端",
    icon: Terminal,
    className: "border-amber-200/35 bg-amber-600 text-white",
  },
  {
    id: "preset:green",
    label: "数据",
    icon: Database,
    className: "border-emerald-200/35 bg-emerald-700 text-white",
  },
  {
    id: "preset:rose",
    label: "目标",
    icon: Target,
    className: "border-rose-200/35 bg-rose-600 text-white",
  },
  {
    id: "preset:slate",
    label: "系统",
    icon: Cpu,
    className: "border-slate-200/35 bg-slate-700 text-white",
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
    className: "border-teal-100/35 bg-teal-700 text-white",
  },
};

export function AgentAvatar({
  agent,
  name,
  kind = "agent",
  size = "md",
  className = "",
}: Props) {
  const displayName = agent?.name ?? name ?? "";
  const brand = resolveBrand(agent?.cliTool, displayName, kind);
  const uploadedAvatar = kind === "agent" && agent?.avatar?.startsWith("data:image/")
    ? resolveCustomAvatar(agent.avatar)
    : null;
  const roleAvatar = kind === "agent" && !uploadedAvatar ? resolveRoleAvatar(displayName) : null;
  const customAvatar = uploadedAvatar ?? (kind === "agent" && !brand && !roleAvatar ? resolveCustomAvatar(agent?.avatar) : null);
  const look = resolveLook(agent?.cliTool, displayName, kind);
  const Icon = customAvatar?.icon ?? look.icon;

  if (kind === "user") {
    return (
      <span
        className={`agenthub-user-avatar inline-flex shrink-0 items-center justify-center ${SIZE_CLASS[size]} ${className}`}
        title={displayName || "用户"}
        aria-label={displayName || "用户"}
      >
        <UserRound size={ICON_SIZE[size] + 2} strokeWidth={1.8} aria-hidden="true" />
      </span>
    );
  }

  if (brand && !uploadedAvatar) {
    return (
      <span
        className={`agenthub-cli-avatar inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full ${SIZE_CLASS[size]} ${className}`}
        title={displayName || brand.label}
        aria-label={displayName || brand.label}
      >
        <img src={brand.src} alt="" className={`agenthub-cli-logo ${brand.darkSrc ? "agenthub-cli-logo-light" : ""}`} />
        {brand.darkSrc && <img src={brand.darkSrc} alt="" className="agenthub-cli-logo agenthub-cli-logo-dark" />}
      </span>
    );
  }

  if (roleAvatar) {
    return (
      <span
        className={`agenthub-role-avatar inline-flex shrink-0 overflow-hidden rounded-full ${SIZE_CLASS[size]} ${className}`}
        title={displayName}
        aria-label={displayName}
      >
        <img src={roleAvatar} alt="" className="h-full w-full object-cover" />
      </span>
    );
  }

  return (
    <span className={`inline-flex shrink-0 ${SIZE_CLASS[size]} ${className}`}>
      <span
        className={`flex h-full w-full items-center justify-center overflow-hidden rounded-full ${kind === "group" ? "shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]" : "border shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]"} ${customAvatar?.className ?? look.className}`}
        title={displayName || customAvatar?.label || look.label}
        aria-label={displayName || customAvatar?.label || look.label}
      >
        {customAvatar?.src ? (
          <img src={customAvatar.src} alt="" className="h-full w-full object-cover" />
        ) : (
          <Icon size={ICON_SIZE[size]} strokeWidth={1.9} aria-hidden="true" />
        )}
      </span>
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

function resolveRoleAvatar(name: string) {
  const normalizedName = name.toLowerCase().replace(/[\s/_-]+/g, "");
  const filename = normalizedName.includes("调度器") || normalizedName.includes("orchestrator")
    ? "项目Leader.png"
    : ROLE_AVATAR_FILES[normalizedName];
  return filename ? `/agent-avatars/${encodeURIComponent(filename)}` : null;
}

function svgDataUri(svg: string) {
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function simpleIconDataUri(path: string, fill: string) {
  return svgDataUri(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="${fill}" d="${path}"/></svg>`,
  );
}

function resolveBrand(
  cliTool: string | undefined,
  name: string,
  kind: Props["kind"],
) {
  if (kind !== "agent") return null;
  const normalizedName = name.toLowerCase();
  if (cliTool === "claude_code" && normalizedName === "claude code") return BRAND_LOGOS.claude_code;
  if (cliTool === "codex" && (normalizedName === "codex" || normalizedName === "openai codex")) return BRAND_LOGOS.codex;
  if (cliTool === "opencode" && normalizedName === "opencode") return BRAND_LOGOS.opencode;
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
      className: "bg-[color:var(--ah-card-soft)] text-[color:var(--ah-text-strong)]",
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

  if (cliTool && TOOL_LOOK[cliTool]) {
    return { ...TOOL_LOOK[cliTool], label: name || cliTool };
  }
  return {
    icon: Code2,
    className: "border-zinc-300/20 bg-zinc-700/70 text-zinc-100",
    label: name || "CLI Agent",
  };
}
