# CLI Adapter Architecture And Implementation

**Date**: 2026-06-05
**Status**: implementation baseline
**Primary code paths**: `backend/app/agents/`, `backend/app/services/*cli*`, `frontend/src/components/*Agent*`, `frontend/src/components/ExecutionTracePanel.tsx`

## 1. Design Position

AgentHub now treats Claude Code, Codex, and OpenCode as local CLI engines. A product-facing Agent is an Agent Profile: Engine + Skills + Context Policy + runtime config. Legacy API-style pseudo agents, provider configuration panels, default role assistants, and user-facing model/temperature configuration are deprecated.

DeepSeek remains allowed as an internal system LLM for product functions such as automatic conversation title generation and group-chat finalization. It is not exposed as a user-selectable Agent friend.

The current runtime rule is:

```text
Project -> Session -> Agent Profile -> CLI Engine process
```

Each Session belongs to a Project. Each CLI process is spawned with `cwd = Project.workspace_path`, so file writes land in the user's selected local workspace rather than in an abstract chat sandbox.

## 2. Runtime Flow

```text
POST /api/sessions/{sessionId}/chat
  -> ChatServiceImpl
  -> SingleCliChatStream or GroupChatStream
  -> CliAgentService
  -> per-CLI adapter
  -> CliProcessManager
  -> real subprocess in project workspace
  -> stdout/stderr pump
  -> StreamSanitizer
  -> PromptInterceptor
  -> CliOutputParser
  -> ParsedOutput + trace metadata
  -> SSE to frontend
  -> MessageBubble + ExecutionTracePanel
  -> message metadata persistence
```

The adapter layer does not create business artifacts directly. It emits text, progress, error, interactive prompt, and artifact-signal style events. Artifact creation remains the responsibility of the artifact bridge and artifact services.

## 3. Backend Components

| Component | Responsibility |
|-----------|----------------|
| `backend/app/services/agent_seed.py` | Seeds the three built-in CLI Agents and archives non-CLI legacy agents. |
| `backend/app/services/cli_agent_registry.py` | Validates CLI Agent config, checks executable availability, serializes/deserializes CLI args/env, and shields sensitive env values from normal API responses. |
| `backend/app/services/cli_agent_service.py` | Renders chat context into a CLI prompt and delegates execution to the selected adapter. |
| `backend/app/services/single_cli_chat_stream.py` | Bridges single-chat message persistence, SSE streaming, and execution trace metadata. |
| `backend/app/services/cli_agent_executor.py` | Lets group/orchestrator execution call CLI Agents using the same adapter surface. |
| `backend/app/agents/cli_runtime.py` | Owns real subprocess creation, cwd validation, stdin writing, stdout/stderr reading, process registry, timeouts, replies, and termination. |
| `backend/app/agents/cli_adapters.py` | Implements the base adapter plus Claude Code, Codex, and OpenCode specializations. |
| `backend/app/agents/cli_output_parser.py` | Keeps per-run parser state, handles JSONL streams, raw fallback lines, HTML-error suppression, and noisy stderr filtering. |
| `backend/app/agents/cli_stream.py` | Cleans ANSI/TUI control text and detects interactive confirmation prompts. |
| `backend/app/agents/cli_trace.py` | Converts CLI-specific events into structured trace items for frontend rendering. |
| `backend/app/services/execution_trace.py` | Builds bounded, persisted execution trace metadata under `message.metadata.executionTrace`. |
| `backend/app/agents/codex_config.py` | Detects local Codex config from `CODEX_HOME` or `~/.codex`, including official OpenAI and third-party proxy providers. |
| `backend/app/services/codex_local_config_service.py` | Repairs and writes host Codex config through AgentHub UI: `config.toml` plus `.env`, without storing proxy keys in Agent rows. |

## 4. Frontend Components

| Component | Responsibility |
|-----------|----------------|
| `AgentAvatar.tsx` | Provides consistent visual identity for Claude Code, Codex, OpenCode, and custom CLI Agents. |
| `AgentCliForm.tsx` | Modal-style CLI Agent configuration, executable check, and Codex official/proxy setup. |
| `AgentCliRow.tsx` | Friend-list row with status, actions, and settings entry. |
| `ExecutionTracePanel.tsx` | Renders structured process/tool/thought/error trace below the reply bubble; it can collapse and scroll independently. |
| `MessageBubble.tsx` | Renders markdown reply bubbles, agent avatar, execution trace, message actions, and quote/reply context. |
| `ChatWindow.tsx` | Handles Telegram-like chat surface, user-message anchoring, and agent working state. |
| `useSendMessage.ts` | Consumes SSE events, streams text into bubbles, persists trace metadata, and avoids forcing the viewport to the bottom during long runs. |

## 5. Data Model

`agent_configs` is now CLI-first:

| Field | Meaning |
|-------|---------|
| `agent_type` | Expected to be `cli_wrapper` for user-facing Agents. |
| `cli_tool` | `claude_code`, `codex`, `opencode`, or `custom`. |
| `executable` | Command name or executable path, for example `claude`, `codex`, `opencode`. |
| `init_args` | JSON array of startup arguments. |
| `env_vars` | JSON object for advanced runtime overrides. Sensitive Codex API keys are managed in local Codex files, not exposed as ordinary Agent config. |
| `is_active` | Soft-delete/archive flag. |

Message execution traces are persisted in message metadata:

```json
{
  "executionTrace": {
    "status": "running|completed|failed",
    "agentName": "Codex",
    "cliTool": "codex",
    "workspacePath": "D:/...",
    "processId": "cli_...",
    "exitCode": 0,
    "items": [
      {
        "kind": "tool|command|process|error|artifact",
        "text": "...",
        "command": "...",
        "target": "...",
        "timestamp": "..."
      }
    ]
  }
}
```

Trace item count and text size are bounded to prevent a single CLI run from bloating the message row.

## 6. Per-CLI Adapters

### Claude Code

Default invocation:

```text
claude -p --verbose --output-format stream-json --include-partial-messages --dangerously-skip-permissions
```

Claude Code emits JSON events with assistant content, thinking blocks, tool calls, tool results, and final result events. The adapter maps assistant text to reply streaming and maps tool/thinking events to execution trace items.

### Codex

Default invocation:

```text
codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --color never --json -
```

Codex requires extra handling because a user's local Codex can use either official OpenAI endpoints or a third-party OpenAI-compatible gateway. AgentHub detects `~/.codex/config.toml`, `~/.codex/auth.json`, `~/.codex/.env`, `CODEX_HOME`, and process environment variables.

When AgentHub detects official/proxy settings, it launches Codex with `--ignore-user-config` plus explicit `-c` runtime settings. This keeps useful host auth/config information while avoiding polluted profiles that can cause HTML pages, stale provider settings, or wrong model providers to leak into chat output.

For proxy mode, AgentHub requires a proxy API key. ChatGPT login tokens cannot authenticate against third-party gateways. The UI writes stable proxy secrets to `CODEX_HOME/.env` and points the selected provider at `env_key = "CODEX_API_KEY"`.

### OpenCode

Default invocation:

```text
opencode run --pure --agent build --format json --dangerously-skip-permissions
```

OpenCode is normalized away from older unsupported argument patterns. The adapter passes the user prompt as a run argument when needed and parses JSON parts for text, tool usage, and step transitions.

## 7. Process Lifecycle

`CliProcessManager` owns lifecycle boundaries:

- validates that the workspace exists and is a directory
- resolves Windows `.cmd`, `.bat`, and `.ps1` launch paths correctly
- builds a clean CLI environment and sets `NO_COLOR=1` and `TERM=dumb`
- writes prompt input when stdin is piped
- pumps stdout and stderr concurrently
- emits process started/completed/timeout events
- tracks active process snapshots by session
- supports `POST /api/sessions/{id}/interactive_reply` for `y`/`n` prompts
- kills silent processes after the configured timeout

This service intentionally handles only process I/O and lifecycle. CLI-specific meaning stays in adapters and parser modules.

## 8. Output And Trace Strategy

Raw CLI output is not shown directly as one large blob. It is split into:

- reply text, rendered as markdown in the agent bubble
- process/tool/thought/error trace, rendered below the bubble
- interactive prompts, rendered as confirmation cards
- artifact signals, forwarded for downstream artifact handling

The trace panel is meant to be more readable than terminal logs. It keeps the concrete command, tool name, target path, stderr signal, and provider-specific detail when the CLI exposes those fields.

## 9. Configuration And Secret Handling

AgentHub deliberately separates user-visible Agent identity from provider secrets:

- Claude Code and OpenCode mostly inherit host CLI auth.
- Codex official mode can use OpenAI API key or local ChatGPT auth when compatible.
- Codex proxy mode must use a proxy API key because third-party gateways cannot use ChatGPT tokens.
- Codex API keys are written to `CODEX_HOME/.env`, usually `~/.codex/.env`.
- The current provider in `config.toml` is updated to use `env_key`, not inline secrets.
- Frontend API responses show whether a key is set, but not the key value.

## 10. Current Remaining Risks

- Artifact Bridge still needs final end-to-end hardening so workspace diffs, code blocks, and artifact cards stay consistent.
- Per-CLI trace parsing should keep gaining fixtures from real Claude Code, Codex, and OpenCode sessions, especially command/file-operation detail.
- Long-running process cancellation should become a first-class UI action, not only a backend runtime capability.
- Real smoke tests depend on the user's local CLI installations and auth state, so CI can only cover parser/runtime fixtures unless dedicated runners are prepared.
