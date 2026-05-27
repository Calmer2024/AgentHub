# AgentHub Context

## Domain Glossary

### Core Concepts
- **AgentHub**: 多 Agent 协作平台，采用 IM 聊天作为核心交互范式
- **Agent**: 聊天中的"联系人"，具备特定能力的 AI 角色
- **Orchestrator**: 主 Agent 协调器，负责任务拆解和子 Agent 调度
- **单聊模式**: 1v1 与单个 Agent 对话
- **群聊模式**: 一个对话中包含多个 Agent，支持 @ 指定，Orchestrator 自动协调分工
- **产物**: Agent 生成的富媒体内容，包括代码 Diff、网页预览、文档等

### Technical Terms
- **Vibe Coding**: 以探索式、边想边写的方式进行快速开发，不追求过早的完整详细设计
- **Walking Skeleton**: 贯穿所有架构层的最薄可运行实现，验证全链路可行（来源：Alistair Cockburn）
- **Architectural Runway**: 只为你近期要飞过的跑道铺路，不为远期需求过早投资（来源：SAFe）
- **Incremental Delivery**: 每次迭代产出可演示的完整功能切片，而非零散功能点堆积

### AI Collaboration Terms
- **Rules**: 全局约束层。AI 在项目里永远不能做什么、必须遵守什么。文件：`CLAUDE.md` + `.trae/rules/`
- **Spec**: 功能规格层。每个模块"要建成什么样子"，人和 AI 共同的完工标准。文件：`docs/specs/`
- **Skill**: 能力复用层。重复性 AI 开发流程封装为可一键调用的工作流。文件：`.claude/skills/`

---

## Target Architecture (7 Layers)

```
Frontend (React + shadcn/ui + Zustand)
  → API Gateway (FastAPI REST + WebSocket Manager)
    → Service / Business Logic (Session, Message, Artifact Services)
      → Domain / Core (Orchestrator, Context/Prompt Manager)
        → Infrastructure (Agent Adapters, Event Bus, File Storage)
          → Data / Persistence (SQLAlchemy Models, Configuration Store)
```

**Key rule**: Architecture grows on demand. Day 1 (Phase 1) only implements 3 of 7 layers. New layers are introduced only when complexity forces it — see ADR-0004 for trigger conditions.

---

## Development Methodology

**Hybrid model**: Architectural Runway (strategy) + Walking Skeleton (tactics) + Incremental Delivery (rhythm)

### Five Phases

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 0** (Prep) | 2-3 days | Interface contracts, target architecture, skeleton definition, priority matrix |
| **Phase 1** (Walking Skeleton) | 3-5 days | Single-chat full pipeline: frontend → API → Claude → SQLite, streaming works |
| **Phase 2** (Core Features) | 1-2 weeks | Multi-agent, group chat + Orchestrator, artifact previews |
| **Phase 3** (Enhancements) | 1-2 weeks | P1 features: deployment, richer artifacts, multi-platform |
| **Phase 4** (Polish) | 3-5 days | Bug fixes, demo video, presentation prep |

### Core Principles
1. **Architecture on demand** — don't build all 7 layers on Day 1
2. **Interface before implementation** — define contracts first, iterate on implementation freely
3. **Every increment is demoable** — no "backend done but frontend not connected" intermediate states
4. **ADR documents every architectural decision** — why now, what alternatives were considered

### Forbidden
- ❌ Writing module code without an interface contract first
- ❌ Building abstractions "we might need later"
- ❌ Ending an increment with a non-demoable frontend
- ❌ Skipping Phase 0 (interface contracts and skeleton definition)

---

## AI Collaboration System (30% assessment weight)

**Three-tier system**: Rules (always active) → Spec (per-feature) → Skill (reusable workflows)

| Tier | File Location | When Active | Purpose |
|------|--------------|-------------|---------|
| **Rules** | `CLAUDE.md`, `.trae/rules/project_rules.md` | Every AI conversation | Tech stack lock, architecture constraints, code rules, forbidden actions |
| **Spec** | `docs/specs/SPEC_TEMPLATE.md`, `docs/specs/*-spec.md` | Per-feature development | What to build, input/output, behavior, acceptance criteria, non-goals |
| **Skill** | `.claude/skills/*.md` | On-demand (`/skill-name`) | Standardized development workflow, code review checklist |

### Collaboration Principles
1. **No Spec, no code** — AI must refuse to develop without a Spec document
2. **Contract first** — interface definition before implementation
3. **Accumulate continuously** — Rules/Specs/Skills evolve through Git history, not written once
4. **Demo the evolution** — show Git diff of these artifacts during defense

---

## Key Documents

| Document | Purpose |
|----------|---------|
| [ADR-0001](docs/adr/0001-tech-stack-selection.md) | Tech stack: React, FastAPI, SQLite, Tauri, Capacitor |
| [ADR-0002](docs/adr/0002-directory-structure.md) | Directory structure conventions |
| [ADR-0003](docs/adr/0003-vibe-coding-philosophy.md) | Structured vibe coding philosophy |
| [ADR-0004](docs/adr/0004-development-methodology.md) | Hybrid development model, phase definitions, trigger conditions |
| [ADR-0005](docs/adr/0005-target-architecture.md) | 7-layer target architecture + core interface contracts |
| [ADR-0006](docs/adr/0006-phase1-walking-skeleton.md) | Phase 1 detailed plan, acceptance criteria, directory layout |
| [ADR-0007](docs/adr/0007-ai-collaboration-system.md) | AI collaboration system: Rules/Spec/Skill three-tier design, accumulation roadmap |
| [Spec Template](docs/specs/SPEC_TEMPLATE.md) | Feature specification template (standard format for all module specs) |
| [Phase 1 Spec](docs/specs/phase1-skeleton-spec.md) | Phase 1 walking skeleton spec |
| [Phase 2 Spec](docs/specs/phase2-core-features-spec.md) | Phase 2 core features: multi-agent, group chat, orchestrator, WebSocket, artifacts |
| [Phase 2 Dev Log](docs/phase2-dev-log.md) | Phase 2 development log: timeline, bugs, lessons learned |
| [CLAUDE.md](CLAUDE.md) | Project-level AI behavior guide (loaded automatically by Claude Code) |
| [Test Protocol](docs/TEST_PROTOCOL.md) | 通用测试协议：金字塔、工具链、环境、Bug 修复流程 |
| [UX Test Spec](docs/testing/UX_TEST_SPEC.md) | UX 交互体验测试规范：6 状态模型、Chat 检查清单、P0-P3 分级 |
| [Phase 1 Test Plan](docs/testing/phase1-test-plan.md) | Phase 1 测试计划：29 条测试用例清单 |
| [Git Protocol](docs/GIT_PROTOCOL.md) | Git 协作规范：分支策略、Commit 格式、PR 流程、AI 提交规则 |
| [Skill: module-dev](.claude/skills/agenthub-module-dev/SKILL.md) | Standardized module development workflow |
| [Skill: code-review](.claude/skills/agenthub-code-review/SKILL.md) | Standardized code review checklist |
| [Skill: phase-wrapup](.claude/skills/agenthub-phase-wrapup/SKILL.md) | Phase wrapup workflow |
