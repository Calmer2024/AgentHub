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
- Single file max 300 lines (source code only; protocol/design docs exempt). Split if exceeds.
- Every module completion → immediately write unit tests.
- Small commits: each runnable function = one commit.

### Python (Backend)
- Use Pydantic v2 for request/response validation.
- Every API endpoint must validate input. Empty messages → 400. Non-existent session → 404.
- Async everywhere: `async def` for all route handlers and service methods.
- Environment variables via `python-dotenv`. Never hardcode API keys.
- Follow `BaseAgentAdapter` contract from ADR-0005 for all agent adapters.
- 测试使用内存数据库（`sqlite+aiosqlite:///:memory:`），不依赖真实数据库文件。每个测试自己创建所需 fixtures，不假设 DB 中已有数据。

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
- **执行任何 Git 操作（add/commit/push）前，必须先获得用户明确的"人工验收"确认。** 即使模块开发 Skill 中已进入 Step 6，也必须等待用户说"人工验收认可"/"验收通过"/"批准提交"等确认口令。未获确认前，Git 操作等同于 Spec 之外的功能——禁止执行。

---

## Debug 质量守则

Debug 不是"让 bug 消失"，而是"让系统更正确"。修复问题时必须遵守：

1. **修根因，不修表象** — 找到问题的系统性原因（如字段命名不一致、架构设计缺陷），不写补丁式修复
2. **保持代码质量不降级** — 修复不能引入 `any`、绕过类型检查、破坏分层架构、添加临时 hack
3. **前瞻性** — 修复方案要考虑同一类问题是否在项目中其他地方也存在，一并修复
4. **全局性** — 一个 bug 修复后，检查相关联的模块是否受影响（运行全量测试，不仅是相关测试）
5. **安全性** — 不为了"快速修复"而降级 API Key 校验、跳过输入验证、暴露错误详情给前端
6. **字段命名一致性** — 前后端字段名必须严格一致。后端 Pydantic 模型必须用 `Field(alias="camelCase")` + `populate_by_name=True` 统一输出 camelCase
7. **每轮修复后全量测试零回归** — `pytest test_api/` + `npx vitest run` + `npx tsc --noEmit` 三者必须全部通过
8. **主动发现问题** — 用户的验收反馈是片面的，不应只修复用户提出的问题。必须从用户的反馈延申出去，主动审查相关功能是否存在同类设计缺陷、UI/UX 问题、边界条件遗漏。从"这段代码还能怎么出问题"的角度思考，而不是"用户说了什么我就修什么"。

---

## Phase Awareness

Currently **Phase 2 已完成**。Phase 1+2 已合并到 `phase/main` 集成分支。

开发流程：新 Module → `feat/<module>` → 人工验收通过 → squash merge 到 `phase/main`。

Before suggesting any code, check which phase we're in and whether the suggestion fits current scope.
