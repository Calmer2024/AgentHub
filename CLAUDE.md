# CLAUDE.md

## Project: AgentHub — Multi-Agent Collaboration Platform

IM-style chat platform where users converse with AI agents (Claude, Codex, etc.), with group chat orchestration and artifact previews.

> **项目全局上下文**：见 [CONTEXT.md](CONTEXT.md)（领域术语、架构总览、开发方法论、文档索引）。首次参与本项目的开发者/Agent 建议先阅读 CONTEXT.md。

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
- All code comments in Chinese. AI-facing docs (CLAUDE.md, Skills, ADRs) in English for efficient agent consumption. Human-facing docs (design docs, dev logs, specs) in Chinese.
- Single file max 300 lines (source code only; protocol/design docs exempt). Split if exceeds.
- Every module completion → immediately write unit tests.
- Small commits: each runnable function = one commit.
- **自动化优先**: 任何功能设计在前端上的体现是让任务尽量可以自动化处理，不要让用户做太多配置。便利化用户交互逻辑，复杂决策由后端自动完成。例如：Orchestrator 链式协作应自动触发，不应要求用户手动配置开关。

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

## Documentation Rules

All project documentation follows **progressive disclosure**:

1. **Layer by detail depth, not by topic.** Entry docs (CLAUDE.md, CONTEXT.md) provide overview and link to details. ADRs explain decisions. Specs define exact requirements. Dev logs record history.
2. **Summarize, don't duplicate.** A downstream doc may summarize an upstream concept with a link, but never copy-paste the full content. One authoritative source per fact.
3. **Cross-reference, never repeat.** If a rule/decision already exists in another doc, link to it instead of restating.
4. **Index before detail.** Every doc directory has an index (CONTEXT.md "Key Documents", ADR numbering, Spec template) so readers can find what they need without reading everything.
5. **New docs must earn their place.** Before creating a new doc, ask: does this fit in an existing doc? If yes, amend; if no, create and add to the index.

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

Currently in **Phase 2 (Core Features) — completed**. Phase 3 (Enhancements) in planning.

Phase 2 scope: multi-agent support, group chat, orchestrator, WebSocket, artifact previews.
Phase 3 scope: Orchestrator upgrade (intent + task decomposition + agent chains), artifact versioning + Diff + inline editing, message reply/regenerate/pin/search.
