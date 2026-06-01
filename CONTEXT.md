# AgentHub Context

> **这是 AgentHub 项目的全局上下文文档。** 首次参与本项目的开发者/Agent 建议先阅读此文件，建立全局认知后再深入各子文档。
> 
> 本项目文档采用**渐进式披露**策略：入口层概述 → 决策层解释 → 规格层定义 → 协议层约束 → 记录层沉淀。每层总结并向下链接，不跨层复制内容。详见 [CLAUDE.md](CLAUDE.md) Documentation Rules。

## 从哪里开始

| 阅读顺序 | 文档 | 用途 |
|---------|------|------|
| 1 | [ONBOARDING.md](ONBOARDING.md) | **新成员首选** — 项目概览、目录结构、启动命令、Skill 说明 |
| 2 | [CONTEXT.md](CONTEXT.md)（本文件） | 领域术语、架构总览、文档索引 |
| 3 | [CLAUDE.md](CLAUDE.md) | AI 行为规则：能做什么、不能做什么 |
| 4 | [docs/adr/](docs/adr/) | 关键架构决策及原因 |
| 5 | [docs/specs/](docs/specs/) | 各阶段功能规格与验收标准 |
| 6 | [FIRST_ISSUES.md](FIRST_ISSUES.md) | **新成员推荐优先 Issue** — 分三个难度等级 |

## Domain Glossary

### Core Concepts
- **AgentHub**: 多 Agent 协作平台，采用 IM 聊天作为核心交互范式
- **Agent**: 用户创建的"AI联系人"，具有自定义名称、描述、system_prompt。多个 Agent 可能使用同一家模型厂商（DeepSeek/Gemini/GLM/MiniMax），但能力标签不同。Agent ≠ 模型厂商。
- **Provider (模型厂商)**: 提供底层 LLM API 的服务商。当前可用: DeepSeek、Gemini、GLM（智谱）、MiniMax。Agent 通过 AgentConfig.provider 字段选择底层模型。
- **Orchestrator**: 主 Agent 协调器，负责意图分析 → Agent 选择 → 任务拆解 → 角色分配 → 执行调度。**自动化优先**: 链式协作、角色分配等复杂决策由后端自动完成，不暴露给用户配置。
- **单聊模式**: 1v1 与单个 Agent 对话
- **群聊模式**: 一个对话中包含多个 Agent，支持 @ 指定，Orchestrator 自动协调分工
- **链式协作**: 多 Agent 按阶段顺序协作（规划→执行→审查→综合），由 Orchestrator 自动触发，动态分配角色
- **协作角色**: 6 种模板角色 — planner/executor/reviewer/researcher/synthesizer/critic，Phase 3 模板驱动，Phase 4 升级 LLM 动态分配
- **协作 DAG**: 有向无环图，描述一次协作中 Phase 间的依赖关系。Phase 间串行，Phase 内可并行。由 `SubTask.depends_on` 声明依赖，`ExecutionPlanner` 拓扑排序后分配 Phase。
- **共享上下文 (SharedContext)**: 所有 Agent 可读的对话历史，Agent 完成后其产出自动追加。链式依赖的 Agent 额外接收前驱产出的定向注入。
- **CollaborationPanel**: 前端 DAG 可视化面板，展示协作流程的各 Phase 及其实时状态，替代当前的 CollaborationView。
- **对话流共享**: Agent 产出实时追加到共享对话历史，后续 Agent 像群聊成员一样"看到前面的人说了什么"。
- **定向注入**: Chain 模式下，依赖链上前驱的完整产出以 structured prompt 形式注入后继 Agent 的输入。
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

| Phase | Deliverable |
|-------|----------|-------------|
| **Phase 0** (Prep) | Interface contracts, target architecture, skeleton definition, priority matrix |
| **Phase 1** (Walking Skeleton) | Single-chat full pipeline: frontend → API → Claude → SQLite, streaming works |
| **Phase 2** (Core Features) | Multi-agent, group chat + Orchestrator, artifact previews |
| **Phase 3** (Enhancements) | Orchestrator 智能升级、产物版本管理+Diff+局部修改、消息引用+重生成+Pin+搜索 |
| **Phase 4** (Polish) | Bug fixes, demo video, presentation prep |

### Core Principles
1. **Architecture on demand** — don't build all 7 layers on Day 1
2. **Interface before implementation** — define contracts first, iterate on implementation freely
3. **Every increment is demoable** — no "backend done but frontend not connected" intermediate states
4. **自动化优先** — 任何功能设计让任务尽量自动化处理，不要让用户做太多配置。复杂决策（链式触发、角色分配、Agent 选择）由后端自动完成。
5. **ADR documents every architectural decision** — why now, what alternatives were considered

### Forbidden

详见 [CLAUDE.md](CLAUDE.md) 第 "Forbidden" 节（权威源）。核心原则：无契约不写代码、不提前建抽象、每个增量可演示、不跳过 Phase 0、Git 操作前必须人工作业验收。

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
| [Phase 3 Spec](docs/specs/phase3-enhancements-spec.md) | Phase 3 智能增强 (完整技术规格) |
| [Phase 3 Modules](docs/specs/phase3-modules.md) | Phase 3 模块化拆解 + 依赖图 + 复杂度矩阵 |
| [Phase 3 Parallel Guide](docs/specs/phase3-parallel-guide.md) | Phase 3 并行开发指南 (团队协作) |
| [ADR-0008](docs/adr/0008-orchestrator-architecture.md) | Orchestrator 架构决策记录 (Pipeline 四阶段 + 最终交互设计) |
| [Orchestrator Docs](docs/specs/orchestrator/README.md) | **Orchestrator 完整设计文档 (9 篇)** — 架构/Agent选择/任务拆解/执行引擎/协作交互/SSE协议/前端/开发计划/日志 |
| [Phase 1 Dev Log](docs/phase1-dev-log.md) | Phase 1 开发日志：时间线、Bug 与教训 |
| [Phase 2 Dev Log](docs/phase2-dev-log.md) | Phase 2 开发日志：时间线、Bug 与教训 |
| [CLAUDE.md](CLAUDE.md) | 项目级 AI 行为指南（Claude Code 每次对话自动加载） |
| [Test Protocol](docs/TEST_PROTOCOL.md) | 通用测试协议：金字塔、工具链、环境、Bug 修复流程 |
| [UX Test Spec](docs/testing/UX_TEST_SPEC.md) | UX 交互体验测试规范：6 状态模型、Chat 检查清单、P0-P3 分级 |
| [Phase 1 Test Plan](docs/testing/phase1-test-plan.md) | Phase 1 测试计划：28 条测试用例清单 |
| [Git Protocol](docs/GIT_PROTOCOL.md) | Git 协作规范：分支策略、Commit 格式、PR 流程、AI 提交规则 |
| [Skill: module-dev](.claude/skills/agenthub-module-dev/SKILL.md) | Standardized module development workflow |
| [Skill: code-review](.claude/skills/agenthub-code-review/SKILL.md) | Standardized code review checklist |
| [Skill: phase-wrapup](.claude/skills/agenthub-phase-wrapup/SKILL.md) | Phase wrapup workflow |
| [Skill: qa-audit](.claude/skills/agenthub-qa-audit/SKILL.md) | Enterprise QA audit: real-world testing, E2E chain verification, UX heuristic inspection |
