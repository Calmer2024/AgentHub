# AgentHub Context

> **这是 AgentHub 项目的全局上下文文档。** 首次参与本项目的开发者/Agent 建议先阅读此文件，建立全局认知后再深入各子文档。
> 
> 本项目文档采用**渐进式披露**策略：入口层概述 → 决策层解释 → 规格层定义 → 协议层约束 → 记录层沉淀。每层总结并向下链接，不跨层复制内容。详见 [CLAUDE.md](CLAUDE.md) Documentation Rules。

## 从哪里开始

| 阅读顺序 | 文档 | 用途 |
|---------|------|------|
| 1 | [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | **新成员首选** — 项目是什么、技术栈、目录结构 |
| 2 | [CONTEXT.md](CONTEXT.md)（本文件） | 领域术语、架构总览、文档索引 |
| 3 | [CLAUDE.md](CLAUDE.md) | AI 行为规则：能做什么、不能做什么 |
| 4 | [docs/PRD/](docs/PRD/) | **产品需求文档 (5 篇)** — 北极星指标、CLI 适配器、Orchestrator、UX 设计、数据契约 |
| 5 | [docs/adr/](docs/adr/) | 关键架构决策及原因 |
| 6 | [docs/specs/](docs/specs/) | 各阶段功能规格与验收标准（Phase 1-7） |

## Domain Glossary

### Core Concepts
- **AgentHub**: 多 Agent 协作平台，采用 IM 聊天作为核心交互范式
- **Agent**: 用户创建的"AI 联系人"，具有自定义名称、描述、system_prompt。长期架构中 Agent 是可被后端管理的真实工具实例，优先通过 CLI Wrapper 封装 Anthropic 官方 `claude` CLI、开源 `opencode` 等物理工具；当前 HTTP API Provider 适配器只是过渡/并存能力。Agent ≠ 模型厂商。
- **Provider / Adapter**: 底层执行适配器。Phase 1-4 已有 DeepSeek、Gemini、GLM、MiniMax、Claude、OpenAI 的 HTTP API 代理；Phase 6 的权威方向是 PRD-01 定义的 CLI Adapter，通过 PTY/subprocess 管理真实 CLI 工具。
- **Orchestrator**: 主 Agent 协调器，负责意图分析 → Agent 选择 → 任务拆解 → 角色分配 → 执行调度。**自动化优先**: 链式协作、角色分配等复杂决策由后端自动完成，不暴露给用户配置。
- **自动项目小队**: Orchestrator 驱动的用户心智模型，一组 Agent 被组织成面向任务目标的临时协作团队。
- **单聊模式**: 1v1 与单个 Agent 对话
- **群聊模式**: 一个对话中包含多个 Agent，支持 @ 指定，Orchestrator 自动协调分工
- **链式协作**: 多 Agent 按阶段顺序协作（规划→执行→审查→综合），由 Orchestrator 自动触发，动态分配角色
- **协作角色**: 6 种模板角色 — planner/executor/reviewer/researcher/synthesizer/critic，Phase 3 模板驱动，未来可升级 LLM 动态分配
- **协作 DAG**: 有向无环图，描述一次协作中 Phase 间的依赖关系。Phase 间串行，Phase 内可并行。
- **共享上下文 (SharedContext)**: 所有 Agent 可读的对话历史，Agent 完成后其产出自动追加。链式依赖的 Agent 额外接收前驱产出的定向注入。
- **引用消息**: 用户显式点选某条历史消息后发出的当前消息。真正引用必须保存 `parentMessageId` + `metadata.replyReference` 快照，并在 Agent prompt 中注入 `[Reply context]` 块；仅显示引用卡片不算完成。
- **Pin 消息**: 用户固定的关键历史消息。Phase 4 起由 ContextManager 在单聊与群聊 Orchestrator Pipeline 中以 `[Pinned message]` 长期上下文块优先注入；仅显示 Pin 标记不算完成。
- **中枢总结**: Orchestrator 在 DAG/chain 等多 Agent 结构化协作完成后生成的系统整理消息。使用独立的 `orchestratorProvider/orchestratorModel` 配置。
- **CollaborationPanel**: 前端 DAG 可视化面板，展示协作流程的各 Phase 及其实时状态。
- **产物 (Artifact)**: Agent 生成的富媒体内容，包括代码 Diff、网页预览、文档等。支持版本历史和在线编辑（Phase 5）。

### Technical Terms
- **Vibe Coding**: 以探索式、边想边写的方式进行快速开发，不追求过早的完整详细设计
- **Walking Skeleton**: 贯穿所有架构层的最薄可运行实现，验证全链路可行（来源：Alistair Cockburn）
- **Architectural Runway**: 只为你近期要飞过的跑道铺路，不为远期需求过早投资（来源：SAFe）
- **Incremental Delivery**: 每次迭代产出可演示的完整功能切片，而非零散功能点堆积
- **功能板块制 (Functional Block System)**: Phase 4 起采用的新开发策略。每个 Phase = 一个独立功能板块，板块内做到 PRD 级完整后才进入下一板块。详见 [ADR-0008](docs/adr/0008-revised-development-strategy.md)。

### AI Collaboration Terms (30% 考察权重)
- **Rules**: 全局约束层。文件：`CLAUDE.md` + `.trae/rules/`
- **Spec**: 功能规格层。文件：`docs/specs/phaseN/`
- **Skill**: 能力复用层。文件：`.claude/skills/`

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

## Development Phases (七阶段模型)

| Phase | 名称 | 状态 | 核心交付 |
|-------|------|------|---------|
| **Phase 0** | 准备期 | ✅ | 接口契约、目标架构、骨架定义、优先级矩阵 |
| **Phase 1** | Walking Skeleton | ✅ | 单聊全链路：前端→API→Agent→SQLite，流式对话 |
| **Phase 2** | Core Features | ✅ | 多 Agent、群聊 + Orchestrator v1、WebSocket、产物基础 |
| **Phase 3** | Orchestrator + Infrastructure | ✅ | EventBus、Orchestrator v2 (Pipeline + DAG + 6角色)、CollaborationPanel |
| **Phase 4** | 消息交互闭环 | ✅ | Reply/Regenerate/Pin、全文搜索 FTS5、Reply/Pin prompt 注入 |
| **Phase 5** | 产物深度管理 | 📋 | 版本链 + Diff、在线编辑 (Tool Calling) |
| **Phase 6** | CLI 适配器 | 📋 | PTY 进程管理、ANSI 清洗、交互拦截 (PRD-01 架构基础) |
| **Phase 7** | UX 体验闭环 | 📋 | 三栏动态布局、产物抽屉、审批卡片、全局打磨 |

**Phase 4-7 采用功能板块制**：每板块独立完整交付，用户可直接使用。板块间按用户可感知价值排序。详见 [ADR-0008](docs/adr/0008-revised-development-strategy.md)。

### Core Principles
1. **Architecture on demand** — don't build all 7 layers on Day 1
2. **Interface before implementation** — define contracts first, iterate on implementation freely
3. **Every increment is demoable** — no "backend done but frontend not connected" intermediate states
4. **自动化优先** — 任何功能设计让任务尽量自动化处理，不要让用户做太多配置。复杂决策（链式触发、角色分配、Agent 选择）由后端自动完成。
5. **功能板块完整交付** — 每个板块内所有子模块（后端 + 前端 + 测试）达到 PRD 级完整后，才进入下一板块。严禁"所有板块都碰一点"（自 Phase 4 起执行）。
6. **ADR documents every architectural decision** — why now, what alternatives were considered

### Forbidden

详见 [CLAUDE.md](CLAUDE.md) 第 "Forbidden" 节（权威源）。核心原则：无契约不写代码、不提前建抽象、每个增量可演示、不跳过 Phase 0、Git 操作前必须人工作业验收。

---

## AI Collaboration System

**Three-tier system**: Rules (always active) → Spec (per-feature) → Skill (reusable workflows)

| Tier | File Location | When Active | Purpose |
|------|--------------|-------------|---------|
| **Rules** | `CLAUDE.md`, `.trae/rules/project_rules.md` | Every AI conversation | Tech stack lock, architecture constraints, code rules, forbidden actions |
| **Spec** | `docs/specs/phaseN/` | Per-feature development | What to build, input/output, behavior, acceptance criteria, non-goals |
| **Skill** | `.claude/skills/*.md` | On-demand (`/skill-name`) | Standardized development workflow, code review checklist |

---

## Key Documents

### PRD (产品需求文档 — 权威需求源)

| Document | Purpose |
|----------|---------|
| [00-Master_Hub](docs/PRD/00-Master_Hub.md) | **PRD 总览**: 北极星指标、产品愿景、成功衡量、非目标边界 |
| [01-Architecture_Adapter](docs/PRD/01-Architecture_Adapter.md) | CLI 适配器设计: PTY/subprocess、ANSI 清洗、交互拦截 |
| [02-Orchestrator_Engine](docs/PRD/02-Orchestrator_Engine.md) | 调度引擎: DAG 拆解、状态机、Human-in-the-loop |
| [03-User_Experience](docs/PRD/03-User_Experience.md) | 交互设计: 三栏布局、资产卡片、产物抽屉、审批卡片 |
| [04-Data_API_Contracts](docs/PRD/04-Data_API_Contracts.md) | 数据模型: agents/sessions/messages/tasks 表, REST/SSE API |

### ADR (架构决策记录)

| ADR | File | Decision |
|-----|------|----------|
| ADR-0001 | [0001-tech-stack-selection.md](docs/adr/0001-tech-stack-selection.md) | 技术栈: React, FastAPI, SQLite |
| ADR-0002 | [0002-directory-structure.md](docs/adr/0002-directory-structure.md) | 目录结构规范 |
| ADR-0003 | [0003-vibe-coding-philosophy.md](docs/adr/0003-vibe-coding-philosophy.md) | 结构化 vibe coding |
| ADR-0004 | [0004-development-methodology.md](docs/adr/0004-development-methodology.md) | 架构跑道 + 行走骨架 + 增量交付 |
| ADR-0005 | [0005-target-architecture.md](docs/adr/0005-target-architecture.md) | 7 层目标架构 + 核心接口契约 |
| ADR-0006 | [0006-ai-collaboration-system.md](docs/adr/0006-ai-collaboration-system.md) | AI 协作体系: Rules/Spec/Skill 三层沉淀 |
| ADR-0007 | [0007-orchestrator-architecture.md](docs/adr/0007-orchestrator-architecture.md) | Orchestrator 架构: Pipeline 四阶段 + DAG + 最终交互设计 |
| ADR-0008 | [0008-revised-development-strategy.md](docs/adr/0008-revised-development-strategy.md) | **🆕 修订开发策略**: 功能板块制 + Phase 4-7 路线图 + 文档治理 |

### Specs (功能规格 — 按 Phase 组织)

| Phase | Directory | 核心 Spec |
|-------|-----------|----------|
| Phase 1 | [specs/phase1/](docs/specs/phase1/) | [01-skeleton-spec.md](docs/specs/phase1/01-skeleton-spec.md) |
| Phase 2 | [specs/phase2/](docs/specs/phase2/) | [01-core-features-spec.md](docs/specs/phase2/01-core-features-spec.md) |
| Phase 3 | [specs/phase3/](docs/specs/phase3/) | [README](docs/specs/phase3/README.md) + [Orchestrator 9 篇](docs/specs/phase3/02-orchestrator/README.md) |
| Phase 4 | [specs/phase4/](docs/specs/phase4/) | [README](docs/specs/phase4/README.md) + 消息操作 + 搜索 |
| Phase 5 | [specs/phase5/](docs/specs/phase5/) | [README](docs/specs/phase5/README.md) + 产物版本 + 在线编辑 |
| Phase 6 | [specs/phase6/](docs/specs/phase6/) | [README](docs/specs/phase6/README.md) + CLI 适配器 |
| Phase 7 | [specs/phase7/](docs/specs/phase7/) | [README](docs/specs/phase7/README.md) + UX 闭环 + 集成 |
| Template | [SPEC_TEMPLATE.md](docs/specs/SPEC_TEMPLATE.md) | 模块规格模板 |
| Planning | [specs/planning/](docs/specs/planning/) | 历史规划文档 (参考) |

### 审计与日志

| Document | Purpose |
|----------|---------|
| [Phase 3 审计报告](docs/audit/phase3-audit-report.md) | **🆕** PRD 符合性矩阵、架构偏离分析、模块完成度、文档债、后续行动 |
| [Git 协议](docs/GIT_PROTOCOL.md) | 分支策略 (phase/main 唯一集成分支)、Commit 格式、AI 提交规则 |
| [测试协议](docs/TEST_PROTOCOL.md) | 测试金字塔、工具链、环境、Bug 修复流程 |
| [UX 测试规范](docs/testing/UX_TEST_SPEC.md) | UX 交互体验: 6 状态模型、检查清单、P0-P3 分级 |
| [Phase 1 Dev Log](docs/dev-logs/phase1-dev-log.md) | Phase 1 时间线、Bug 与教训 |
| [Phase 2 Dev Log](docs/dev-logs/phase2-dev-log.md) | Phase 2 时间线、Bug 与教训 |
| [Phase 3 Dev Log](docs/dev-logs/phase3-dev-log.md) | **🆕** Phase 3 时间线、Bug 与教训、架构决策时间线 |
| [Phase 4 Dev Log](docs/dev-logs/phase4-dev-log.md) | **🆕** Phase 4 实现摘要、FTS5 触发器修复、真实 UI 人工验收记录 |
| [Phase 4 Spec](docs/specs/phase4/README.md) | **🆕** Phase 4 完成记录、验收结果、真实 HTTP + 真实 UI 测试 |

### Skills (AI 能力复用)

| Skill | File | Purpose |
|-------|------|---------|
| module-dev | `.claude/skills/agenthub-module-dev/SKILL.md` | 标准模块开发流程 |
| code-review | `.claude/skills/agenthub-code-review/SKILL.md` | 标准代码审查 |
| phase-wrapup | `.claude/skills/agenthub-phase-wrapup/SKILL.md` | Phase 收尾流程 |
| qa-audit | `.claude/skills/agenthub-qa-audit/SKILL.md` | 企业级质量审计 |

---

## 文档治理规则

1. **Phase 结束时审计** — 检查所有 docs/ 下的交叉引用是否有效
2. **ADR 编号与文件名一致** — `NNNN-title.md` 内部标题必须是 `ADR-NNNN`
3. **Spec 文件必须被索引** — 不被 CONTEXT.md 索引的 Spec = 无效文档
4. **旧文档立即归档或删除** — 不再适用的文档移入 `docs/archive/`
5. **一个事实一个权威源** — 同一信息不出现在两个地方。引用用链接，不复制。
