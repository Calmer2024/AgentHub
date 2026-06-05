# CLI Adapter Usage Guide

**Date**: 2026-06-05
**Audience**: AgentHub users and developers
**Applies to**: Claude Code, Codex, OpenCode local CLI Agents

## 1. User Guide

### 1.1 Prerequisites

Install and authenticate the CLI tools you want to use on the host machine:

| Agent | Executable | Auth expectation |
|-------|------------|------------------|
| Claude Code | `claude` | Use the normal local Claude Code login/auth flow. |
| Codex | `codex` | Use official OpenAI auth or configure a third-party gateway through AgentHub. |
| OpenCode | `opencode` | Use the normal local OpenCode config/auth flow. |

AgentHub does not install these CLIs for the user. It detects and runs the local executables.

### 1.2 Create Or Select A Project

1. Open AgentHub.
2. In the workspace sidebar, create a blank project or select an existing folder.
3. AgentHub binds that Project to a local `workspacePath`.
4. Every chat under the Project runs its CLI process inside that workspace.

This means generated files are real files on your machine.

### 1.3 Configure A CLI Agent

Open the Agent friend settings from the sidebar.

Common fields:

| Field | Meaning |
|-------|---------|
| CLI tool | Claude Code, Codex, OpenCode, or custom. |
| Executable | Command or executable path, for example `codex`. |
| Startup args | The launch arguments AgentHub passes to the CLI. Defaults are already set for the built-in Agents. |
| Environment variables | Advanced overrides. Do not use this as the normal place for Codex API keys. |

Use the executable check button to verify that AgentHub can find the command.

### 1.4 Configure Codex Official Or Proxy Mode

Codex has an additional connection section.

Official OpenAI mode:

- Base URL defaults to `https://api.openai.com/v1`.
- You can use an OpenAI API key.
- You can also allow local ChatGPT auth when the local Codex installation supports it.

Proxy mode:

- Enter the third-party gateway Base URL.
- AgentHub normalizes the URL to an OpenAI-compatible `/v1` endpoint when possible.
- Enter the proxy API key.
- AgentHub writes the key to local Codex `.env`, usually `~/.codex/.env`, using `CODEX_API_KEY`.
- AgentHub updates `~/.codex/config.toml` so the selected provider uses `env_key = "CODEX_API_KEY"`.

Important: proxy mode cannot use a local ChatGPT token. If the proxy returns `401 Unauthorized`, re-open Codex settings and update the proxy API key.

### 1.5 Start A Chat

1. Pick a Project.
2. Click a CLI Agent friend and start a private chat, or create a group chat.
3. Send a prompt.
4. AgentHub starts a real CLI process in the Project workspace.
5. The agent reply appears as a chat bubble.
6. The execution process appears below the bubble as a collapsible trace block.

While the agent is working, the view anchors to your newly sent message. It does not force-scroll to the latest agent output. The execution block has its own scroll area for long traces.

### 1.6 Read Execution Trace Blocks

Execution trace blocks are saved with the message. They may contain:

- process start and finish
- executed command
- tool name
- target file or path
- CLI stderr warnings that matter
- interactive prompt details
- artifact or diff signals

When a reply finishes, the block can collapse automatically so the chat stays readable.

### 1.7 Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `未找到 'codex' 命令` | Executable is not on PATH. | Install the CLI or set the full executable path in Agent settings. |
| Codex shows `401 Unauthorized` for a proxy URL | Proxy API key is missing or invalid. | Open Codex settings in AgentHub and save the proxy API key again. |
| Codex output contains HTML page content | Base URL points to a web page, not an API endpoint. | Use the gateway API base URL, usually ending in `/v1`. |
| A chat stays waiting after process end | SSE/message finalization bug or parser missed completion. | Check backend logs and `/api/agents/runtime/processes`; then run the related CLI smoke test. |
| Trace has too little detail | That CLI emitted a format the parser does not yet understand. | Add a parser fixture from the real output and extend `cli_trace.py` / `cli_adapters.py`. |

## 2. Developer Guide

### 2.1 Main APIs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/agents` | GET | List active CLI Agents. |
| `/api/agents` | POST | Create a CLI Agent. |
| `/api/agents/{agentId}` | PATCH | Update a CLI Agent. |
| `/api/agents/{agentId}` | DELETE | Soft-delete/archive a CLI Agent. |
| `/api/agents/check-executable?path=...` | GET | Check whether a CLI executable is available. |
| `/api/agents/codex-config` | GET | Read local Codex connection status. |
| `/api/agents/codex-config` | PUT | Write or repair local Codex official/proxy config. |
| `/api/agents/runtime/processes` | GET | Inspect active CLI processes, optionally by `sessionId`. |
| `/api/sessions/{sessionId}/chat` | POST | Start a streaming chat run. |
| `/api/sessions/{sessionId}/interactive_reply` | POST | Reply `y` or `n` to a waiting CLI prompt. |

### 2.2 Agent Config Payload

```json
{
  "name": "Codex",
  "description": "OpenAI Codex CLI",
  "agentType": "cli_wrapper",
  "cliTool": "codex",
  "executable": "codex",
  "initArgs": [
    "exec",
    "--skip-git-repo-check",
    "--dangerously-bypass-approvals-and-sandbox",
    "--color",
    "never",
    "--json",
    "-"
  ],
  "envVars": {}
}
```

For Codex proxy credentials, prefer `/api/agents/codex-config` over `envVars`.

### 2.3 Add A New CLI Adapter

1. Add default config in `backend/app/agents/cli_defaults.py`.
2. Implement an adapter in `backend/app/agents/cli_adapters.py`.
3. Register it in `_ADAPTERS`.
4. Add trace helpers in `backend/app/agents/cli_trace.py`.
5. Add parser/runtime unit tests with real sample output.
6. Add frontend preset/avatar data if it should appear as a first-class friend.
7. Add smoke documentation for real local CLI verification.

Keep process lifecycle logic in `CliProcessManager`. Keep CLI-specific semantics in the adapter and trace parser.

### 2.4 Local Verification Commands

Backend:

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest test_api/ test_unit/test_cli_adapter_runtime.py test_unit/test_codex_local_config_service.py -q
```

Frontend:

```powershell
cd frontend
npm run build
npx vitest run
```

Real local smoke tests require installed and authenticated CLIs:

```powershell
cd backend
.\venv\Scripts\python.exe test_real_api_claude_smoke.py
.\venv\Scripts\python.exe test_real_api_codex_smoke.py
.\venv\Scripts\python.exe test_real_cli_smoke.py
```

Do not treat mock CLI tests as acceptance for this module. They are useful regression tests, but final acceptance must run against the user's real local CLI tools.
