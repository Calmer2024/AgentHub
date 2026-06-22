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
├── PRD/                         ← 产品需求拆解文档（与核心设计共同构成权威需求源）
├── adr/                         ← 架构决策记录
├── architecture/                ← 当前架构事实：总览、数据模型、运行模型、事件契约
├── submission/                  ← 课程/挑战赛提交用飞书可复制文档
├── user-guides/                 ← 面向最终用户的使用与配置手册
├── testing/                     ← 测试规范
└── archive/                     ← 归档文档（含核心设计与已完成 Phase 资料）
```

---

## 快速导航

### 我想了解产品要做什么
→ 先读 [archive/AgentHub-多Agent协作平台设计.md](archive/AgentHub-多Agent协作平台设计.md) 把握核心启动需求，再从 [PRD/00-Master_Hub.md](PRD/00-Master_Hub.md) 开始按编号阅读其余 7 篇。早期设计文档虽然位于 `archive/`，但仍是 IM、多 Agent 协作、Artifact、预览/编辑/部署、多端协作等核心需求的权威来源；PRD 系列负责拆解、收缩边界并阶段化落地。

**产品交付阶段**：P1 先做桌面版（Web UI + 本地无头服务器 → 本机文件系统 + 本机 CLI Agent），P2 再做 SaaS 云版（云端沙箱 + 一键部署）。详见 PRD-00 第 9 节。

### 我要提交课程/挑战赛作业
→ 先读 [submission/00-交付总入口.md](submission/00-交付总入口.md)。该目录下的文档按飞书可复制格式组织，包含交付总入口、产品设计文档、技术设计文档和 AI 协作开发记录。

### 我想了解项目现在的状态
→ 看 [CONTEXT.md](../CONTEXT.md) 的产品状态与 Phase 表格。所有 Phase 资料已归档到 [archive/phases/](archive/phases/)：规格在 `archive/phases/specs/`，交付快照在 `archive/phases/deliverables/`，开发日志在 `archive/phases/dev-logs/`，审计记录在 `archive/phases/audit/`。

### 我要了解当前 v1.0 发布边界
→ 读 [archive/phases/deliverables/v1.0-release/](archive/phases/deliverables/v1.0-release/) 和 [archive/phases/specs/phase7/README.md](archive/phases/specs/phase7/README.md)。这些内容已归档，仅用于追溯 v1.0 发布边界。

### 我想理解为什么要这样设计
→ 进入 [adr/](adr/) 目录，先读 [adr/README.md](adr/README.md)，再按编号阅读架构决策记录。

### 我想了解当前系统实际长什么样
→ 进入 [architecture/](architecture/) 目录。读 [architecture/overview.md](architecture/overview.md) 看总体架构，读 [architecture/data-model.md](architecture/data-model.md) 看当前数据库表和关系。

### 我想跑测试
→ 看 [TEST_PROTOCOL.md](TEST_PROTOCOL.md)（通用协议）+ [testing/UX_TEST_SPEC.md](testing/UX_TEST_SPEC.md)（UX 测试规范）。

### 我想配置 SaaS 内置 CLI
→ 看 [user-guides/saas-cli-engine-configuration.md](user-guides/saas-cli-engine-configuration.md)。它面向 SaaS Web 用户，说明 Claude Code、Codex、OpenCode 三个内置 Engine 的 Provider、Base URL、模型、Env Key 和 API Key 怎么填。

---

## 各目录详解

### PRD/ — 产品需求拆解文档

**权威级别**: 最高。PRD 系列与早期核心设计文档共同构成需求权威；早期设计定义产品骨架，PRD 负责拆解、边界收缩和阶段化交付。

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
| ADR-0005 | [0005-target-architecture.md](adr/0005-target-architecture.md) | 整体目标架构：前端、API、应用服务、领域、基础设施、数据持久化六层架构 |
| ADR-0006 | [0006-ai-collaboration-system.md](adr/0006-ai-collaboration-system.md) | AI 协作体系: Rules/Spec/Skill |
| ADR-0007 | [0007-orchestrator-architecture.md](adr/0007-orchestrator-architecture.md) | Orchestrator 架构: Pipeline + DAG |
| ADR-0008 | [0008-revised-development-strategy.md](adr/0008-revised-development-strategy.md) | **🆕** 功能板块制 + Phase 4-7 路线图 |
| ADR-0009 | [0009-project-workspace-model.md](adr/0009-project-workspace-model.md) | **🆕** Project-Workspace 绑定模型 + CLI 适配策略 + 分层渲染 |
| ADR-0010 | [0010-message-level-artifact-experience.md](adr/0010-message-level-artifact-experience.md) | 消息级 Artifact 体验取代 P1 右侧 Drawer |
| ADR-0011 | [0011-agent-engine-skill-model.md](adr/0011-agent-engine-skill-model.md) | **🆕** Agent = Engine + Toolset 建模；调度器作为特殊 Agent 模板 |
| ADR-0012 | [0012-data-persistence-model.md](adr/0012-data-persistence-model.md) | **🆕** 数据持久化模型：SQLite + SQLAlchemy + Project-first 数据结构 |

**阅读建议**: 新成员先读 [adr/README.md](adr/README.md) 了解 ADR 状态。开发者遇到设计疑问时，先查对应 ADR 是否有记录；如果要了解当前实现事实，再看 `architecture/`。

### architecture/ — 当前架构事实

面向开发、答辩和代码导航，解释当前系统实际结构。它回答“现在是什么样”，ADR 回答“为什么这样决定”。

| 文件 | 内容 |
|------|------|
| [README.md](architecture/README.md) | Architecture 文档索引和使用建议 |
| [overview.md](architecture/overview.md) | 当前架构总览、分层结构、主请求链路和本机/云端分流 |
| [data-model.md](architecture/data-model.md) | 当前数据库表组、核心关系、FTS 表和数据设计约束 |
| [runtime-model.md](architecture/runtime-model.md) | 本机 CLI runtime、云端 runtime、Run/Task/Process 状态和审批 |
| [event-contracts.md](architecture/event-contracts.md) | SSE、WebSocket、EventBus 事件类型和新增事件规则 |
| [documentation-governance.md](architecture/documentation-governance.md) | ADR、PRD、Architecture、Archive 等文档边界和更新规则 |

### archive/phases/ — Phase 历史资料归档

所有 Phase 已完成，相关规格、交付快照、开发日志和审计记录统一归档到本目录，不再作为活跃开发入口。

| 目录 | 内容 |
|------|------|
| [archive/phases/specs/](archive/phases/specs/) | Phase 1-16 规格、验收标准和历史 planning 文档 |
| [archive/phases/deliverables/](archive/phases/deliverables/) | 阶段交付快照、实现说明和验收记录 |
| [archive/phases/dev-logs/](archive/phases/dev-logs/) | Phase 开发日志 |
| [archive/phases/audit/](archive/phases/audit/) | 阶段审计和覆盖审计 |

### user-guides/ — 用户手册

面向最终用户，解释产品界面里的关键配置和使用方式，不承载架构决策或 Phase 验收标准。

| 文件 | 内容 |
|------|------|
| [saas-cli-engine-configuration.md](user-guides/saas-cli-engine-configuration.md) | SaaS Web 内置 Claude Code、Codex、OpenCode 三个 CLI Engine 的用户级凭据配置手册 |

### submission/ — 课程/挑战赛提交材料

面向飞书收集表和课程/挑战赛提交，整理为可直接复制到飞书文档的交付材料。该目录只做摘要和导航，深入细节仍以 PRD、ADR、归档 Spec、归档 deliverables 和归档 Dev Log 为权威来源。

| 文件 | 内容 |
|------|------|
| [00-交付总入口.md](submission/00-交付总入口.md) | 表单提交总入口：作品链接、材料导航、课题要求映射和仓库材料索引 |
| [01-产品设计文档.md](submission/01-产品设计文档.md) | 产品定位、用户场景、核心链路、完成度和亮点 |
| [02-技术设计文档.md](submission/02-技术设计文档.md) | 总体架构、CLI Wrapper、Orchestrator、Workspace、Artifact、桌面端和 SaaS |
| [03-AI协作开发记录.md](submission/03-AI协作开发记录.md) | Rules、归档 Spec、历史 Skill、Dev Log、ADR、测试与人工验收闭环 |
| [04-项目答辩核心掌握指南.md](submission/04-项目答辩核心掌握指南.md) | 答辩准备速查：架构选型、核心链路、代码入口、常见追问和演示路线 |

### testing/ — 测试规范

| 文件 | 内容 |
|------|------|
| [UX_TEST_SPEC.md](testing/UX_TEST_SPEC.md) | UX 交互测试：6 状态模型 (空/加载/正常/完成/错误/边界)、Chat 检查清单、P0-P3 缺陷分级 |

### archive/ — 归档文档

`archive/` 表示文档位置归档，不自动代表需求废弃。部分文档仍可能具有权威性，必须以表格中的“当前用途”为准。

| 文件 | 当前用途 | 说明 |
|------|----------|------|
| [AgentHub-多Agent协作平台设计.md](archive/AgentHub-多Agent协作平台设计.md) | 核心启动需求源 | 仍作为 IM、多 Agent 协作、Artifact、预览/编辑/部署、多端协作等产品骨架的权威来源；PRD 系列负责拆解和阶段化，不替代其需求事实 |
| [phases/](archive/phases/) | Phase 历史资料 | Phase 1-16 的规格、交付快照、开发日志和阶段审计均已归档到此目录 |
| Trae.md | 历史参考 | Trae IDE 使用说明，不再维护 |

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
- 项目入口：[README.md](../README.md) — 项目是什么、运行方式、交付入口
