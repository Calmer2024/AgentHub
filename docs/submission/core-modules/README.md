# 核心功能模块技术文档索引

> 本目录提取 AgentHub 最核心的功能模块，并分别说明当前实现的核心逻辑、架构设计和关键代码入口。它是提交材料中的技术模块说明集，配合 `../02-技术设计文档.md` 阅读。

## 核心模块清单

| 模块 | 文档 | 核心价值 |
| --- | --- | --- |
| Project 与 IM 会话系统 | [01-project-and-im-session.md](01-project-and-im-session.md) | 建立 Project-first 工作流，把项目、会话、消息和 workspace 统一到一个协作上下文。 |
| Agent Profile 与 CLI Runtime | [02-agent-profile-and-cli-runtime.md](02-agent-profile-and-cli-runtime.md) | 把 Claude Code、Codex、OpenCode 等真实 CLI 工具封装成可聊天、可执行、可观测的 Agent。 |
| Orchestrator 多 Agent 调度 | [03-orchestrator-collaboration.md](03-orchestrator-collaboration.md) | 将用户目标拆解为计划、DAG 和 Agent 分工，驱动群聊协作执行。 |
| Workspace 与 Run 状态管理 | [04-workspace-and-run-state.md](04-workspace-and-run-state.md) | 管理本机/云端 workspace、运行状态、任务状态和进程生命周期。 |
| Artifact 产物链路 | [05-artifact-pipeline.md](05-artifact-pipeline.md) | 将 Agent 输出、文件变化、代码块和预览链接沉淀为消息级 Artifact。 |
| 审批与人工控制 | [06-human-in-the-loop.md](06-human-in-the-loop.md) | 支持任务暂停、审批、驳回、续跑、取消和交互式 CLI 提示。 |
| SaaS 云端协作与部署 | [07-saas-cloud-and-deployment.md](07-saas-cloud-and-deployment.md) | 承接团队、租户、云端 workspace、sandbox runtime、preview 和 deployment。 |
| 多端产品壳与权限安全 | [08-multi-shell-auth-security.md](08-multi-shell-auth-security.md) | 支撑 Local Desktop、SaaS Web、Mobile 三端入口，以及 Auth、TenantScope、RBAC、安全边界。 |

## 模块划分依据

这 8 个模块来自项目当前核心链路：

```text
创建 Project
  -> 创建单聊 / 群聊
  -> 选择 Agent Profile
  -> CLI Runtime 或云端 Runtime 执行
  -> Orchestrator 计划 / DAG / 调度
  -> Run / Task / Process 状态推进
  -> Artifact 创建、预览、编辑、版本化
  -> 审批、续跑、部署和多端访问
```

这些模块覆盖了 AgentHub 区别于普通聊天应用的核心技术：真实 CLI Agent 接入、Project workspace、Orchestrator 多 Agent 调度、消息级 Artifact 回流、本机桌面执行和 SaaS 云端扩展。

## 相关总览文档

| 文档 | 作用 |
| --- | --- |
| [../02-技术设计文档.md](../02-技术设计文档.md) | 提交材料中的整体技术设计说明。 |
| [../../architecture/overview.md](../../architecture/overview.md) | 当前系统六层架构事实和主链路。 |
| [../../architecture/data-model.md](../../architecture/data-model.md) | 当前数据库表组和数据设计约束。 |
| [../../architecture/runtime-model.md](../../architecture/runtime-model.md) | Runtime、Run、Task、Process 状态模型。 |
| [../../architecture/event-contracts.md](../../architecture/event-contracts.md) | SSE、WebSocket、EventBus 事件导航。 |
| [../../adr/0005-目标架构.md](../../adr/0005-目标架构.md) | 整体架构约束。 |
| [../../adr/0007-Orchestrator%20架构设计.md](../../adr/0007-Orchestrator%20架构设计.md) | Orchestrator 架构决策与约束。 |
