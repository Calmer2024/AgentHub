# Phase 10：Sandbox Runner 与云端 Agent Runtime

**版本**: v1.1
**创建日期**: 2026-06-08
**状态**: Completed
**关联 ADR/PRD**: [AgentHub-多Agent协作平台设计](../../../AgentHub-多Agent协作平台设计.md)、[ADR-0005](../../../../adr/0005-目标架构.md)、[ADR-0009](../../../../archive/adr/0009-project-workspace-model.md)、[PRD-01](../../../../PRD/01-Architecture_Adapter.md)、[PRD-02](../../../../PRD/02-Orchestrator_Engine.md)、[PRD-07](../../../../PRD/07-SaaS_Cloud_Workspace_Delivery.md)
**依赖模块**: Phase 9 Cloud Workspace Foundation、Phase 6/7 CLI Runtime contract、Phase 8 Context Pack/Orchestrator hardening

> Phase 10 把 P1 的本机 CLI Runtime 迁移到云端隔离 sandbox。它必须保持 CLI 事件契约兼容，让前端和 Orchestrator 不需要关心 Agent 在本机还是云端运行。

---

## 1. 目标

Phase 10 解决 P2 的真实执行问题：云端 Project 有 workspace 后，必须能在隔离环境中运行 Claude Code、Codex、OpenCode 等真实 CLI Agent，并把 stdout/stderr、交互提示、文件变更、Artifact 检测、取消/恢复事件回传到现有聊天流。

目标用户是 SaaS 版使用者和平台运维者。用户需要可靠的云端 Agent 执行体验；平台需要多租户隔离、资源配额、secret 注入、日志脱敏、空闲回收和故障可诊断性。

**成功标准**（可证伪）：

- [x] 云端 sandbox 可以挂载 Phase 9 workspace，执行真实 CLI Agent 并修改文件。
- [x] 前端接收的 `agent.output`、`agent.process.*`、`artifact.created`、`approval.*` 与 P1 事件契约兼容。
- [x] 运行取消能终止 sandbox 内 CLI 进程，并持久化 cancelled 状态。
- [x] CPU、内存、磁盘、运行时长、并发数、网络策略至少有最小配额控制。
- [x] secret 只在 sandbox 内按需注入，日志和事件中不出现原始 secret 值。
- [x] P1 本机 CLI runtime、会话级常驻进程、Artifact Bridge 和运行取消不因 cloud runtime 引入而回归。
- [x] 本阶段 SaaS 最小可运行切片为：cloud Project → 创建 run → sandbox ready → 真实 CLI 输出标准事件 → Artifact Card 或 run 终态。
- [x] 不通过标准：云端 Agent 通过裸 HTTP LLM API 假装执行，或 sandbox 间可互相读写 workspace。

**实现说明**：Phase 10 已交付可替换 runner 切片。当前开发实现把 `cloud://agenthub/workspaces/{workspaceId}` 映射到 `data/workspaces/.cloud-workspaces/{workspaceId}` 的隔离目录，并通过真实 subprocess/CLI Adapter 执行 Agent；不是最终生产 Docker/microVM，但 API、DB、SSE、Artifact、Secret、Quota 和前端契约已按云端 runtime 形态落地。旧交付快照目录已在 2026-06-22 文档整理中删除，当前追溯入口为本文与 [Phase 10 Dev Log](../../dev-logs/phase10-dev-log.md)。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
Phase 9 Cloud Workspace
  → [Phase 10: Sandbox lifecycle + CloudAgentRuntime + quota/secret/isolation]
  → Phase 11 Cloud Preview + Deployment
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | `workspaceId`、ContextPack、Agent Profile、Orchestrator Plan | 为一次 run 分配 sandbox 并启动真实 CLI |
| **上游输入** | Phase 9 RBAC、SecretProvider、QuotaPolicy | 校验执行权限、注入 secret、限制资源 |
| **下游产出** | `agent.output`、`agent.process.*`、`artifact.detected`、`run.*` | 前端聊天流、Artifact Bridge、运行控制消费 |
| **下游产出** | workspace diff、build-ready artifact | Phase 11 preview/deploy 消费 |
| **本模块不通** | 公网 preview URL、部署发布、团队评论和移动端通知 | Phase 11-12 负责 |

### 2.3 双运行时兼容门禁

Phase 10 引入 cloud runtime，但 local runtime 仍是 P1 桌面版的主路径：

- `/api/sessions/{sessionId}/runs` 必须显式接受 `runtime = "local" | "cloud"`；不传或本机环境默认选择 local，不得自动强制 cloud。
- `runtimeMode = "cloud"` 可以返回 `sandboxId`；`runtimeMode = "local"` 的响应和 Store 状态不能要求存在 `sandboxId`。
- `agent.output`、`artifact.detected`、`approval.*`、`run.*` 事件必须继续使用统一契约，前端 MessageList 和 Artifact Card 不分叉实现。
- 阶段完成报告必须同时列出 P1 local runtime 回归结果和 Phase 10 cloud runtime 真实服务结果。

---

## 3. 跨模块契约

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/sandboxes` | POST | `{ "workspaceId": string, "image": string, "ttlSeconds"?: number }` | `201: Sandbox` | `403` / `409` 配额不足 |
| `/api/sandboxes/{sandboxId}` | GET | 无 | `200: Sandbox` | `403` / `404` |
| `/api/sandboxes/{sandboxId}/stop` | POST | `{ "reason"?: string }` | `202: { "status": "stopping" }` | `404` / `409` |
| `/api/sessions/{sessionId}/runs` | POST | `{ "agentId": string, "messageId": string, "runtime": "local" \| "cloud" }` | `202: { "runId": string, "sandboxId"?: string }` | `400` / `403` / `409` |
| `/api/runs/{runId}/cancel` | POST | `{ "reason"?: string }` | `202: { "runId": string, "status": "cancelling" }` | `404` / `409` |
| `/api/runs/{runId}/logs` | GET | 无 | `200: { "chunks": RuntimeLogChunk[] }` | `403` / `404` |
| `/api/secrets` | POST | `{ "name": string, "value": string, "scope": "user" \| "team" \| "project" }` | `201: SecretRef` | `400` / `403` |
| `/api/quotas/me` | GET | 无 | `200: QuotaSummary` | `401` |

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `sandbox.created` | SandboxRunner → EventBus | `{ sandboxId, workspaceId, image, ttlSeconds }` |
| `sandbox.ready` | SandboxRunner → EventBus | `{ sandboxId, workspaceId, mountPath }` |
| `sandbox.resource.updated` | SandboxRunner → EventBus | `{ sandboxId, cpuMs, memoryMb, diskMb }` |
| `sandbox.stopped` | SandboxRunner → EventBus | `{ sandboxId, reason, exitCode? }` |
| `agent.process.started` | CloudAgentRuntime → EventBus | `{ runId, sandboxId, agentId, pid? }` |
| `agent.output` | CloudAgentRuntime → EventBus | `{ runId, sessionId, agentId, text, sequence }` |
| `interactive_prompt` | CloudAgentRuntime → EventBus | `{ runId, promptId, promptType, text }` |
| `artifact.detected` | ArtifactDetector → EventBus | `{ runId, sessionId, messageId, artifactType, path? }` |
| `quota.exceeded` | QuotaService → EventBus | `{ userId, teamId?, quotaType, limit, observed }` |

### 3.3 数据库 Schema 变更

```sql
CREATE TABLE sandboxes (
  id VARCHAR PRIMARY KEY,
  workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
  status VARCHAR NOT NULL,
  image VARCHAR NOT NULL,
  runner_node_id VARCHAR,
  resource_limits_json TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  stopped_at DATETIME
);

CREATE TABLE runtime_runs (
  id VARCHAR PRIMARY KEY,
  session_id VARCHAR NOT NULL REFERENCES sessions(id),
  agent_id VARCHAR NOT NULL REFERENCES agent_configs(id),
  sandbox_id VARCHAR REFERENCES sandboxes(id),
  runtime_mode VARCHAR NOT NULL,
  status VARCHAR NOT NULL,
  started_at DATETIME,
  finished_at DATETIME,
  error_summary TEXT
);

CREATE TABLE runtime_logs (
  id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL REFERENCES runtime_runs(id),
  sequence INTEGER NOT NULL,
  stream VARCHAR NOT NULL,
  text TEXT NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE TABLE secrets (
  id VARCHAR PRIMARY KEY,
  scope VARCHAR NOT NULL,
  owner_id VARCHAR NOT NULL,
  name VARCHAR NOT NULL,
  encrypted_value TEXT NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE TABLE quota_usages (
  id VARCHAR PRIMARY KEY,
  subject_type VARCHAR NOT NULL,
  subject_id VARCHAR NOT NULL,
  quota_type VARCHAR NOT NULL,
  used INTEGER NOT NULL,
  limit_value INTEGER NOT NULL,
  window_started_at DATETIME NOT NULL
);
```

### 3.4 跨组件 TypeScript 类型（前端）

```typescript
type SandboxStatus = 'creating' | 'ready' | 'running' | 'stopping' | 'stopped' | 'failed'

interface Sandbox {
  id: string
  workspaceId: string
  status: SandboxStatus
  image: string
  createdAt: string
  stoppedAt?: string
}

interface CloudRun {
  id: string
  sessionId: string
  agentId: string
  runtimeMode: 'local' | 'cloud'
  sandboxId?: string
  status: 'queued' | 'running' | 'waiting_input' | 'cancelling' | 'completed' | 'failed' | 'cancelled'
}

interface QuotaSummary {
  cpuSecondsRemaining: number
  memoryMbLimit: number
  diskMbRemaining: number
  concurrentRunsRemaining: number
}
```

---

## 4. 行为规格

### 4.1 正常流程

```
1. 用户在 cloud Project 下发送消息 → SessionService 创建 run，读取 Context Pack 和 Agent Profile。
2. CloudAgentRuntime 请求 SandboxRunner 创建或复用 sandbox → Runner 挂载 workspace。
3. SecretProvider 将允许的 secret 注入 sandbox 环境 → 原始 secret 不进入数据库日志或事件。
4. Adapter 在 sandbox 内启动真实 CLI → stdout/stderr 转为标准事件。
5. File watcher 检测 workspace 变更 → ArtifactDetector 发布 artifact.detected → Artifact Bridge 创建 Artifact Card。
6. 用户点击取消 → RunService 调用 SandboxRunner terminate process → run 状态变为 cancelled。
7. sandbox 空闲超过 TTL → Runner 停止并释放资源，workspace 数据保留在 CloudWorkspaceProvider。
```

### 4.2 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** (Empty) | cloud Project 尚无运行时，ChatInput 可发送，运行区无状态条 | 无 active run |
| **加载态** (Loading) | “正在准备云端执行环境”，显示 sandbox 创建进度 | sandbox creating |
| **正常态** (Normal) | 消息流实时输出，运行控制条显示 sandbox/Agent 状态 | run running |
| **完成态** (Complete) | 输出结束，Artifact Card 出现，资源使用摘要可查看 | run completed |
| **错误态** (Error) | sandbox 启动失败、配额不足、CLI 缺失显示可恢复错误 | run failed / quota exceeded |
| **边界态** (Edge) | 并发上限、网络禁用、secret 缺失、长时间无输出、用户快速取消 | 配额或运行异常 |

### 4.3 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| 配额不足 | 409 | 当前云端运行配额不足 | 等待释放、停止其他任务或升级配额 |
| sandbox 创建失败 | 500 | 云端执行环境启动失败 | 重试或切换本地运行 |
| CLI 不存在 | runtime.error | 云端镜像缺少该 Agent CLI | 更换 Agent 或联系管理员 |
| secret 缺失 | 400 | 当前任务需要配置密钥 | 打开 Secret 设置 |
| 用户取消 | 202/cancelled | 本次云端运行已取消 | 可重新发送或继续编辑 |
| 网络策略阻断 | runtime.error | 云端环境不允许访问该网络资源 | 调整任务或申请网络权限 |

---

## 5. 前端页面设计

### 5.1 页面布局

```text
┌───────────────┬──────────────────┬────────────────────────────────────┐
│ ProjectSidebar │ SessionSidebar   │ ChatWorkspace                      │
│ Cloud quota    │                  │ ┌──────────────────────────────┐   │
│ Runtime health │                  │ │ ChatHeader: Cloud runtime     │   │
│               │                  │ ├──────────────────────────────┤   │
│               │                  │ │ MessageList + RuntimeStrip    │   │
│               │                  │ │ SandboxStatusPanel            │   │
│               │                  │ ├──────────────────────────────┤   │
│               │                  │ │ ChatInput                     │   │
│               │                  │ └──────────────────────────────┘   │
└───────────────┴──────────────────┴────────────────────────────────────┘
```

Cloud runtime 状态采用紧凑 strip，不把主聊天界面变成运维控制台。详细资源和日志放入 Runtime Detail Modal。

### 5.2 组件树

```text
ChatWorkspace
├── ChatHeader
│   ├── RuntimeModeBadge
│   └── QuotaIndicator
├── MessageList
│   ├── RuntimeControlStrip
│   ├── SandboxStatusPanel
│   └── MessageArtifactStrip
├── RuntimeDetailModal
│   ├── SandboxResourceChart
│   └── RuntimeLogViewer
└── ChatInput
```

### 5.3 关键视觉元素

| 元素 | 位置 | 视觉规格 |
|------|------|---------|
| RuntimeModeBadge | ChatHeader | 云图标 + “Cloud”，本地为硬盘图标 + “Local”，不加粗 |
| QuotaIndicator | ChatHeader 右侧 | 细进度条，接近限制时变 amber，超限 red |
| SandboxStatusPanel | MessageList 当前 run 下 | 8px radius，显示 creating/ready/running/stopped |
| RuntimeLogViewer | RuntimeDetailModal | 等宽日志，secret 命中显示 `[REDACTED]` |

---

## 6. 前端交互序列

### 6.1 云端 Agent 执行

```
用户: 在 cloud Project 发送消息
  → 前端: POST /api/sessions/{sessionId}/runs runtime=cloud
  → 后端: 创建 sandbox 和 run
  → SSE/WebSocket: sandbox.created → sandbox.ready → agent.process.started
  → 前端: RuntimeControlStrip 显示准备中到运行中
  → SSE/WebSocket: agent.output / artifact.detected
  → 前端: 消息流和 Artifact Card 更新
```

### 6.2 取消云端运行

```
用户: 点击停止
  → 前端: POST /api/runs/{runId}/cancel，按钮进入 cancelling
  → 后端: Runner 终止 sandbox 内 CLI 进程
  → SSE/WebSocket: agent.process.exited + run.cancelled
  → 前端: 当前消息标记 cancelled，输入框恢复
```

### 6.3 Secret 配置

```
用户: 运行失败提示 secret 缺失
  → 前端: 打开 Secret 设置页
  → 用户: 输入 secret
  → 前端: POST /api/secrets
  → 后端: 加密保存，只返回 SecretRef
  → 用户: 返回聊天重新运行
```

---

## 7. 验收标准

- [x] AC-P10-01: cloud Project 中发送消息会创建 sandbox，并在 ready 后启动真实 CLI Agent。
- [x] AC-P10-02: 云端运行输出沿用 P1 事件契约，现有 MessageList 和 Artifact Card 无需分叉实现。
- [x] AC-P10-03: 云端 CLI 修改 workspace 文件后，Artifact Bridge 创建消息级 Artifact。
- [x] AC-P10-04: 取消 run 后，sandbox 内 CLI 进程终止，前端输入框恢复，run 持久化为 cancelled。
- [x] AC-P10-05: 并发、CPU、内存、磁盘或运行时长超限会阻断或终止运行，并展示明确提示。
- [x] AC-P10-06: secret 原文不会出现在 runtime_logs、EventBus payload、前端日志或错误摘要中。
- [x] AC-P10-07: sandbox 停止后 workspace 数据仍可通过 Phase 9 workspace/snapshot API 访问。
- [x] AC-P10-08: 本地 P1 runtime 不因云端 runtime 引入而回归。
- [x] AC-P10-09: local 和 cloud run 使用同一 MessageList、Artifact Card、ApprovalCard 渲染路径，不新增云端专用聊天 UI 分叉。
- [x] AC-P10-10: Phase 10 cloud slice 在真实服务上完成 sandbox ready、CLI 输出、run 终态和日志查询闭环。

---

## 8. 测试策略

### 8.1 单元测试（45 条）

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| SandboxRunner | 12 | create/ready/stop/ttl/failure 状态转换 |
| CloudAgentRuntime | 10 | CLI 启动、输出解析、交互提示、取消 |
| QuotaService | 8 | 并发、CPU、内存、磁盘、运行时间限制 |
| SecretProvider | 8 | 加密、作用域、注入、日志脱敏 |
| ArtifactDetector | 7 | 文件变更、路径过滤、事件生成 |

### 8.2 集成测试

- Fake sandbox runner + real SQLite：启动 run、输出事件、取消、日志查询。
- Secret 注入测试：带 secret 的命令输出必须被脱敏。
- Quota 测试：并发上限和运行超时触发 `quota.exceeded`。

### 8.3 E2E 测试

- 云端 Project 发送任务，等待 sandbox ready，查看输出和 Artifact Card。
- 点击取消，验证 UI 状态、后端 run 状态、sandbox 状态一致。
- secret 缺失 → 配置 secret → 重新运行成功。

### 8.4 P1/P2 兼容门禁

- P1 local 回归：本机 Project 中发送消息，确认本机 CLI runtime、取消、审批续跑、Artifact Bridge 和本地 build/preview/export 仍可用。
- P2 cloud slice：cloud Project 中发送消息，确认 sandbox 生命周期、标准事件、日志脱敏、Artifact 检测和 run 状态持久化。
- 多端视口：桌面宽度展示 RuntimeModeBadge/QuotaIndicator；移动宽度下 runtime 状态为紧凑条，不遮挡 ChatInput。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| 用户可见 Agent 必须是真实 CLI/RPC 运行，不裸调 HTTP LLM API | [PRD-01](../../../../PRD/01-Architecture_Adapter.md) |
| 云端运行必须挂载 Project workspace | [ADR-0009](../../../../archive/adr/0009-project-workspace-model.md)、[PRD-07](../../../../PRD/07-SaaS_Cloud_Workspace_Delivery.md) |
| 事件契约兼容 P1 CLI Runtime | [ADR-0005](../../../../adr/0005-目标架构.md)、[PRD-01](../../../../PRD/01-Architecture_Adapter.md) |
| 多租户 sandbox 必须有隔离、配额、secret 策略 | [PRD-07](../../../../PRD/07-SaaS_Cloud_Workspace_Delivery.md) |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 9 CloudWorkspaceProvider | workspaceId、mount/storage_uri、snapshot | ✅ 已就绪（元数据基座；真实挂载由 Phase 10 实现） |
| Phase 8 ContextPackBuilder | `approval_resume`、`send` context pack | ✅ 已就绪 |
| CLI Adapter contracts | stdout/stderr 解析、interactive prompt、取消 | ✅ P1 基线 |
| EventBus | 标准事件发布和前端流式消费 | ✅ P1 基线 |
| Object storage | workspace 挂载与持久化 | ✅ 开发态隔离目录已就绪；生产对象存储/volume 后续替换 |

---

## 11. Non-Goals（明确不做什么）

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 云端 preview URL | 需要 Preview Service | Phase 11 |
| 一键部署和域名 | 需要 Deploy Service | Phase 11 |
| 团队评论、通知、移动端 | 协作体验阶段 | Phase 12 |
| 完整镜像市场 | 先提供锁定基础镜像 | 后续平台阶段 |
| 裸 HTTP LLM Agent | 架构明确禁止 | 永不做 |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| Runtime key | P1 按 session/agent 绑定本机进程 | P2 增加 sandboxId/runtimeMode | Store 和 API 类型增加可选字段，local 默认无 sandboxId |
| 环境变量 | 本机 `.env`/进程环境 | SecretProvider 按 scope 注入 | 本地保留 `.env`，云端必须使用 SecretRef |
| 日志 | 本机 runtime 日志 | 云端 runtime_logs + 脱敏 | 前端 RuntimeLogViewer 统一读取 `/api/runs/{runId}/logs` |

> **版本历史**
> - v1.2 (2026-06-08): 标记 Phase 10 完成，补充实现边界、验收结果、交付文档和文档审计记录。
> - v1.1 (2026-06-08): 增加 P1 local runtime 零回归与 Phase 10 cloud runtime 可运行切片门禁。
> - v1.0 (2026-06-08): 按 `SPEC_TEMPLATE.md` 创建 Phase 10 独立 Spec。

---

## Phase 10 文档审计记录

- 发现问题：Phase 10 实现完成后，`CONTEXT.md`、`docs/README.md`、`docs/specs/README.md`、`AGENTS.md`、`CLAUDE.md`、`.trae/rules/project_rules.md` 仍把 Phase 10 描述为“准备期 / 下一阶段 / 🔜”。
- 已执行修复：新增 `docs/deliverables/phase10-cloud-runtime/` 交付快照与 `docs/dev-logs/phase10-dev-log.md`；同步更新 Phase 状态、验收入口、P1/P2 工作目录边界、Phase 11 依赖状态和 AgentHub skills 审计记录。
- 口径确认：Phase 10 已打通 cloud runtime 可运行切片，但底层隔离实现仍是开发态本机隔离目录；生产 SaaS runner、preview/deploy 与正式 Auth/KMS 分别进入后续 Phase。
