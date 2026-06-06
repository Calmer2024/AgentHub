# AgentHub 文档中心

> 本文档是 `docs/` 目录的总索引，说明每一份文档和子目录的作用，帮助新成员快速定位所需信息。

---

## 目录结构

```
docs/
├── README.md                    ← 本文件
├── GIT_PROTOCOL.md              ← Git 协作规范
├── TEST_PROTOCOL.md             ← 通用测试协议
│
├── PRD/                         ← 产品需求文档 (权威需求源)
├── adr/                         ← 架构决策记录
├── specs/                       ← 功能规格文档 (按 Phase 组织)
├── deliverables/                 ← 阶段性交付快照、交接文档、使用指南
├── dev-logs/                    ← 开发日志
├── audit/                       ← 阶段性审计报告
├── testing/                     ← 测试规范
└── archive/                     ← 已废弃的历史文档
```

---

## 快速导航

### 我想了解产品要做什么
→ 从 [PRD/00-Master_Hub.md](PRD/00-Master_Hub.md) 开始，然后按编号阅读其余 7 篇。尤其不要跳过 [PRD/05-End_to_End_Product_Flow.md](PRD/05-End_to_End_Product_Flow.md)，它定义了启动文档需求追踪和端到端产品闭环。

**产品交付阶段**：P1 先做桌面版（Web UI + 本地无头服务器 → 本机文件系统 + 本机 CLI Agent），P2 再做 SaaS 云版（云端沙箱 + 一键部署）。详见 PRD-00 第 9 节。

### 我想了解项目现在的状态
→ 看 [CONTEXT.md](../CONTEXT.md) 的 Phase 表格；Phase 6 进度看 [specs/phase6/README.md](specs/phase6/README.md) 与 [dev-logs/phase6-dev-log.md](dev-logs/phase6-dev-log.md)，Phase 7A-7C 看 [deliverables/phase7-runtime-control/](deliverables/phase7-runtime-control/)，Phase 7D IM 加固看 [deliverables/phase7-im-hardening/](deliverables/phase7-im-hardening/)。历史 Phase 3 审计见 [audit/phase3-audit-report.md](audit/phase3-audit-report.md)。

### 我要了解当前 v1.0 发布边界
→ 先读 [deliverables/v1.0-release/](deliverables/v1.0-release/)，再读 [specs/phase7/README.md](specs/phase7/README.md)。7A-7C 运行控制/审批/体检交付快照见 [deliverables/phase7-runtime-control/](deliverables/phase7-runtime-control/)；7D 会话 IM 基线、右键菜单、明亮主题和执行过程全屏见 [deliverables/phase7-im-hardening/](deliverables/phase7-im-hardening/)。

### 我想理解为什么要这样设计
→ 进入 [adr/](adr/) 目录，按编号顺序阅读架构决策记录。

### 我想跑测试
→ 看 [TEST_PROTOCOL.md](TEST_PROTOCOL.md)（通用协议）+ [testing/UX_TEST_SPEC.md](testing/UX_TEST_SPEC.md)（UX 测试规范）。

---

## 各目录详解

### PRD/ — 产品需求文档

**权威级别**: 最高。所有功能开发的最终依据。

| 文件 | 内容 | 读者 |
|------|------|------|
| [00-Master_Hub.md](PRD/00-Master_Hub.md) | 产品愿景、北极星指标、成功衡量、非目标边界 | 所有人 |
| [01-Architecture_Adapter.md](PRD/01-Architecture_Adapter.md) | CLI Agent 封装：PTY 进程管理、ANSI 清洗、交互拦截 | 架构师、后端 |
| [02-Orchestrator_Engine.md](PRD/02-Orchestrator_Engine.md) | 调度引擎：DAG 拆解、状态机、Human-in-the-loop | 后端、AI 工程师 |
| [03-User_Experience.md](PRD/03-User_Experience.md) | 界面原型：三栏布局、资产卡片、页面级 Artifact 预览/编辑、审批卡片 | 设计师、前端 |
| [04-Data_API_Contracts.md](PRD/04-Data_API_Contracts.md) | 数据模型 (projects/agents/sessions/messages/tasks/artifacts)、REST/SSE API | 全栈开发 |
| [05-End_to_End_Product_Flow.md](PRD/05-End_to_End_Product_Flow.md) | 启动文档需求追踪、含 workspace 的北极星演示闭环、Artifact 生成与回流、P2 Roadmap | 产品、架构、全栈、答辩准备 |
| [06-MVP_Local_Workspace_Delivery.md](PRD/06-MVP_Local_Workspace_Delivery.md) | MVP 本机 workspace：创建/绑定目录、Agent cwd、文件变更、预览、导出、可选部署 | 产品、架构、全栈、答辩准备 |
| [07-SaaS_Cloud_Workspace_Delivery.md](PRD/07-SaaS_Cloud_Workspace_Delivery.md) | SaaS 云端 workspace：多租户 sandbox、云端预览、一键部署、配额与安全 | 产品、架构、平台工程 |

### adr/ — 架构决策记录

**权威级别**: 高。记录"做了什么决策 + 为什么"，是架构演进的审计线索。

| 编号 | 文件 | 决策主题 |
|------|------|---------|
| ADR-0001 | [0001-tech-stack-selection.md](adr/0001-tech-stack-selection.md) | 技术栈选型 (React/FastAPI/SQLite) |
| ADR-0002 | [0002-directory-structure.md](adr/0002-directory-structure.md) | 项目目录结构规范 |
| ADR-0003 | [0003-vibe-coding-philosophy.md](adr/0003-vibe-coding-philosophy.md) | 结构化 Vibe Coding 模式 |
| ADR-0004 | [0004-development-methodology.md](adr/0004-development-methodology.md) | 架构跑道 + 行走骨架 + 增量交付 |
| ADR-0005 | [0005-target-architecture.md](adr/0005-target-architecture.md) | 7 层目标架构 + CLI Wrapper 接口契约（进程管理、Workspace Provider、EventBus） |
| ADR-0006 | [0006-ai-collaboration-system.md](adr/0006-ai-collaboration-system.md) | AI 协作体系: Rules/Spec/Skill |
| ADR-0007 | [0007-orchestrator-architecture.md](adr/0007-orchestrator-architecture.md) | Orchestrator 架构: Pipeline + DAG |
| ADR-0008 | [0008-revised-development-strategy.md](adr/0008-revised-development-strategy.md) | **🆕** 功能板块制 + Phase 4-7 路线图 |
| ADR-0009 | [0009-project-workspace-model.md](adr/0009-project-workspace-model.md) | **🆕** Project-Workspace 绑定模型 + CLI 适配策略 + 分层渲染 |
| ADR-0010 | [0010-message-level-artifact-experience.md](adr/0010-message-level-artifact-experience.md) | 消息级 Artifact 体验取代 P1 右侧 Drawer |
| ADR-0011 | [0011-agent-engine-skill-model.md](adr/0011-agent-engine-skill-model.md) | **🆕** Agent = Engine + Skills 建模；调度器作为特殊 Agent |

**阅读建议**: 新成员按编号顺序读。开发者遇到设计疑问时，先查对应 ADR 是否有记录。

### specs/ — 功能规格文档

**权威级别**: 高。每个 Phase 的"完工标准"，人和 AI 共同的验收依据。

| 目录 | Phase | 状态 | 一句话描述 |
|------|-------|------|-----------|
| [phase1/](specs/phase1/) | Walking Skeleton | ✅ | 单聊全链路可运行 |
| [phase2/](specs/phase2/) | Core Features | ✅ | 多 Agent + 群聊 + 产物基础 |
| [phase3/](specs/phase3/) | Orchestrator + Infrastructure | ✅ | EventBus + Pipeline + DAG + CollaborationPanel |
| [phase4/](specs/phase4/) | 消息交互闭环 | ✅ | Reply/Regenerate/Pin + FTS5 搜索 |
| [phase5/](specs/phase5/) | 产物工作台能力 | ✅ | 对已有 Artifact 做版本链 + Diff + 在线编辑；上游入口由 Phase 6/7 补齐 |
| [phase6/](specs/phase6/) | Workspace Runtime + CLI Engine + Agent Profile + 产物入口桥接 | ✅ | 6A Workspace Runtime、6B-6E CLI Adapter、6F Artifact Bridge 与 Agent = Engine + Skills 建模均已落地 |
| [phase7/](specs/phase7/) | 任务可控性 + 审批 + 环境体检 + IM 体验 + 演示闭环 | 🚧 | v1.0 本机 MVP 基线已覆盖运行控制、审批、体检、IM 会话基线和 UI 加固；7E 上下文包与缓存策略已记录；真实 cc 完整自动化脚本待补 |

### deliverables/ — 阶段性交付快照

面向交接、验收和阶段复盘，记录“当前实现到底长什么样”。它不是 PRD/ADR 的替代品，而是实现快照。

| 目录 | 内容 |
|------|------|
| [phase6-cli-adapter/](deliverables/phase6-cli-adapter/) | CLI Adapter 架构与实现原理、用户/开发者使用指南、阶段开发日志 |
| [phase6-artifact-bridge/](deliverables/phase6-artifact-bridge/) | Artifact Bridge 验收快照：消息级产物卡片、文件编辑器、代码引用、版本管理与真实服务验收 |
| [phase7-runtime-control/](deliverables/phase7-runtime-control/) | Phase 7A-7C 验收快照：运行控制、审批卡片、环境体检与取消回退修复 |
| [phase7-im-hardening/](deliverables/phase7-im-hardening/) | Phase 7D 验收快照：会话置顶/归档/未读/免打扰/转发/多选、消息右键菜单、明亮主题与执行过程全屏 |
| [v1.0-release/](deliverables/v1.0-release/) | v1.0.0 发布摘要：本机 MVP 基线、Phase 7D 本轮总结、验证记录与后续风险 |
| [planning/](specs/planning/) | 历史规划 | 📦 | 旧的 Phase 3 模块化计划 (已被 ADR-0008 取代) |

每个 Phase 目录下都有独立的 `README.md`，包含验收标准清单和子模块索引。

**Spec 模板**: [SPEC_TEMPLATE.md](specs/SPEC_TEMPLATE.md) — 新建模块 Spec 时照此填写。

### dev-logs/ — 开发日志

记录每个 Phase 的时间线、关键决策、Bug 与教训。用于复盘和知识传承。

| 文件 | 内容 |
|------|------|
| [phase1-dev-log.md](dev-logs/phase1-dev-log.md) | Phase 1: 时间线、Bug (camelCase/snake_case 不一致、测试污染 .env) |
| [phase2-dev-log.md](dev-logs/phase2-dev-log.md) | Phase 2: WebSocket 心跳、群聊 token 路由、Orchestrator V1 架构违规 |
| [phase3-dev-log.md](dev-logs/phase3-dev-log.md) | Phase 3: 6 天时间线、6 个关键 Bug、4 次 Grill Session、测试覆盖演变 |
| [phase4-dev-log.md](dev-logs/phase4-dev-log.md) | Phase 4: 消息交互闭环、FTS5 修复、真实 UI 验收 |
| [phase5-dev-log.md](dev-logs/phase5-dev-log.md) | Phase 5: 产物版本链、Diff、在线编辑、架构优化、真实 HTTP 验收 |
| [phase6-dev-log.md](dev-logs/phase6-dev-log.md) | Phase 6A: Project-first workspace runtime；Phase 6B-6E: 真实本机 CLI Agent；6F: Artifact Bridge、消息级产物卡片、文件编辑器与版本管理 |
| [phase6-cli-adapter-dev-log.md](dev-logs/phase6-cli-adapter-dev-log.md) | Phase 6 CLI Adapter 专项交接日志：真实 CLI 验证、Codex 中转修复、执行轨迹 UI 与剩余工作 |
| [phase7-dev-log.md](dev-logs/phase7-dev-log.md) | Phase 7A-7D: run/task/process 运行控制、审批 checkpoint、环境体检、IM 基线、明亮主题和 v1.0 UI 加固 |

### audit/ — 审计报告

阶段性质量审计，对照 PRD 检查完成度、架构符合性和文档健康度。

| 文件 | 内容 |
|------|------|
| [phase3-audit-report.md](audit/phase3-audit-report.md) | Phase 3 全面审计：PRD 符合性矩阵、架构偏离分析、模块完成度、文档债 |
| [prd-spec-coverage-audit.md](audit/prd-spec-coverage-audit.md) | 启动文档 → PRD → Spec 覆盖审计：指出端到端 Artifact 链路缺口与修订原则 |

### testing/ — 测试规范

| 文件 | 内容 |
|------|------|
| [UX_TEST_SPEC.md](testing/UX_TEST_SPEC.md) | UX 交互测试：6 状态模型 (空/加载/正常/完成/错误/边界)、Chat 检查清单、P0-P3 缺陷分级 |

### archive/ — 历史文档归档

存放已被取代或不再适用的文档，仅作历史参考。

| 文件 | 原用途 | 取代者 |
|------|--------|--------|
| AgentHub-多Agent协作平台设计.md | 早期课题设计文档 | PRD/ 目录，特别是 PRD-05 的需求追踪矩阵 |
| Trae.md | Trae IDE 使用说明 | 不再维护 |

---

## 根目录文件

### GIT_PROTOCOL.md
Git 协作规范：分支策略 (phase/main 唯一集成分支)、Commit 格式 (`[ai] type: desc`)、AI 提交前必须人工验收的规则。

### TEST_PROTOCOL.md
通用测试协议：测试金字塔定义、工具链 (pytest/vitest/Playwright)、环境要求、Bug 修复后回归测试流程、Mock 使用原则。

---

## 相关入口

- 项目入口：[CONTEXT.md](../CONTEXT.md) — 领域术语、架构总览、完整文档索引
- AI 规则：[CLAUDE.md](../CLAUDE.md) — AI Agent 行为约束
- 人看的总览：[PROJECT_OVERVIEW.md](../PROJECT_OVERVIEW.md) — 项目是什么、怎么做
