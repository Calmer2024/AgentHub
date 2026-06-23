# AgentHub 文档中心

> 本文档是 `docs/` 目录的总索引。它只索引当前工作区实际存在的文档；已经删除的交付快照、审计报告和陈旧资料不再作为可点击入口保留。

---

## 目录结构

```text
docs/
├── README.md                       ← 本文件
├── documentation-governance.md     ← 文档治理规范
├── GIT_PROTOCOL.md                 ← Git 协作规范
├── TEST_PROTOCOL.md                ← 通用测试协议
├── PRD/                            ← 产品需求拆解文档
├── adr/                            ← 当前保留的架构决策记录
├── architecture/                   ← 当前架构事实
├── submission/                     ← 课程/挑战赛提交材料
├── user-guides/                    ← 面向最终用户的使用与配置手册
├── testing/                        ← 测试规范
└── archive/                        ← 归档文档
    ├── AgentHub-多Agent协作平台设计.md
    ├── adr/                        ← 已从当前 ADR 目录归档的历史决策
    └── phases/                     ← Phase 规格与开发日志归档
```

---

## 快速导航

| 我想了解 | 阅读入口 |
| --- | --- |
| 产品要做什么 | [archive/AgentHub-多Agent协作平台设计.md](archive/AgentHub-多Agent协作平台设计.md) + [PRD/00-Master_Hub.md](PRD/00-Master_Hub.md) |
| 当前系统实际长什么样 | [architecture/README.md](architecture/README.md) |
| 关键架构决策和开发约束是什么 | [adr/README.md](adr/README.md) |
| 文档应该写在哪里、怎么归档 | [documentation-governance.md](documentation-governance.md) |
| 项目现在状态 | [../CONTEXT.md](../CONTEXT.md) |
| 课程/挑战赛提交材料 | [submission/00-交付总入口.md](submission/00-交付总入口.md) |
| 测试与验收规范 | [TEST_PROTOCOL.md](TEST_PROTOCOL.md) + [testing/UX_TEST_SPEC.md](testing/UX_TEST_SPEC.md) |
| SaaS CLI Engine 配置 | [user-guides/saas-cli-engine-configuration.md](user-guides/saas-cli-engine-configuration.md) |

---

## PRD — 产品需求拆解文档

PRD 系列与早期核心设计文档共同构成需求权威。早期设计定义产品骨架，PRD 负责拆解、边界收缩和阶段化交付。

| 文件 | 内容 | 读者 |
| --- | --- | --- |
| [00-Master_Hub.md](PRD/00-Master_Hub.md) | 产品愿景、北极星指标、成功衡量、非目标边界 | 所有人 |
| [01-Architecture_Adapter.md](PRD/01-Architecture_Adapter.md) | CLI Agent 封装、PTY/subprocess、ANSI 清洗、交互拦截 | 架构师、后端 |
| [02-Orchestrator_Engine.md](PRD/02-Orchestrator_Engine.md) | 调度引擎、DAG 拆解、状态机、Human-in-the-loop | 后端、AI 工程师 |
| [03-User_Experience.md](PRD/03-User_Experience.md) | 三栏布局、消息级 Artifact、页面级预览/编辑、审批卡片 | 设计师、前端 |
| [04-Data_API_Contracts.md](PRD/04-Data_API_Contracts.md) | 数据模型和 REST/SSE API 契约 | 全栈开发 |
| [05-End_to_End_Product_Flow.md](PRD/05-End_to_End_Product_Flow.md) | 北极星演示闭环、需求追踪、Artifact 回流、P2 Roadmap | 产品、架构、答辩准备 |
| [06-MVP_Local_Workspace_Delivery.md](PRD/06-MVP_Local_Workspace_Delivery.md) | 本机 workspace、Project 绑定目录、Agent cwd、预览和导出 | 产品、架构、全栈 |
| [07-SaaS_Cloud_Workspace_Delivery.md](PRD/07-SaaS_Cloud_Workspace_Delivery.md) | SaaS 云端 workspace、多租户 sandbox、预览、部署、配额与安全 | 产品、平台工程 |

---

## ADR — 架构决策记录

当前 `docs/adr/` 只保留仍作为活跃阅读入口的 ADR。ADR 记录项目关键架构决策、核心设计和后续开发约束；部分历史 ADR 已移入 [archive/adr/](archive/adr/)，仍可追溯，但默认不作为当前开发入口。

| 编号 | 文件 | 当前用途 |
| --- | --- | --- |
| ADR 索引 | [adr/README.md](adr/README.md) | ADR 状态、治理规则、当前/归档边界 |
| ADR-0001 | [adr/0001-技术栈选型.md](adr/0001-技术栈选型.md) | 技术栈选型 |
| ADR-0002 | [adr/0002-目录结构规范.md](adr/0002-目录结构规范.md) | 项目目录结构规范 |
| ADR-0005 | [adr/0005-目标架构.md](adr/0005-目标架构.md) | 当前整体架构约束 |
| ADR-0007 | [adr/0007-Orchestrator 架构设计.md](adr/0007-Orchestrator%20架构设计.md) | Orchestrator Pipeline、DAG、Plan-first 演进 |
| 历史 ADR | [archive/adr/](archive/adr/) | 已归档的开发方法论、AI 协作、Project-first、Artifact、Agent Profile、持久化等历史决策 |

---

## Architecture — 当前架构事实

`architecture/` 回答“现在系统实际是什么样”。文档治理规范已提升到 [documentation-governance.md](documentation-governance.md)，不再放在 Architecture 目录内。

| 文件 | 内容 |
| --- | --- |
| [architecture/README.md](architecture/README.md) | Architecture 文档索引和使用建议 |
| [architecture/overview.md](architecture/overview.md) | 当前架构总览、分层结构、主请求链路和本机/云端分流 |
| [architecture/data-model.md](architecture/data-model.md) | 当前数据库表组、核心关系、FTS 表和数据设计约束 |
| [architecture/runtime-model.md](architecture/runtime-model.md) | 本机 CLI runtime、云端 runtime、Run/Task/Process 状态和审批 |
| [architecture/event-contracts.md](architecture/event-contracts.md) | SSE、WebSocket、EventBus 事件类型和新增事件规则 |

---

## Phase 归档

Phase 1-16 已完成。删除或收拢后的当前归档只保留规格与开发日志两个可点击入口；旧 `deliverables/`、`audit/`、`planning/` 目录已经从当前工作区移除。

| 目录 | 内容 |
| --- | --- |
| [archive/phases/](archive/phases/) | Phase 归档总入口 |
| [archive/phases/specs/](archive/phases/specs/) | Phase 1-16 规格、验收标准和历史设计 |
| [archive/phases/dev-logs/](archive/phases/dev-logs/) | Phase 开发日志 |

---

## 用户、提交与测试文档

| 目录或文件 | 内容 |
| --- | --- |
| [user-guides/saas-cli-engine-configuration.md](user-guides/saas-cli-engine-configuration.md) | SaaS Web 内置 CLI Engine 凭据配置手册 |
| [submission/00-交付总入口.md](submission/00-交付总入口.md) | 课程/挑战赛交付材料入口 |
| [submission/core-modules/](submission/core-modules/) | 核心功能模块技术文档 |
| [testing/UX_TEST_SPEC.md](testing/UX_TEST_SPEC.md) | UX 交互测试规范 |
| [GIT_PROTOCOL.md](GIT_PROTOCOL.md) | Git 协作规范 |
| [TEST_PROTOCOL.md](TEST_PROTOCOL.md) | 通用测试协议 |

---

## Archive — 归档文档

`archive/` 表示文档位置归档，不自动代表需求废弃。仍具权威性的归档文档必须在索引中说明当前用途。

| 文件或目录 | 当前用途 |
| --- | --- |
| [archive/AgentHub-多Agent协作平台设计.md](archive/AgentHub-多Agent协作平台设计.md) | 核心启动需求源 |
| [archive/adr/](archive/adr/) | 历史 ADR 追溯 |
| [archive/phases/](archive/phases/) | Phase 历史规格和开发日志追溯 |

---

## 相关入口

- 项目入口：[../README.md](../README.md)
- 全局上下文：[../CONTEXT.md](../CONTEXT.md)
- AI 规则：[../CLAUDE.md](../CLAUDE.md)
- 文档治理：[documentation-governance.md](documentation-governance.md)
