# Phase 8：P1 发布候选收口

**版本**: v1.0
**创建日期**: 2026-06-08
**状态**: Verified
**关联 ADR/PRD**: [AgentHub-多Agent协作平台设计](../../../AgentHub-多Agent协作平台设计.md)、[ADR-0005](../../../../adr/0005-target-architecture.md)、[ADR-0008](../../../../adr/0008-revised-development-strategy.md)、[ADR-0009](../../../../adr/0009-project-workspace-model.md)、[ADR-0010](../../../../adr/0010-message-level-artifact-experience.md)、[PRD-05](../../../../PRD/05-End_to_End_Product_Flow.md)、[PRD-06](../../../../PRD/06-MVP_Local_Workspace_Delivery.md)
**依赖模块**: Phase 6 Workspace Runtime + CLI Engine + Artifact Bridge、Phase 7 Runtime Control + Approval + Health + IM baseline

> 早期的“AgentHub-多Agent协作平台设计”虽然位于 `docs/archive/`，但仍是核心启动需求源。Phase 8 只负责把 P1 桌面版收敛到可发布候选状态，并为 P2 的 Provider 抽象留出接口边界；P2 云端实现拆分到 Phase 9-12。

---

## 1. 目标

Phase 8 解决 P1 仍“可演示但不可发布候选”的问题。目标用户是本地桌面版的真实使用者和项目验收者：他们需要看到真实 CLI Agent 可以在本机 workspace 内稳定完成任务，产物可以构建、预览、编辑、版本化和导出，群聊 Orchestrator 能在审批后继续执行，关键 UI 状态能通过真实服务截图审计。

本阶段不新增 SaaS 能力，而是把 P1 的真实服务证据、交付闭环和架构边界补齐，使后续 Phase 9 可以在不推翻本地实现的情况下引入 Cloud Workspace。

**成功标准**（可证伪）：

- [x] 一条真实服务 E2E 脚本覆盖 Project → 本地 CLI Agent → 文件变更 → Build/Preview/Export → Context Pack → Orchestrator resume；真实 Claude Code 分支通过 `AGENTHUB_PHASE8_REAL_CLI=1` 启用。
- [x] 本地 Project 支持真实构建、构建日志、构建产物预览、源码导出、构建产物导出。
- [x] Reply、Pin、审批恢复、Artifact 继续编辑均通过统一 Context Pack Builder 进入真实 Agent 上下文。
- [x] 群聊 Orchestrator 支持计划、执行、等待审批、审批续跑、失败恢复、最终总结的最小状态机。
- [x] 主要页面和错误/空/加载状态具备 Playwright 截图审计脚本，输出桌面和移动端基线截图。
- [x] 不通过标准：只补静态文档或 UI，不接真实 API/事件/持久化；或把公网一键部署误设为 P1 发布硬门槛。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
Phase 7 v1.0 baseline
  → [Phase 8: 真实 CLI E2E + 本地 Build/Export/Preview + Context/Orchestrator/Store 硬化]
  → Phase 9 Cloud Workspace Foundation
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | Phase 6/7 CLI Runtime: `agent.output`、`agent.process.*`、`artifact.created`、`run.*`、`approval.*` | 消费真实运行事件，沉淀 E2E 证据包和上下文续跑能力 |
| **上游输入** | Project workspace、ArtifactService、MessageService、ApprovalService | 读取文件变更、Artifact 版本、引用消息和审批状态 |
| **下游产出** | Build/Preview/Export API、Context Pack Builder、Orchestrator Plan 状态机 | 被前端 Artifact Card、群聊运行视图、真实服务 E2E 脚本消费 |
| **下游产出** | `WorkspaceProvider` 本地接口边界 | Phase 9 在此基础上增加 `CloudWorkspaceProvider` |
| **本模块不通** | 云端多租户、云端 sandbox、公网一键部署、移动端推送 | Phase 9-12 负责 |

---

## 3. 跨模块契约

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/projects/{projectId}/builds` | POST | `{ "command"?: string, "installCommand"?: string, "artifactPath"?: string }` | `202: { "buildId": string, "status": string }` | `400` workspace 不可写 / `404` project 不存在 / `409` 已有构建运行中 |
| `/api/projects/{projectId}/builds` | GET | 无 | `200: { "items": BuildRun[] }` | `404` |
| `/api/projects/{projectId}/builds/{buildId}` | GET | 无 | `200: BuildRun` | `404` |
| `/api/projects/{projectId}/builds/{buildId}/logs` | GET | 无 | `200: { "chunks": BuildLogChunk[] }` | `404` |
| `/api/projects/{projectId}/exports/source` | GET | 无 | `200: application/zip` | `404` / `409` workspace 仍在写入 |
| `/api/projects/{projectId}/exports/builds/{buildId}` | GET | 无 | `200: application/zip` | `404` / `409` 构建未完成 |
| `/api/projects/{projectId}/previews` | POST | `{ "source": "workspace" \| "build", "path"?: string, "buildId"?: string }` | `200: { "previewId": string, "url": string, "source": string }` | `400` 路径非法 / `404` |
| `/api/sessions/{sessionId}/context-pack` | GET | `purpose` query: `send`/`approval_resume`/`artifact_edit` | `200: ContextPackPreview` | `404` session 不存在 |
| `/api/orchestrator/plans/{planId}/resume` | POST | `{ "approvalId"?: string, "message"?: string }` | `200: OrchestratorPlanView` | `409` 状态不允许 / `404` |

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `build.queued` | BuildService → EventBus | `{ buildId, projectId, command }` |
| `build.log` | BuildService → EventBus | `{ buildId, stream: "stdout" \| "stderr", text, sequence, phase }` |
| `build.completed` | BuildService → EventBus | `{ buildId, projectId, artifactPath, durationMs }` |
| `build.failed` | BuildService → EventBus | `{ buildId, projectId, exitCode, errorSummary }` |
| `preview.created` | PreviewService → EventBus | `{ previewId, projectId, source, url }` |
| `context_pack.created` | ContextPackBuilder → EventBus | `{ contextPackId, sessionId, purpose, messageCount, artifactCount }` |
| `orchestrator.plan.paused` | Orchestrator → EventBus | `{ planId, sessionId, approvalId, currentStepId }` |
| `orchestrator.plan.resumed` | Orchestrator → EventBus | `{ planId, sessionId, resumedFromStepId }` |

### 3.3 数据库 Schema 变更

```sql
CREATE TABLE build_runs (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL REFERENCES projects(id),
  status VARCHAR NOT NULL,
  command TEXT NOT NULL,
  install_command TEXT,
  artifact_path TEXT,
  exit_code INTEGER,
  error_summary TEXT,
  started_at DATETIME,
  finished_at DATETIME,
  created_at DATETIME NOT NULL
);

CREATE TABLE build_logs (
  id VARCHAR PRIMARY KEY,
  build_id VARCHAR NOT NULL REFERENCES build_runs(id),
  sequence INTEGER NOT NULL,
  stream VARCHAR NOT NULL,
  text TEXT NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE TABLE context_pack_snapshots (
  id VARCHAR PRIMARY KEY,
  session_id VARCHAR NOT NULL REFERENCES sessions(id),
  purpose VARCHAR NOT NULL,
  payload_json TEXT NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE TABLE orchestrator_plans (
  id VARCHAR PRIMARY KEY,
  session_id VARCHAR NOT NULL REFERENCES sessions(id),
  status VARCHAR NOT NULL,
  steps_json TEXT NOT NULL,
  current_step_id VARCHAR,
  run_id VARCHAR,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

### 3.4 跨组件 TypeScript 类型（前端）

```typescript
type BuildStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

interface BuildRun {
  id: string
  projectId: string
  status: BuildStatus
  command: string
  artifactPath?: string
  exitCode?: number
  errorSummary?: string
  createdAt: string
  startedAt?: string
  finishedAt?: string
}

interface ContextPackPreview {
  id: string
  sessionId: string
  purpose: 'send' | 'approval_resume' | 'artifact_edit'
  blocks: Array<{ type: string; title: string; tokenEstimate: number }>
  warnings: string[]
}

interface OrchestratorPlanView {
  id: string
  status: 'draft' | 'running' | 'waiting_approval' | 'completed' | 'failed'
  steps: Array<{ id: string; title: string; agentId: string; status: string }>
}
```

---

## 4. 行为规格

### 4.1 正常流程

```
1. 用户创建或选择 Project → 系统确认 workspace 可读写 → 聊天输入可用。
2. 用户在私聊或群聊中发起任务 → CLI Runtime 以 project.workspace_path 为 cwd 执行 → 产生消息和文件变更。
3. Artifact Bridge 捕获文件变更 → 创建消息级 Artifact Card → 用户可打开预览/编辑/版本。
4. 用户点击构建 → BuildService 执行命令并流式记录日志 → build.completed 后 Artifact Card 显示预览和导出入口。
5. 用户触发审批 → Orchestrator Plan 暂停 → Approval Card 显示当前步骤和相关 Artifact。
6. 用户批准 → Context Pack Builder 组合审批、引用、置顶、Artifact 版本和计划状态 → Orchestrator 从暂停点继续。
7. E2E 脚本归档日志、截图、Artifact 快照和 OpenAPI/前端代理验收记录。
```

### 4.2 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** (Empty) | Project 无构建时显示“暂无构建记录”，Artifact Card 只显示预览/编辑基础入口 | 没有 build_runs |
| **加载态** (Loading) | 构建按钮变为进度态，日志区域显示实时输出，导出按钮禁用 | build status = queued/running |
| **正常态** (Normal) | Artifact Card 展示构建状态、预览、编辑、版本、导出；群聊计划显示各步骤状态 | build succeeded 或 plan running |
| **完成态** (Complete) | 构建成功提示、导出可用、E2E 证据包生成路径可见 | build.completed 或 E2E 成功 |
| **错误态** (Error) | 显示错误摘要、日志入口、重试按钮；审批续跑失败时保留原 Approval Card | build.failed / plan resume failed |
| **边界态** (Edge) | 并发构建提示已有任务；超长日志折叠；workspace 路径非法时阻断 | 快速重复点击、超大项目、路径越界 |

### 4.3 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| Project 不存在 | 404 | 项目不存在或已被删除 | 返回项目列表 |
| workspace 不可写 | 400 | 当前工作区不可写，请检查目录权限 | 打开 Project 设置重新选择目录 |
| 构建命令仍在运行 | 409 | 当前项目已有构建任务运行中 | 查看当前构建或取消后重试 |
| 构建失败 | build.failed | 构建失败，查看日志定位错误 | 打开日志、复制错误、重新构建 |
| 导出构建产物时构建未完成 | 409 | 构建完成后才能导出产物 | 等待构建或选择历史成功构建 |
| 审批续跑状态非法 | 400 | 当前任务不能从该审批点继续 | 回到群聊计划或重新发起任务 |

---

## 5. 前端页面设计

### 5.1 页面布局

```text
┌───────────────┬──────────────────┬────────────────────────────────────┐
│ ProjectSidebar │ SessionSidebar   │ ChatWorkspace                      │
│ Project/Agent  │ 会话/群聊列表      │ ┌──────────────────────────────┐   │
│ Health入口      │                  │ │ ChatHeader + Build/Export入口 │   │
│               │                  │ ├──────────────────────────────┤   │
│               │                  │ │ MessageList                   │   │
│               │                  │ │ ArtifactCard + ApprovalCard   │   │
│               │                  │ │ OrchestratorPlanStrip         │   │
│               │                  │ ├──────────────────────────────┤   │
│               │                  │ │ ChatInput                     │   │
│               │                  │ └──────────────────────────────┘   │
└───────────────┴──────────────────┴────────────────────────────────────┘
```

ProjectSidebar 保持当前宽度与滚动规则；SessionSidebar 保持 IM 列表密度；ChatWorkspace 是唯一主工作区。构建日志、Context Pack 预览和 E2E 证据包详情使用页面级 Modal，不嵌套卡片。

### 5.2 组件树

```text
ChatWorkspace
├── ChatHeader
│   └── ArtifactCard actions
├── MessageList
│   ├── MessageBubble[]
│   ├── MessageArtifactStrip
│   │   └── ArtifactCard
│   │       ├── PreviewButton
│   │       ├── BuildButton
│   │       ├── ExportButton
│   │       └── VersionButton
│   ├── ApprovalCard
│   └── OrchestratorPlanStrip
├── BuildLogModal
├── ContextPackPreviewModal
└── ChatInput
```

### 5.3 关键视觉元素

| 元素 | 位置 | 视觉规格 |
|------|------|---------|
| BuildButton | ArtifactCard 右侧操作区 | lucide hammer 图标，32px icon button，running 时显示紧凑 spinner |
| ExportButton | ArtifactCard / ChatHeader | lucide download 图标，下拉菜单含源码 zip、构建产物 zip、日志 |
| BuildLogModal | 页面级 overlay | 80vw max-width，等宽字体日志，stdout/stderr 用细色条区分 |
| OrchestratorPlanStrip | MessageList 中靠近群聊任务消息 | 8px radius，步骤横向或纵向紧凑展示，不使用大卡片嵌套 |
| ContextPackPreviewModal | 开发/诊断入口 | 展示上下文块、token 估算和警告，不暴露密钥 |

---

## 6. 前端交互序列

### 6.1 构建与导出

```
用户: 在 ArtifactCard 点击构建
  → 前端: 调用 POST /api/projects/{projectId}/builds，按钮进入 running
  → 后端: BuildService 执行命令，发布 build.log
  → 前端: BuildLogModal 可准实时查看日志
  → 后端: build.completed
  → 前端: ArtifactCard 显示预览和导出入口，toast 提示构建完成
```

### 6.2 审批续跑

```
用户: 在 ApprovalCard 点击批准
  → 前端: 调用 POST /api/approvals/{id}/approve
  → 后端: ContextPackBuilder 生成 approval_resume 上下文
  → 后端: 调用 POST /api/orchestrator/plans/{planId}/resume 内部流程
  → WebSocket/SSE: orchestrator.plan.resumed + agent.output
  → 前端: OrchestratorPlanStrip 从 waiting_approval 变为 running
```

### 6.3 P1 真实服务证据包

```
用户/CI: 运行 P1 E2E 脚本
  → 脚本: 检查后端 /、/openapi.json、前端 /、/api 代理
  → 脚本: 创建 Project、自定义本地 CLI Agent、Session
  → 脚本: 执行构建、预览、导出、Context Pack、审批续跑
  → 脚本: 可选启用真实 Claude Code 主链路，保存截图审计结果
```

---

## 7. 验收标准

- [x] AC-P8-01: 真实服务 E2E 脚本能在本机启动的前后端服务上跑通 P1 主链路并生成证据包。
- [x] AC-P8-02: `POST /api/projects/{projectId}/builds` 执行真实构建命令，成功后持久化 build_runs 和 build_logs。
- [x] AC-P8-03: 构建日志能通过 API 查询，并在前端实时或准实时展示 stdout/stderr。
- [x] AC-P8-04: 源码 zip 和构建产物 zip 可下载，路径不能越过 Project workspace。
- [x] AC-P8-05: Artifact Card 在构建成功后显示 build preview、源码导出、构建产物导出入口。
- [x] AC-P8-06: Reply、Pin、审批恢复、Artifact 继续编辑生成的 prompt 都来自统一 Context Pack Builder。
- [x] AC-P8-07: 群聊 Orchestrator 审批通过后从原暂停步骤继续，不丢失计划、Agent、Artifact 引用。
- [x] AC-P8-08: Playwright 截图具备桌面/移动基线审计脚本，无 P0/P1 视觉缺陷时返回 0。
- [x] AC-P8-09: 全量回归通过：`pytest backend/test_api/`、`pytest backend/test_unit/`、`npx vitest run`、`npx tsc --noEmit`。
- [x] AC-P8-10: 服务交接流程完成，前端、后端、OpenAPI、`/api` 代理均在真实服务返回 200。

---

## 8. 测试策略

### 8.1 自动化测试

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| `backend/test_api/test_phase8_release_candidate.py` | 5 | 构建成功/失败、日志、build preview、源码/构建导出、路径越界、Context Pack、Orchestrator resume |
| `frontend/src/components/ArtifactCard.test.tsx` | 6 | Artifact 预览、版本、编辑、构建操作、日志弹窗、导出按钮 |
| `frontend/src/api/client.test.ts` | 27 | API client 契约、构建/预览/导出 URL、聊天流解析 |

### 8.2 集成测试

- Project + BuildService + PreviewService：创建临时 workspace，执行测试构建命令，验证 build artifact 和 preview URL。
- Session + ContextPackBuilder + ApprovalService：创建消息、Pin、Artifact、审批，验证审批恢复上下文。
- Orchestrator + CLI Runtime mock：模拟群聊计划暂停与续跑。

### 8.3 E2E 测试

- 真实服务脚本：`python e2e/phase8_release_smoke.py` 覆盖 Project、fixture CLI Agent、Build、Preview、Export、Context Pack、Orchestrator resume。
- 真实 Claude Code 主链路：`AGENTHUB_PHASE8_REAL_CLI=1 python e2e/phase8_release_smoke.py`，要求本地存在启用的 `claude_code` Agent。
- 截图审计：`python e2e/phase8_screenshot_audit.py` 输出桌面和窄屏截图到 `e2e/screenshots/phase8-release-candidate/`。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| CLI Agent 必须以 `Project.workspace_path` 为 cwd | [ADR-0009](../../../../adr/0009-project-workspace-model.md) |
| Artifact 跟随消息级卡片展示，不恢复右侧 Drawer | [ADR-0010](../../../../adr/0010-message-level-artifact-experience.md) |
| Adapter/Runtime 通过事件输出，不直接耦合前端 | [ADR-0005](../../../../adr/0005-target-architecture.md) |
| P1 不把公网一键部署作为硬门槛 | [PRD-00](../../../../PRD/00-Master_Hub.md)、[PRD-06](../../../../PRD/06-MVP_Local_Workspace_Delivery.md) |
| Build/Export/Preview 是 P1 本地交付闭环 | [PRD-06](../../../../PRD/06-MVP_Local_Workspace_Delivery.md) |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 6 Artifact Bridge | `artifact.created`、workspace diff、消息级 Artifact 绑定 | ✅ 已就绪 |
| Phase 7 Runtime Control | run/task/process 状态、取消、恢复 | ✅ 已就绪 |
| Phase 7 Approval | Approval Card、approve/reject API、审批状态 | ✅ 已就绪 |
| Phase 7 IM/UI baseline | 会话列表、消息操作、全屏执行过程、CRUD 提示 | ✅ 已就绪 |
| Phase 9 Cloud Workspace | `CloudWorkspaceProvider` | ❌ 未开始，Phase 8 只定义本地兼容边界 |

---

## 11. Non-Goals（明确不做什么）

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 云端多租户和团队权限 | P2 范围 | Phase 9 |
| 云端 sandbox / microVM 执行 | P2 范围 | Phase 10 |
| 公网 preview URL 和一键部署 | P2 核心能力 | Phase 11 |
| 移动端审批推送、团队协作、PPT Artifact | P2 后续体验 | Phase 12 |
| 裸 HTTP LLM API 作为用户可见 Agent | 违反核心架构 | 永不做 |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| Build API | `POST /api/projects/{id}/build` 仅发布 building 状态 | `POST /api/projects/{id}/builds` 真实执行构建并记录日志 | 保留旧端点一个兼容期，内部转发到新 BuildService |
| Preview API | 静态文件预览为主 | 支持 workspace/build source，返回 previewId/source/url | 旧 previewId 继续可访问，新 UI 使用 `/previews` |
| Context 注入 | Reply/Pin/审批上下文分散 | 统一 Context Pack Builder | 先双写诊断日志，再切换调用方 |
| Orchestrator 状态 | 计划和审批续跑不完整 | 持久化 `orchestrator_plans` 与步骤状态 | 对历史群聊无计划记录时显示 legacy plan unavailable |

> **版本历史**
> - v1.0 (2026-06-08): 按 `SPEC_TEMPLATE.md` 重写为 Phase 8 独立 Spec，P2 细节拆分到 Phase 9-12。
> - v1.1 (2026-06-08): 对齐 Phase 8 实现，记录 Build/Export/Preview、Context Pack、Orchestrator resume、前端 ArtifactCard 操作与 E2E 脚本。

---

## Phase 8 文档审计记录

- 发现问题：上一版 Phase 8 同时承载 P1 收尾和 P2 全量规划，不符合“一个 Phase 一个可验收模块”的规格粒度。
- 已执行修复：Phase 8 只保留 P1 发布候选收口；Cloud Workspace、Sandbox Runtime、Cloud Preview/Deploy、协作多端分别拆入 Phase 9-12。
- 口径确认：`docs/archive/AgentHub-多Agent协作平台设计.md` 仍是核心启动需求源，PRD 系列负责拆解和阶段化。
