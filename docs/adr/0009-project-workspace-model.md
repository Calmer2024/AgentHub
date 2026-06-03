# ADR-0009: Project-Workspace 绑定模型

**Date**: 2026-06-04
**Status**: Accepted

## Context

ADR-0005 和 PRD-06 原始设计将 Workspace 直接绑定到 Session：一个"项目型会话"有一个 workspace_id。但 Phase 6 设计细化中发现这个模型存在根本性缺陷：

- 如果一个 Project 下有多个 Session（如私聊前端 Agent + 私聊后端 Agent + 一个群聊），它们应该共享同一个 workspace 目录。Session 级绑定意味着要么不支持多 Session 共享 workspace（限制了协作能力），要么让多个 Session 指向同一个 workspace（数据模型不一致）。
- 用户的心智模型是"先有项目，再有聊天"，而不是"聊天即项目"。这要求顶层存在一个 Project 实体。

## Decision

### 引入 Project 作为顶层组织实体

```
Project
  ├── name, workspace_path (一对一绑定)
  ├── Sessions[] (一对多：一个 Project 下可有多个私聊/群聊)
  └── 所有 Session 共享同一个 workspace_path
```

### 核心规则

1. **所有聊天必须属于某个 Project**。不存在"无 Project 的聊天"。用户必须先创建/选择 Project，然后在该 Project 下创建私聊或群聊。
2. **一个 Project 绑定一个 workspace 目录**。Project 创建时用户选择/新建目录，此后不可更改。
3. **Project 内所有 Session 共享 workspace**。所有 CLI Agent 进程的 `cwd` 指向 Project 的 `workspace_path`。
4. **同一个 CLI Agent 可在同一 Project 下有多个私聊**（如"前端私聊"和"后端私聊"各一个 Session，都绑 Claude Code Agent）。
5. **MVP 阶段不允许跨 Project 共享 workspace**（降低复杂度）。

### 数据模型调整

```
projects
  ├── id: UUID PK
  ├── name: VARCHAR
  ├── workspace_path: VARCHAR (绝对路径)
  ├── created_at: DATETIME
  └── updated_at: DATETIME

sessions
  ├── ...
  ├── project_id: UUID FK → projects.id (新增，NOT NULL)
  └── workspace_id: 移除（workspace 信息从 Project 获取）
```

### 用户流程

```
首页 Project 列表
  → 新建 Project（命名 + 选择/创建目录）
    → 进入 Project 工作区
      → 创建私聊（选一个 Agent → 创建 Session）
      → 创建群聊（选多个 Agent → 创建 Session）
      → 所有 Agent 的 cwd = Project.workspace_path
```

### 配套决策：CLI 适配器策略

本次 Phase 6 设计细化同时确定了以下配套决策：

**A. CLI 工具由用户在外部安装**
- CLI 工具（`claude`、`codex`、`opencode` 等）由用户在操作系统层面自行安装
- AgentHub 不提供"一键安装 CLI"功能（面向 Persona 1：开发者极客）
- AgentHub 只管理配置：在 AgentPanel 中配置 `executable` 路径、`init_args` 启动参数、环境变量（API Keys 等）

**B. 每个 CLI 工具单独适配**
- 不同 CLI 的输出格式、进度表示、交互模式完全不同
- 为每个 CLI 实现专属 Adapter：`ClaudeCodeAdapter`、`CodexAdapter`、`OpenCodeAdapter`
- 所有 Adapter 实现统一 `BaseAgentAdapter` 接口，产出标准化事件
- 新增 CLI 工具只需写一个新 Adapter

**C. 分层渲染**
- CLI stdout 输出按类型做语义解析，分层渲染到前端：
  - 纯文本 → 聊天消息气泡
  - spinner/进度条 → UI 状态指示条
  - Diff/代码块 → Artifact Card
  - 网页/组件 → Artifact Card（Drawer iframe 预览）
  - 交互式提示（y/n）→ 确认卡片

### 用户完整流程

```
首页 Project 列表
  → 新建 Project（命名 + 选择/创建目录）
    → 进入 Project 工作区
      → 配置 Agent（选择 CLI 工具类型 + executable 路径 + init_args）
      → 创建私聊（选一个 Agent → 创建 Session → CLI cwd = workspace_path）
      → 创建群聊（选多个 Agent → 创建 Session → 所有 CLI cwd = workspace_path）
      → Agent 输出分层渲染到聊天界面
      → 产物自动出现在 Artifact Card 和 Drawer
```

## Consequences

- 需要新增 `projects` 表和 `sessions.project_id` 外键
- 移除 `sessions.workspace_id`（workspace 从 Project 间接获取）
- 前端需要新增 Project 创建/选择流程（在进入聊天之前）
- CLI Agent 的 `cwd` 不再从 Session 获取，而是从 `Session.project.workspace_path` 获取
- `agent_configs` 表需要新增 `executable`、`init_args` 字段（CLI 工具配置）
- 每个 CLI 工具需要一个专属 Adapter 类，实现 `BaseAgentAdapter`
- Adapter 需要实现语义分层解析（区分文本/进度/产物/交互）
- Spec 文档（PRD-01、PRD-06、Phase 6 Specs）需相应更新
