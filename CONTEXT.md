# AgentHub 项目上下文

> **这是 AgentHub 项目的全局上下文文档。** 首次参与本项目的开发者/Agent 必须先阅读此文件，建立全局认知后再深入各子文档。
>
> 本项目文档采用**渐进式披露**策略：入口层概述 → 决策层解释 → 规格层定义 → 记录层沉淀。每层总结并向下链接，不跨层复制内容。

---

## 阅读路线

| 顺序 | 文档 | 用途 |
|------|------|------|
| 1 | [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | **新成员首选** — 项目是什么、技术栈、目录结构 |
| 2 | [CONTEXT.md](CONTEXT.md)（本文件） | 领域术语、架构总览、Phase 状态、完整文档索引 |
| 3 | [CLAUDE.md](CLAUDE.md) | AI Agent 行为规则：架构约束、代码规则、禁止事项、Debug 守则 |
| 4 | [docs/PRD/](docs/PRD/) | 产品需求文档（8 篇）— 北极星指标、CLI 适配器、Orchestrator、UX 设计、数据契约、端到端闭环、MVP/SaaS Workspace |
| 5 | [docs/adr/](docs/adr/) | 架构决策记录 — 关键决策及原因 |
| 6 | [docs/specs/](docs/specs/) | 功能规格 — 各 Phase 的具体功能定义与验收标准（Phase 1-7） |

---

## 领域术语表

### 核心概念

- **AgentHub**：多 Agent 协作平台，采用 IM 聊天作为核心交互范式。
- **Engine**：Agent 的底层执行引擎，例如 Claude Code、Codex、OpenCode 或自定义 CLI。Engine 负责真实进程、工具调用、文件读写和 stdout/stderr 输出；Engine 本身不是用户最终调度的 Agent。
- **Skill**：可复用能力定义，包含能力标签、职责说明和 Prompt 片段，例如 `frontend_engineer`、`backend_engineer`、`code_reviewer`、`orchestrator_planner`。Skill 来自全局 Skill Pool，第一版可内置，后续支持目录扫描和用户自定义。
- **Agent / Agent Profile**：用户创建的"AI 联系人"。Agent = Engine + Skills + Context Policy + Runtime Config。比如“前端专家”可以是 Claude Code Engine + `frontend_engineer` 主 Skill + `react/typescript` 辅助 Skill。Agent ≠ 模型厂商，也 ≠ 裸 CLI 工具。
- **CLI Adapter**：底层执行适配器，每个 CLI 工具单独适配（`ClaudeCodeAdapter`、`CodexAdapter`、`OpenCodeAdapter`），各自理解该 CLI 的特定输出格式。Adapter 通过 PTY/subprocess 孵化进程、读取 stdout/stderr、做语义分层解析（文本→聊天消息、进度指示器→状态条、Diff/代码块→Artifact Card）、ANSI 清洗、交互式提示（y/n）拦截。Adapter 把 CLI 输出转为标准事件（`agent.output` / `artifact.detected` / `interactive_prompt`）。CLI 工具由用户在外部安装，AgentHub 只管理配置（executable 路径、init_args、env vars）。DeepSeek 仅作为系统模型用于中枢总结、标题生成和产物编辑辅助，不作为用户可聊天 Agent。
- **Orchestrator Agent**：绑定 `orchestrator_planner` Skill 的特殊 Agent Profile，负责意图分析、任务拆解、DAG/Plan 生成和 Agent 分配建议。它本质上也是 Agent 的一种，第一版先产出计划，不直接执行子 Agent。
- **Scheduler / Executor**：读取 Orchestrator Agent 产出的 Plan/DAG，校验依赖关系，并启动对应 Agent Profile 的后端服务。它是执行机制，不是一个用户可聊天 Agent。
- **Project（项目）**：AgentHub 的顶层组织实体。用户必须先创建 Project（新建空白文件夹，或通过系统原生目录选择器选择已有文件夹），然后在该 Project 下创建任意数量的私聊或群聊 Session。一个 Project 绑定一个 workspace 目录，Project 内所有 Session 共享此目录。所有聊天必须属于某个 Project，不存在"无 Project 的聊天"。详见 [ADR-0009](docs/adr/0009-project-workspace-model.md)。
- **Workspace**：Project 绑定的物理或云端工作目录。MVP 版是本机 `workspace_path`（Project 创建时指定）；Project 内所有 CLI Agent 以该路径作为 `cwd` 执行。SaaS 版是云端隔离 workspace，由 sandbox/runner 挂载。详见 [PRD-06](docs/PRD/06-MVP_Local_Workspace_Delivery.md) 和 [PRD-07](docs/PRD/07-SaaS_Cloud_Workspace_Delivery.md)。
- **单聊模式**：在某个 Project 下，1v1 与单个 Agent 的私聊 Session。该 Agent 以 Project 的 `workspace_path` 为 `cwd` 执行。
- **群聊模式**：在某个 Project 下，包含多个 Agent Profile 的对话 Session，支持 @ 指定，Orchestrator Agent 自动协调分工。所有 Agent 共享 Project 的 `workspace_path`。
- **分层渲染**：CLI Adapter 对 stdout 输出做语义解析，按类型分层渲染到前端：纯文本 → 聊天消息气泡；spinner/进度条 → UI 状态指示条（如 `🔧 正在修改文件...`）；Diff/代码块 → Artifact Card；交互式提示 → 确认卡片。不同 CLI 的输出格式由其专属 Adapter 解析。
- **链式协作**：多 Agent 按阶段顺序协作（规划→执行→审查→综合），由 Orchestrator 自动触发，动态分配角色。
- **协作角色**：6 种模板角色 — planner / executor / reviewer / researcher / synthesizer / critic。Phase 3 模板驱动，未来可升级 LLM 动态分配。
- **协作 DAG**：有向无环图，描述一次协作中 Phase 间的依赖关系。Phase 间串行，Phase 内可并行。
- **共享上下文 (SharedContext)**：所有 Agent 可读的对话历史，Agent 完成后其产出自动追加。链式依赖的 Agent 额外接收前驱产出的定向注入。
- **引用消息**：用户显式点选某条历史消息后发出的当前消息。引用必须保存 `parentMessageId` + `metadata.replyReference` 快照，并在 Agent prompt 中注入 `[Reply context]` 块——仅显示引用卡片不算完成。
- **Pin 消息**：用户固定的关键历史消息。Phase 4 起由 ContextManager 在单聊与群聊中以 `[Pinned message]` 长期上下文块优先注入——仅显示 Pin 标记不算完成。
- **中枢总结**：Orchestrator 在 DAG/chain 等多 Agent 结构化协作完成后生成的系统整理消息。由系统模型（DeepSeek）生成，独立于普通工程 Agent Profile。
- **CollaborationPanel**：前端 DAG 可视化面板，展示协作流程的各 Phase 及其实时状态。
- **产物 (Artifact)**：Agent 生成的富媒体内容，类型包括 `code_diff`、`web_preview`、`document`、`file_tree`。Phase 5 已完成已有 Artifact 的版本历史、Diff 和在线编辑；Phase 6/7 负责补齐 Agent 输出入口、Artifact Card、Drawer 预览和审批回流。
- **Artifact Card**：聊天流中的产物卡片，由标准 `artifact.created` 事件驱动，绑定 `artifact_id / message_id / task_id / version`，不是前端临时扫描 Markdown 得到的装饰。
- **Artifact Drawer**：右侧产物抽屉。统一承载聊天卡片、会话产物列表、审批卡片打开后的预览、Diff、版本切换和局部编辑。
- **北极星链路**：AgentHub MVP 必须打通的端到端链路：创建 Project + 绑定 workspace → 在 Project 下创建私聊/群聊 → 用户输入 → Orchestrator/Agent 执行 → Agent 读写 workspace → Artifact 创建 → 聊天流 Artifact Card → Drawer 预览 → 局部编辑/版本化 → 审批继续调度 → 中枢总结。权威定义见 [PRD-05](docs/PRD/05-End_to_End_Product_Flow.md)。

### 方法论术语

- **Vibe Coding**：以探索式、边想边写的方式快速开发，不追求过早的完整详细设计。
- **Walking Skeleton**：贯穿所有架构层的最薄可运行实现，验证全链路可行（来源：Alistair Cockburn）。
- **Architectural Runway**：只为你近期要飞过的跑道铺路，不为远期需求过早投资（来源：SAFe）。
- **Incremental Delivery**：每次迭代产出可演示的完整功能切片，而非零散功能点堆积。
- **功能板块制**：Phase 4 起采用的新开发策略。每个 Phase = 一个独立功能板块，板块内做到 PRD 级完整后才进入下一板块。详见 [ADR-0008](docs/adr/0008-revised-development-strategy.md)。

---

## 目标架构（7 层）

```
前端 (React + shadcn/ui + Zustand)
  → API 网关 (FastAPI REST + WebSocket Manager)
    → 业务逻辑 (Session / Message / Artifact Services)
      → 领域核心 (Orchestrator / ContextManager)
        → 基础设施 (CLI Agent Adapters / EventBus / File Storage)
          → 数据持久化 (SQLAlchemy Models / Configuration Store)
```

**核心规则**：架构按需增长。Day 1（Phase 1）仅实现 3 层。复杂度达到触发条件时才引入新层——见 ADR-0004。

---

## 开发阶段

### Phase 总览

| Phase | 名称 | 状态 | 核心交付 |
|-------|------|------|---------|
| **Phase 0** | 准备期 | ✅ | 接口契约、目标架构、骨架定义、优先级矩阵 |
| **Phase 1** | Walking Skeleton | ✅ | 单聊全链路：前端 → API → Agent → SQLite，流式对话 |
| **Phase 2** | Core Features | ✅ | 多 Agent、群聊 + Orchestrator v1、WebSocket、产物基础 |
| **Phase 3** | Orchestrator + 基础设施 | ✅ | EventBus、Orchestrator v2（Pipeline + DAG + 6 角色）、CollaborationPanel |
| **Phase 4** | 消息交互闭环 | ✅ | Reply / Regenerate / Pin、FTS5 全文搜索、Reply/Pin prompt 注入 |
| **Phase 5** | 产物工作台能力 | ✅ | 版本链 + Diff + 在线编辑（Tool Calling）；上游产物生成入口由 Phase 6/7 补齐 |
| **Phase 6** | Workspace Runtime + CLI 适配器 + 产物入口桥接 | 🚧 | 6A Workspace Runtime 已验收；6B-6E CLI Adapter 基线已落地；Orchestrator Plan-first 真实执行已阶段性通过：用户批准 draft plan 后可创建 execution，Scheduler 按 DAG 调度真实 CLI Agent 写入 workspace，并将 Agent 气泡、任务结果、executionTrace 落库。下一步是合并队友功能后打磨语言继承、trace 分层、消息瘦身、文件噪音过滤、取消/中断验收与 Artifact Bridge |
| **Phase 7** | UX 体验闭环 + MVP 演示闭环 | 📋 | 三栏动态布局、产物抽屉、审批卡片、环境体检，跑通全链路 |

Phase 4-7 采用**功能板块制**：每板块独立完整交付。板块间按用户可感知价值排序。详见 [ADR-0008](docs/adr/0008-revised-development-strategy.md)。

### 产品交付阶段

| 优先级 | 产品形态 | 工作区位置 | Agent CLI 运行位置 | 部署 |
|--------|---------|-----------|-------------------|------|
| **P1（当前）** | **桌面版** — Web UI + 本地无头服务器（Tauri/Node.js 进程作为本地特权执行引擎） | 本机文件系统 | 用户主机 | ❌ 不支持一键部署 |
| **P2（远期）** | **SaaS 云版** — Web UI + 云端后端 + 云端沙箱 | 云端隔离沙箱 | 云端容器 | ✅ 一键部署到云端 URL |

**P1 数据流**：`用户浏览器 → localhost 后端 → 本机文件系统 + 本机 CLI Agent 进程`

**P2 数据流**：`用户浏览器 → 云端后端 → 云端沙箱 + 云端 CLI Agent 进程 → 一键部署`

桌面版（P1）的核心特征：Web 端是主力 UI，所有 API 调用指向本地桌面端后端；桌面端是"特权层"——拥有文件系统访问权、能 spawn CLI 进程。数据和 Agent 执行都在本机闭环。

### Project-first 工作流

用户必须先创建 Project（新建空白 workspace 目录，或通过系统目录选择器选择已有目录），然后在 Project 下创建私聊或群聊。所有聊天必须属于某个 Project。Project 不再暴露“静态网页 / Vite React / 已有项目”等用户可选属性；Project 内所有 Agent 共享 `Project.workspace_path` 作为 `cwd`。详见 [ADR-0009](docs/adr/0009-project-workspace-model.md)。

---

## 核心原则

1. **架构按需增长** — 不在 Day 1 构建全部 7 层（ADR-0004）。
2. **接口先于实现** — 先定义契约，实现可自由迭代（ADR-0005）。
3. **每个增量可演示** — 不允许"后端完成但前端未接通"的中间态。
4. **自动化优先** — 复杂决策（链式触发、角色分配、Agent 选择）由后端自动完成，不暴露为前端配置项。
5. **功能板块完整交付** — 每个板块所有子模块（后端 + 前端 + 测试）达到 PRD 级完整后，才进入下一板块。严禁"所有板块都碰一点"（ADR-0008，Phase 4 起执行）。
6. **每个架构决策记录为 ADR** — 包含：为什么现在做、考虑了哪些替代方案。

> 行为规则（代码规范、禁止事项、Debug 守则、文档修改规则）见 [CLAUDE.md](CLAUDE.md)，此处不重复。

---

## 文档索引

### PRD — 产品需求文档（最高权威）

| 文档 | 内容 |
|------|------|
| [00-Master_Hub](docs/PRD/00-Master_Hub.md) | **PRD 总览**：北极星指标、产品愿景、成功衡量、非目标边界、P1/P2 交付阶段 |
| [01-Architecture_Adapter](docs/PRD/01-Architecture_Adapter.md) | CLI 适配器设计：PTY/subprocess、ANSI 清洗、Per-CLI 适配策略、分层渲染 |
| [02-Orchestrator_Engine](docs/PRD/02-Orchestrator_Engine.md) | 调度引擎：DAG 拆解、状态机、Human-in-the-loop |
| [03-User_Experience](docs/PRD/03-User_Experience.md) | 交互设计：三栏布局、资产卡片、产物抽屉、审批卡片 |
| [04-Data_API_Contracts](docs/PRD/04-Data_API_Contracts.md) | 数据模型：projects / agents / sessions / messages / tasks，REST/SSE API |
| [05-End_to_End_Product_Flow](docs/PRD/05-End_to_End_Product_Flow.md) | 端到端产品闭环：需求追踪矩阵、Workspace + Artifact 链路、Phase 责任矩阵 |
| [06-MVP_Local_Workspace_Delivery](docs/PRD/06-MVP_Local_Workspace_Delivery.md) | MVP 本机 workspace：Project 绑定目录、Agent cwd、文件变更、预览、导出 |
| [07-SaaS_Cloud_Workspace_Delivery](docs/PRD/07-SaaS_Cloud_Workspace_Delivery.md) | SaaS 云端 workspace：云端 sandbox、preview URL、多租户隔离、一键部署 |

### ADR — 架构决策记录

| 编号 | 文件 | 决策 |
|------|------|------|
| ADR-0001 | [0001-tech-stack-selection.md](docs/adr/0001-tech-stack-selection.md) | 技术栈选型：React / FastAPI / SQLite |
| ADR-0002 | [0002-directory-structure.md](docs/adr/0002-directory-structure.md) | 项目目录结构规范 |
| ADR-0003 | [0003-vibe-coding-philosophy.md](docs/adr/0003-vibe-coding-philosophy.md) | 结构化 Vibe Coding 模式 |
| ADR-0004 | [0004-development-methodology.md](docs/adr/0004-development-methodology.md) | 架构跑道 + 行走骨架 + 增量交付 |
| ADR-0005 | [0005-target-architecture.md](docs/adr/0005-target-architecture.md) | 7 层目标架构 + CLI Wrapper 接口契约 |
| ADR-0006 | [0006-ai-collaboration-system.md](docs/adr/0006-ai-collaboration-system.md) | AI 协作体系：Rules / Spec / Skill 三层沉淀 |
| ADR-0007 | [0007-orchestrator-architecture.md](docs/adr/0007-orchestrator-architecture.md) | Orchestrator 架构：Pipeline 四阶段 + DAG |
| ADR-0008 | [0008-revised-development-strategy.md](docs/adr/0008-revised-development-strategy.md) | 功能板块制 + Phase 4-7 路线图 + 文档治理 |
| ADR-0009 | [0009-project-workspace-model.md](docs/adr/0009-project-workspace-model.md) | **🆕** Project-Workspace 模型 + CLI 适配策略 + 分层渲染 |
| ADR-0010 | [0010-agent-engine-skill-model.md](docs/adr/0010-agent-engine-skill-model.md) | **🆕** Agent = Engine + Skills 建模；调度器作为特殊 Agent |

### Specs — 功能规格（按 Phase）

| Phase | 目录 | 核心文档 |
|-------|------|---------|
| Phase 1 | [specs/phase1/](docs/specs/phase1/) | [01-skeleton-spec.md](docs/specs/phase1/01-skeleton-spec.md) |
| Phase 2 | [specs/phase2/](docs/specs/phase2/) | [01-core-features-spec.md](docs/specs/phase2/01-core-features-spec.md) |
| Phase 3 | [specs/phase3/](docs/specs/phase3/) | [README](docs/specs/phase3/README.md) + [Orchestrator 文档集](docs/specs/phase3/02-orchestrator/README.md)，含 [真实 Agent 执行复盘](docs/specs/phase3/02-orchestrator/10-real-agent-execution/README.md) |
| Phase 4 | [specs/phase4/](docs/specs/phase4/) | [README](docs/specs/phase4/README.md) + 消息操作 + 搜索 |
| Phase 5 | [specs/phase5/](docs/specs/phase5/) | [README](docs/specs/phase5/README.md) + [版本/Diff](docs/specs/phase5/01-artifact-versioning.md) + [在线编辑](docs/specs/phase5/02-artifact-editing.md) |
| Phase 6 | [specs/phase6/](docs/specs/phase6/) | [README](docs/specs/phase6/README.md) + [Workspace Runtime](docs/specs/phase6/00-workspace-runtime.md) + [CLI 适配器](docs/specs/phase6/01-cli-adapter.md) + [产物桥接](docs/specs/phase6/02-artifact-output-bridge.md) + [Agent Profile](docs/specs/phase6/03-agent-engine-skill-profile.md) |
| Phase 7 | [specs/phase7/](docs/specs/phase7/) | [README](docs/specs/phase7/README.md) + Drawer + 审批 + 环境体检 + Store 收尾 |
| 模板 | [SPEC_TEMPLATE.md](docs/specs/SPEC_TEMPLATE.md) | 新建模块 Spec 的标准模板 |
| 历史 | [specs/planning/](docs/specs/planning/) | 旧规划文档（参考） |

### 审计与日志

| 文档 | 内容 |
|------|------|
| [Phase 3 审计报告](docs/audit/phase3-audit-report.md) | PRD 符合性矩阵、架构偏离分析、模块完成度、文档债 |
| [PRD/Spec 覆盖审计](docs/audit/prd-spec-coverage-audit.md) | 启动文档 → PRD → Spec 覆盖审计 |
| [Git 协议](docs/GIT_PROTOCOL.md) | 分支策略（phase/main 唯一集成分支）、Commit 格式、AI 提交规则 |
| [测试协议](docs/TEST_PROTOCOL.md) | 测试金字塔、工具链、环境、Bug 修复流程 |
| [UX 测试规范](docs/testing/UX_TEST_SPEC.md) | UX 交互体验：6 状态模型、检查清单、P0-P3 分级 |
| [Phase 1 Dev Log](docs/dev-logs/phase1-dev-log.md) | Phase 1 时间线、Bug 与教训 |
| [Phase 2 Dev Log](docs/dev-logs/phase2-dev-log.md) | Phase 2 时间线、Bug 与教训 |
| [Phase 3 Dev Log](docs/dev-logs/phase3-dev-log.md) | Phase 3 时间线、Bug 与教训、架构决策时间线 |
| [Phase 4 Dev Log](docs/dev-logs/phase4-dev-log.md) | Phase 4 实现摘要、FTS5 修复、真实 UI 验收记录 |
| [Phase 5 Dev Log](docs/dev-logs/phase5-dev-log.md) | Phase 5 产物版本链、Diff、在线编辑、架构收拢与真实 HTTP 验收 |
| [Phase 6 Dev Log](docs/dev-logs/phase6-dev-log.md) | Phase 6A Project-first workspace runtime、系统目录选择器、人工验收记录 |
| [Orchestrator 真实 Agent 执行复盘](docs/specs/phase3/02-orchestrator/10-real-agent-execution/README.md) | 2026-06-06 真实 CLI Agent DAG 执行样本、问题清单、合并后续计划 |

### Skills — AI 能力复用

| Skill | 文件 | 用途 |
|-------|------|------|
| agenthub-module-dev | `.claude/skills/agenthub-module-dev/SKILL.md` | 标准模块开发流程 |
| agenthub-code-review | `.claude/skills/agenthub-code-review/SKILL.md` | 标准代码审查 |
| agenthub-phase-wrapup | `.claude/skills/agenthub-phase-wrapup/SKILL.md` | Phase 收尾流程 |
| agenthub-qa-audit | `.claude/skills/agenthub-qa-audit/SKILL.md` | 企业级质量审计 |

---

## 文档治理

1. **Phase 结束时审计** — 检查所有 `docs/` 下的交叉引用是否有效。
2. **ADR 编号与文件名一致** — `NNNN-title.md` 内部标题必须是 `ADR-NNNN`。
3. **Spec 文件必须被索引** — 不被本文件索引的 Spec = 无效文档。
4. **旧文档立即归档或删除** — 不再适用的文档移入 `docs/archive/`。
5. **一个事实一个权威源** — 同一信息不出现在两个地方。引用用链接，不复制。
