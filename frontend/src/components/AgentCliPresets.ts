export const CLI_PRESETS = {
  claude_code: {
    name: "Claude Code",
    description: "本机 Claude Code CLI",
    executable: "claude",
    initArgs: [
      "-p",
      "--verbose",
      "--output-format",
      "stream-json",
      "--include-partial-messages",
      "--dangerously-skip-permissions",
    ],
    envVars: {},
  },
  codex: {
    name: "Codex",
    description: "本机 Codex CLI",
    executable: "codex",
    initArgs: [
      "exec",
      "--skip-git-repo-check",
      "--dangerously-bypass-approvals-and-sandbox",
      "--color",
      "never",
      "--json",
      "-",
    ],
    envVars: {},
  },
  opencode: {
    name: "OpenCode",
    description: "本机 OpenCode CLI",
    executable: "opencode",
    initArgs: [
      "run",
      "--pure",
      "--agent",
      "build",
      "--format",
      "json",
      "--dangerously-skip-permissions",
    ],
    envVars: {},
  },
  custom: {
    name: "Custom CLI",
    description: "自定义本机 CLI",
    executable: "",
    initArgs: [],
    envVars: {},
  },
} as const;

export type CliTool = keyof typeof CLI_PRESETS;

export function isBlockedAgentEnvKey(key: string, cliTool: CliTool = "custom") {
  void cliTool;
  const normalized = key.trim().toUpperCase();
  return normalized === "API_KEY" || normalized.endsWith("_API_KEY");
}
