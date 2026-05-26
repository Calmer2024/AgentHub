# CLAUDE.md

## Project: AgentHub — Multi-Agent Collaboration Platform

IM-style chat platform where users converse with AI agents (Claude, Codex, etc.), with group chat orchestration and artifact previews.

---

## Architecture Constraints

### Layer Dependency (top → bottom, only downward dependencies allowed)
```
Frontend (React) → API Gateway (FastAPI) → Service/Business Logic → Domain/Core → Infrastructure → Data/Persistence
```

### Key Rules
- Modules can only depend on layers below them. Never upward.
- Same-layer modules communicate through interfaces or Event Bus, never direct imports.
- Domain layer is pure logic: zero framework dependencies (no FastAPI, no SQLAlchemy).
- Architecture grows on demand: Phase 1 only has 3 layers. New layers are introduced only when complexity forces it (see ADR-0004 trigger conditions).
- Interface contracts (ADR-0005) are stable; implementations can change freely.

---

## Tech Stack (Locked)

| Layer | Technology |
|-------|-----------|
| Frontend | React + TypeScript + Vite + shadcn/ui + Tailwind CSS v3 |
| Backend | Python FastAPI + WebSocket |
| Database | SQLite + SQLAlchemy 2.0 (async with aiosqlite) |
| Desktop | Tauri v2 |
| Mobile | Capacitor |
| AI SDK | anthropic (Python), @anthropic-ai/sdk (TypeScript) |

---

## Code Rules

### Universal
- All comments and documentation in Chinese.
- Single file max 300 lines. Split if exceeds.
- Every module completion → immediately write unit tests.
- Small commits: each runnable function = one commit.

### Python (Backend)
- Use Pydantic v2 for request/response validation.
- Every API endpoint must validate input. Empty messages → 400. Non-existent session → 404.
- Async everywhere: `async def` for all route handlers and service methods.
- Environment variables via `python-dotenv`. Never hardcode API keys.
- Follow `BaseAgentAdapter` contract from ADR-0005 for all agent adapters.

### TypeScript (Frontend)
- No `any` type. Use `unknown` if truly uncertain, then narrow.
- Zustand for state management. One store per domain (chat, sessions, etc.).
- Components: shadcn/ui primitives only. Custom styling via Tailwind classes.
- API client: typed fetch wrapper, SSE via EventSource with reconnect logic.

---

## Forbidden

- Building abstractions "we might need later" — only build what the current phase demands.
- Writing module implementation before defining its interface contract.
- Ending any increment without a demoable frontend.
- Skipping acceptance criteria verification before marking a phase complete.
- Adding features outside the current Spec's scope (see Non-Goals section).

---

## Phase Awareness

Currently in **Phase 1 (Walking Skeleton)**. Scope: single-chat full pipeline, Claude only, SSE streaming, no Orchestrator, no WebSocket, no artifacts, no auth.

Before suggesting any code, check which phase we're in and whether the suggestion fits current scope.
