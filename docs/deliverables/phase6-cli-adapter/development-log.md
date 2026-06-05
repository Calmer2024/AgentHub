# Phase 6 CLI Adapter Development Log

**Date**: 2026-06-05
**Stage**: Phase 6B-6E CLI Adapter stabilization
**Status**: implementation baseline ready for commit

## 1. Completed In This Stage

- Removed the old API-agent architecture from the active product path: legacy provider adapters, provider/settings API panels, default role assistants, and user-facing provider/model configuration are no longer the primary Agent model.
- Kept DeepSeek as an internal system LLM for product functions such as title generation and group-chat finalization, without exposing it as a user Agent friend.
- Seeded and normalized the three built-in CLI friends: Claude Code, Codex, and OpenCode.
- Added CLI-only migrations, including schema updates for executable/init args/env vars and cleanup of legacy agent config rows.
- Implemented a real subprocess runtime for local CLI execution with workspace cwd binding, stdout/stderr streaming, Windows command resolution, process registry, timeout handling, and interactive replies.
- Split CLI responsibilities across runtime, defaults, per-CLI adapters, output parsing, trace rendering, Codex config detection, and chat streaming services.
- Added per-CLI adapters for Claude Code, Codex, and OpenCode.
- Connected single chat and group/orchestrator execution to the CLI runner when sessions have a Project workspace.
- Added structured execution traces below reply bubbles and persisted them in message metadata.
- Improved frontend chat UI around Telegram-style bubbles, agent avatars, markdown rendering, scroll behavior, quote/search/actions, and independent trace scrolling.
- Replaced the old model settings panel with an Agent settings modal focused on CLI configuration.
- Added Codex official/proxy configuration support through AgentHub UI.
- Added host Codex config repair: API keys are moved to `CODEX_HOME/.env`; `config.toml` providers point to `env_key`; proxy mode no longer relies on transient ChatGPT tokens.
- Added Codex noise handling for HTML error bodies, model-list fragments, and known stderr warnings.
- Integrated OpenCode real CLI path and fixed previous prompt/argument behavior that caused process completion without reply finalization.
- Added project rename/delete support and cleaned sidebar placement for project/session creation actions.

## 2. Validation Status

Validated during this phase:

- Real Claude Code API path can create a Project, Session, and AgentHub chat run, then write target files into the workspace.
- Real OpenCode CLI path passed manual acceptance after argument normalization and message finalization fixes.
- Codex became usable after configuring the proxy API key through AgentHub and repairing local Codex config.
- Backend and frontend regression commands were run during the larger refactor cycle:

```powershell
cd backend && .\venv\Scripts\python.exe -m pytest test_api/ test_unit/test_cli_adapter_runtime.py -q
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run
cd frontend && npm run build
cd backend && .\venv\Scripts\python.exe test_real_api_claude_smoke.py
cd backend && .\venv\Scripts\python.exe test_real_api_codex_smoke.py
```

Before final handoff/merge, rerun the current regression set because the working tree includes broad backend, frontend, migration, and documentation changes.

## 3. Important Decisions

- A user-facing Agent is a CLI wrapper, not a role prompt and not an API provider.
- One Project owns one local workspace. CLI processes always execute in that workspace.
- CLI output is rendered in two layers: answer text in the bubble, execution process below the bubble.
- Execution process text is saved with the message so users can inspect what happened after the run.
- The old 300-line file limit is no longer treated as a hard rule. Files should be split by real responsibility boundaries, not by an arbitrary line count.
- Codex proxy mode must use a proxy API key. ChatGPT login tokens are not valid credentials for third-party gateways.
- AgentHub should help repair local Codex config rather than asking users to hand-edit `~/.codex` files.

## 4. Remaining Work

- Finish Artifact Bridge hardening: workspace diff signals, code blocks, confidence thresholds, and Artifact Card creation should form one reliable loop.
- Keep expanding per-CLI parser fixtures from real CLI output, especially for detailed command/file-operation display.
- Add first-class cancel/terminate controls to the frontend for long-running CLI processes.
- Build a repeatable real-CLI smoke checklist that records local CLI versions, auth mode, and workspace file assertions.
- Continue trimming architecture friction after the CLI-only cleanup, especially around group chat, artifact creation, and old orchestrator terminology.

## 5. Handoff Notes

Start future work from these files:

- `backend/app/agents/cli_adapters.py`
- `backend/app/agents/cli_runtime.py`
- `backend/app/agents/cli_output_parser.py`
- `backend/app/services/single_cli_chat_stream.py`
- `backend/app/services/codex_local_config_service.py`
- `frontend/src/components/ExecutionTracePanel.tsx`
- `frontend/src/components/AgentCliForm.tsx`
- `frontend/src/hooks/useSendMessage.ts`

When debugging real CLI behavior, capture the smallest real stdout/stderr sample that reproduces the issue, then add a parser or stream regression test before changing UI behavior.
