# Spec: Phase 7A — 运行任务可控性

**版本**: v1.0
**创建日期**: 2026-06-06
**状态**: 验收通过
**关联 ADR/PRD**: [ADR-0008](../../adr/0008-revised-development-strategy.md)、[ADR-0009](../../adr/0009-project-workspace-model.md)、[ADR-0010](../../adr/0010-message-level-artifact-experience.md)、[PRD-02](../../PRD/02-Orchestrator_Engine.md)、[PRD-05](../../PRD/05-End_to_End_Product_Flow.md)
**依赖模块**: Phase 6 CLI Runtime、Phase 6 Artifact Bridge、Phase 3 Orchestrator DAG

> 2026-06-06 实现同步：本模块已落地 `runs`、`run_tasks`、`run_processes` 持久化表，接入单聊和群聊 CLI 流，新增 runs API 与前端 `RuntimeControlStrip`。本轮人工验收发现的“停止后没有明确中止提示、输入框仍锁死、其它会话被占用”已修复：点击停止会立即 abort 当前 SSE、本地回退 run/message 状态、追加可见运行控制消息并释放输入框；后端取消会终止进程/会话活跃进程并持久化 cancelled 状态。

---

## 1. 目标

本模块解决“真实 CLI Agent 一旦开始执行，用户只能等待”的问题。Phase 6 已能启动 Claude Code/Codex/OpenCode 进程并展示执行轨迹，但运行状态主要停留在内存与 SSE 中；用户刷新、切会话、遇到长任务或误操作时，缺少可持久化、可取消、可恢复的任务控制层。

目标用户是正在本机 workspace 中运行真实 CLI Agent 的开发者。用户必须能知道当前是谁在执行、执行到哪个阶段、是否仍有进程存活，并能在界面里明确取消本次运行。

**成功标准**（可证伪）：

- [x] 每次 `/api/sessions/{id}/chat` 创建一个 `run` 记录，至少包含 `runId/sessionId/status/startedAt/currentMessageId`。
- [x] 单聊真实 CLI 进程启动后，`run.status=running`，前端显示运行控制条和取消按钮。
- [x] 用户点击取消后，后端调用 `cli_process_manager.terminate_session(sessionId)` 或按 `processId` 终止进程；最终状态为 `cancelled`。
- [x] 取消操作幂等：重复点击不会报错，不会产生多个失败 toast。
- [x] 不通过标准：只隐藏前端流式状态但后端 CLI 进程仍在运行；或取消后输入框仍被锁死。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
用户发送消息
  → [本模块] run/task 状态创建
  → CLI Agent / Orchestrator 执行
  → 用户可观察、取消、恢复状态
  → Artifact Bridge / Approval Checkpoint
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | `POST /api/sessions/{id}/chat` | 在执行前创建 run/task |
| **上游输入** | CLI Runtime `agent.process.started/completed/timeout` | 同步 processId、exitCode、状态 |
| **上游输入** | Orchestrator `task_started/task_completed/phase_change` | 将 ephemeral collab task 映射为持久 task |
| **下游产出** | `run.*`、`task.status_changed` SSE/WebSocket | 前端运行控制条、协作面板、审批模块消费 |
| **本模块不通** | 不定义审批确认/驳回 | Phase 7B |

---

## 3. 跨模块契约

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/sessions/{sessionId}/runs` | GET | 无 | `200: RunRead[]` | `404` session 不存在 |
| `/api/runs/{runId}` | GET | 无 | `200: RunRead` | `404` run 不存在 |
| `/api/runs/{runId}/cancel` | POST | `{ "reason": string? }` | `200: RunRead(status="cancelled"|"cancelling")` | `404` run 不存在 |
| `/api/runs/{runId}/tasks` | GET | 无 | `200: TaskRead[]` | `404` run 不存在 |
| `/api/agents/runtime/processes` | GET | query: `sessionId?` | `200: { processes: ProcessSnapshot[] }` | 无 |

`POST /api/runs/{runId}/cancel` 规则：

- 如果 run 已经 `completed/failed/cancelled`，直接返回当前状态。
- 如果有 `processId`，优先终止该进程。
- 如果没有 `processId` 但有 `sessionId`，终止该 session 下全部活跃进程。
- 取消后必须写一条 assistant/system message 或更新当前 assistant message metadata，前端能恢复“本轮已取消”的事实。

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `run.started` | 后端 → SSE/WS | `{ runId, sessionId, mode, messageId?, startedAt }` |
| `run.status_changed` | 后端 → SSE/WS | `{ runId, sessionId, status, reason?, updatedAt }` |
| `task.status_changed` | 后端 → SSE/WS | `{ runId, taskId, sessionId, status, phase?, agentId?, messageId? }` |
| `run.cancel_requested` | 前端/API → 后端内部 | `{ runId, sessionId, reason? }` |
| `run.cancelled` | 后端 → SSE/WS | `{ runId, sessionId, killedProcessIds, messageId? }` |

### 3.3 数据库 Schema 变更

```sql
CREATE TABLE runs (
    id VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    project_id VARCHAR REFERENCES projects(id),
    mode VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    current_message_id VARCHAR REFERENCES messages(id),
    started_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    completed_at DATETIME,
    cancel_reason TEXT,
    metadata_json TEXT
);

CREATE TABLE run_tasks (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES runs(id),
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    agent_id VARCHAR REFERENCES agent_configs(id),
    message_id VARCHAR REFERENCES messages(id),
    name VARCHAR NOT NULL,
    role VARCHAR,
    phase INTEGER,
    status VARCHAR NOT NULL,
    depends_on_json TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    metadata_json TEXT
);

CREATE TABLE run_processes (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES runs(id),
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    agent_id VARCHAR REFERENCES agent_configs(id),
    message_id VARCHAR REFERENCES messages(id),
    process_id VARCHAR NOT NULL,
    pid INTEGER,
    executable VARCHAR,
    cwd VARCHAR,
    status VARCHAR NOT NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    exit_code INTEGER
);
```

### 3.4 跨组件 TypeScript 类型

```typescript
type RunStatus = "queued" | "running" | "pausing" | "paused" | "cancelling" | "cancelled" | "completed" | "failed";
type TaskStatus = "pending" | "running" | "paused" | "completed" | "failed" | "cancelled";

interface RunRead {
  id: string;
  sessionId: string;
  projectId?: string | null;
  mode: "single" | "group" | "orchestrated";
  status: RunStatus;
  currentMessageId?: string | null;
  startedAt: string;
  updatedAt: string;
  completedAt?: string | null;
  cancelReason?: string | null;
}

interface TaskRead {
  id: string;
  runId: string;
  sessionId: string;
  agentId?: string | null;
  messageId?: string | null;
  name: string;
  role?: string | null;
  phase?: number | null;
  status: TaskStatus;
  dependsOn: string[];
}
```

---

## 4. 行为规格

### 4.1 正常流程

```text
1. 用户发送消息
   → 后端创建 run(status=queued)
   → SSE run.started
   → 前端 RuntimeControlStrip 显示“准备执行”

2. CLI 进程启动
   → 后端创建 run_processes 记录
   → run.status=running
   → 前端显示 Agent 名称、进程状态、取消按钮

3. Agent 输出文本/轨迹/产物
   → 现有 MessageBubble、ExecutionTracePanel、MessageArtifactStrip 正常更新
   → RuntimeControlStrip 只显示紧凑状态，不复制详细轨迹

4. 用户点击取消
   → 前端 POST /api/runs/{runId}/cancel
   → 后端标记 run.status=cancelling
   → terminate process
   → run.status=cancelled，run_task/run_processes 同步 cancelled
   → SSE run.cancelled
   → 前端停止本轮流式写入，输入框恢复

5. 运行自然完成
   → run.status=completed 或 failed
   → 前端隐藏取消按钮，保留运行摘要入口
```

### 4.2 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** | 没有运行控制条，只显示普通聊天输入 | 当前 session 无 active run |
| **加载态** | Agent 头像旁出现小型 spinner，消息下方显示“准备执行” | `run.started` 后、进程启动前 |
| **正常态** | `RuntimeControlStrip` 显示 Agent、阶段、运行时长、取消按钮 | `run.status=running` |
| **完成态** | 状态收起为一行“已完成 · 用时 X”，无取消按钮 | `completed` |
| **错误态** | 显示错误摘要和“复制诊断”按钮 | `failed` 或 `agent.process.timeout` |
| **边界态** | 快速取消、重复取消、刷新页面后仍能恢复 active run 状态 | 并发/刷新/重试 |

### 4.3 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| run 不存在 | `404` | “本次运行不存在或已被清理” | 刷新会话 |
| 进程已结束 | `RUN_ALREADY_FINISHED` | “任务已经结束” | 返回当前 run 状态 |
| 进程终止失败 | `PROCESS_TERMINATE_FAILED` | “取消失败，请稍后重试” | 保持 cancelling，允许重试 |
| 前端流断开 | `STREAM_DISCONNECTED` | “连接已断开，任务状态稍后同步” | 通过 `/runs` 恢复状态 |
| workspace 丢失 | `WORKSPACE_NOT_FOUND` | “项目目录不可用，任务已停止” | 打开环境体检 |

---

## 5. 前端页面设计

### 5.1 页面布局

```text
MessageBubble
├── AgentAvatar + Agent 正在回答状态
├── Markdown 内容
├── RuntimeControlStrip
├── ExecutionTracePanel
└── MessageArtifactStrip
```

`RuntimeControlStrip` 高度 32-40px，放在 assistant 消息正文下方、ExecutionTracePanel 上方。它只显示当前运行状态和取消入口，详细工具日志仍在 `ExecutionTracePanel`。

### 5.2 组件树

```text
ChatWindow
├── MessageBubble[]
│   └── RuntimeControlStrip
│       ├── RunStatusPill
│       ├── RunDuration
│       └── CancelRunButton
└── ChatInput

stores/
├── runtimeStore.ts
└── chatStore.ts
```

### 5.3 关键视觉元素

| 元素 | 位置 | 视觉规格 |
|------|------|---------|
| 运行状态点 | AgentAvatar 右侧 | 8px 状态点，running 绿色呼吸，cancelling 琥珀，failed 红色 |
| 取消按钮 | RuntimeControlStrip 右侧 | lucide `Square` 或 `CircleStop`，28px icon button，tooltip “停止本次运行” |
| 运行时长 | RuntimeControlStrip 中间 | 12px 等宽数字，如 `01:32` |
| 失败摘要 | RuntimeControlStrip | lucide `AlertTriangle` + 单行错误，点击展开详情 |

---

## 6. 前端交互序列

```text
用户: 发送消息
  → 前端: runtimeStore.createOptimisticRun(sessionId)
  → 后端: SSE run.started
  → 前端: RuntimeControlStrip 显示 loading
  → SSE agent.process.started
  → 前端: RuntimeControlStrip 显示 running + 取消按钮

用户: 点击取消按钮
  → 前端: 按钮进入 loading，禁止重复点击
  → API: POST /api/runs/{runId}/cancel
  → 后端: terminate CLI process
  → SSE/WS: run.cancelled
  → 前端: 停止 streaming 状态，ChatInput 解锁，消息标记“已取消”
```

---

## 7. 验收标准

- [ ] AC-7A-01: 发起单聊 CLI 消息后，`GET /api/sessions/{id}/runs` 返回 running run。
- [ ] AC-7A-02: `agent.process.started` 后，`run_processes` 保存 processId、pid、cwd、agentId。
- [ ] AC-7A-03: 点击取消按钮后，后端活跃进程列表不再包含该 session 的 process。
- [ ] AC-7A-04: 取消后的 assistant 消息 metadata 包含 `{ runStatus: "cancelled" }` 或等价字段，刷新页面可恢复。
- [ ] AC-7A-05: 已完成 run 再次 cancel 返回 200 和当前 completed 状态，不抛 500。
- [ ] AC-7A-06: 群聊/Orchestrator 运行中取消，会取消 run 下全部活跃 task/process。
- [ ] AC-7A-07: 前端断线后重新进入 session，会从 `/runs` 恢复 active run 控制条。

---

## 8. 测试策略

### 8.1 单元测试（10 条）

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| RunService 状态机 | 4 | queued→running→completed/failed/cancelled，非法转换 |
| Process binding | 2 | processId 写入、exitCode 更新 |
| Cancel idempotency | 2 | running/completed 重复取消 |
| Metadata merge | 2 | message metadata 运行状态持久化 |

### 8.2 集成测试

- 使用测试 CLI sleep fixture：发送消息 → run running → cancel → process killed。
- 使用真实 `cli_process_manager.active_snapshots(sessionId)` 验证取消后为空。

### 8.3 E2E 测试

- 浏览器发送长任务 → 点击取消 → UI 显示已取消 → 输入框恢复 → 后端无活跃进程。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| CLI 进程仍由 CLI Runtime 管理，RunService 只编排状态 | ADR-0009 §CLI 适配器策略 |
| run/task 状态持久化，为审批模块提供基础 | PRD-02 §任务状态机 |
| 不把运行控制放到独立工作台 | ADR-0010 |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| `cli_process_manager` | `terminate_session`、`active_snapshots` | 已就绪 |
| SingleCliChatStream | 创建 run、同步 process events | 待接入 |
| GroupChatStream | task/process 级状态映射 | 待接入 |
| chatStore | active run 状态 | 待拆分/迁移 |

---

## 11. Non-Goals

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 不实现后台任务队列系统 | P1 本机运行只需当前进程可控 | 后续平台化 |
| 不实现暂停后从 CLI 原进程继续 | 大多数 CLI 不支持可靠 suspend/resume | 审批用 task checkpoint |
| 不做跨设备运行恢复 | P1 本机版范围外 | P2 |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| 运行状态 | 前端 streaming boolean + 内存 process | 持久化 runs/run_tasks/run_processes | 新增迁移，旧消息不补历史 run |
| 取消 | 无 UI 入口 | `/api/runs/{id}/cancel` | 前端接入 RuntimeControlStrip |
| 刷新恢复 | 只能重新拉消息 | `/runs` 恢复 active run | 进入 session 时加载 runs |

> **版本历史**
> - v1.0 (2026-06-06): 初始版本。
> - v1.1 (2026-06-06): 同步实现基线与取消回退验收修复。
