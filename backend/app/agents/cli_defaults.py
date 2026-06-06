"""内置 CLI Agent 默认配置。"""

DEFAULT_CLI_AGENTS = {
    "claude_code": {
        "name": "Claude Code",
        "description": "Anthropic Claude Code CLI",
        "executable": "claude",
        "init_args": [
            "-p",
            "--verbose",
            "--output-format",
            "stream-json",
            "--include-partial-messages",
            "--dangerously-skip-permissions",
        ],
        "env_vars": {},
    },
    "codex": {
        "name": "Codex",
        "description": "OpenAI Codex CLI",
        "executable": "codex",
        "init_args": [
            "exec",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "--color",
            "never",
            "--json",
            "-",
        ],
        "env_vars": {},
    },
    "opencode": {
        "name": "OpenCode",
        "description": "OpenCode CLI",
        "executable": "opencode",
        "init_args": [
            "run",
            "--pure",
            "--agent",
            "build",
            "--format",
            "json",
            "--dangerously-skip-permissions",
        ],
        "env_vars": {},
    },
}
