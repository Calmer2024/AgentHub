# 06 — SSE 事件协议

**关联实现**: `backend/app/services/chat_service_impl.py` (SSE 格式化), `frontend/src/api/client.ts` (SSE 解析)

---

## 1. 概述

所有 Orchestrator 相关事件通过 SSE (Server-Sent Events) 推送到前端。格式: `data: {json}\n\n`。事件按固定顺序序列化，前端按 `type` 字段分发。

## 2. 事件总览

| 事件 | type | 触发时机 | 状态 |
|------|------|---------|------|
| 路由决策 | `orchestrator.route` | Pipeline 完成后，Agent 调用前 | ✅ |
| 任务开始 (v1) | `orchestrator.task_started` | route 之后, 第一个 agent 之前 | ✅ |
| 任务开始 (v2) | `orchestrator.task_started` | 同上，含 DAG phases | ❌ |
| Phase 切换 | `orchestrator.phase_change` | 每个 DAG Phase 开始时 | ❌ |
| Agent 开始 | `agent.start` | 每个 Agent 首次产出 token 时 | ✅ |
| Token 流 | `(无 type, 含 agentId)` | Agent 流式产出过程 | ✅ |
| 链式步骤 | `orchestrator.chain_step` | 链式模式每步开始时 | ✅ |
| Agent 完成 | `(done=true, agentId 非空)` | Agent 流式结束 | ✅ |
| 任务完成 | `orchestrator.task_completed` | 所有 Agent 完成后 | ✅ |
| 全局错误 | `error` | 所有 Agent 均失败时 | ✅ |

## 3. 事件详细定义

### 3.1 orchestrator.route

```json
{
  "type": "orchestrator.route",
  "agents": [{"id": "a1", "name": "架构师"}, {"id": "a2", "name": "前端专家"}]
}
```

前端消费: `onRoute(agents)` → 设置 routeAgents 状态 → 渲染横幅。

### 3.2 orchestrator.task_started (v1 — 当前)

```json
{
  "type": "orchestrator.task_started",
  "intent": "code_gen",
  "tasks": [
    {"name": "frontend", "role": "executor", "agent": "前端专家", "status": "running"},
    {"name": "backend", "role": "executor", "agent": "后端架构师", "status": "running"}
  ]
}
```

前端消费: `onTaskStarted(tasks, intent)` → CollaborationView/Panel 显示任务列表。

### 3.3 orchestrator.task_started (v2 — DAG 扩展 ❌ 未实现)

```json
{
  "type": "orchestrator.task_started",
  "intent": "code_gen",
  "dag": {
    "phases": [
      {
        "phase": 0,
        "tasks": [
          {"name": "planning", "role": "planner", "agent": "架构师",
           "depends_on": [], "status": "pending"}
        ],
        "mode": "serial"
      },
      {
        "phase": 1,
        "tasks": [
          {"name": "frontend", "role": "executor", "agent": "前端专家",
           "depends_on": ["planning"], "status": "pending"},
          {"name": "backend", "role": "executor", "agent": "后端架构师",
           "depends_on": ["planning"], "status": "pending"}
        ],
        "mode": "parallel"
      }
    ]
  }
}
```

### 3.4 orchestrator.phase_change (❌ 未实现)

```json
{
  "type": "orchestrator.phase_change",
  "phase": 1,
  "status": "running",
  "agents": ["前端专家", "后端架构师"]
}
```

Phase 状态: `"pending"` → `"running"` → `"completed"` / `"error"`。

### 3.5 agent.start

```json
{
  "type": "agent.start",
  "agentId": "a1",
  "agentName": "架构师",
  "messageId": "msg-xxx"
}
```

DAG 扩展 (❌ 未实现) 增加 `"role": "planner"` 和 `"phase": 0` 字段。

### 3.6 Token 流

```json
{"token": "你", "agentId": "a1", "agentName": "架构师", "done": false}
```

- `agentId` 为 null 时 → 单聊模式 → `onToken`。
- `agentId` 非空时 → 群聊模式 → `onAgentToken(agentId, agentName, token)`。

### 3.7 orchestrator.chain_step

```json
{
  "type": "orchestrator.chain_step",
  "step": 0,
  "agent": "架构师",
  "role": "planner",
  "total": 3,
  "status": "running"
}
```

中断状态:
```json
{
  "type": "orchestrator.chain_step",
  "step": 1,
  "agent": "前端专家",
  "role": "executor",
  "total": 3,
  "status": "interrupted",
  "error": "adapter not found"
}
```

### 3.8 Agent 完成 (per-agent done)

```json
{"token": "", "agentId": "a1", "agentName": "架构师", "done": true, "messageId": "msg-xxx"}
```

错误时追加 `"error": "timeout"`。

> **前端关键逻辑**: per-agent done **不终止 SSE 流** (`data.done && !data.agentId` 才终止)。这是 BUG-1 的修复。

### 3.9 orchestrator.task_completed

```json
{
  "type": "orchestrator.task_completed",
  "summary": "2 agents completed",
  "total_tokens": 847
}
```

### 3.10 全局错误

```json
{
  "type": "error",
  "error": "所有 Agent 均无法响应: 前端专家: adapter not found; 后端架构师: adapter not found",
  "done": true
}
```

只有此事件或单聊完成 (done 且无 agentId) 才会终止前端 SSE 流。

## 4. 完整事件序列示例

### 4.1 当前 (无 DAG)

```
orchestrator.route
orchestrator.task_started  ← v1 (tasks list)
agent.start (Agent A)
token, token, ..., agent.done (Agent A)
agent.start (Agent B)
token, token, ..., agent.done (Agent B)
orchestrator.task_completed
```

### 4.2 DAG (最终目标)

```
orchestrator.route
orchestrator.task_started       ← v2 (phases DAG)
orchestrator.phase_change       ← phase=0, running
agent.start (规划者, role="planner", phase=0)
token, token, ..., agent.done
orchestrator.phase_change       ← phase=1, running
agent.start (前端, role="executor", phase=1)
agent.start (后端, role="executor", phase=1)  ← 同时!
token (交错), ..., agent.done (后端)
token, ..., agent.done (前端)
orchestrator.phase_change       ← phase=2, running
agent.start (审查者, role="reviewer", phase=2)
token, token, ..., agent.done
orchestrator.task_completed     ← { phases_completed: 3 }
```

## 5. 前端 SSE 解析规则

```typescript
// client.ts createChatStream() 核心解析逻辑

if (data.type === "orchestrator.route")     → onRoute(data.agents)
if (data.type === "orchestrator.task_started") → onTaskStarted(data.tasks, data.intent)
if (data.type === "orchestrator.chain_step")   → onChainStep(data)
if (data.type === "orchestrator.phase_change") → onPhaseChange(data)  // ❌ 新增
if (data.type === "orchestrator.task_completed") → onTaskCompleted(data.summary)
if (data.type === "agent.start")               → skip (在 chat_service 中处理)
if (data.type === "error")                     → onDone(undefined, data.error); return

// 流终止条件:
if (data.done && !data.agentId)               → onDone(messageId, error); return
// per-agent done (data.done && data.agentId)   → 不终止! 继续读取
```

## 6. 当前实现状态

| 事件 | 状态 | 备注 |
|------|------|------|
| route | ✅ | |
| task_started (v1) | ✅ | tasks list |
| task_started (v2) | ❌ | DAG phases |
| phase_change | ❌ | |
| agent.start | ✅ | 无 role/phase 字段 |
| token 流 | ✅ | |
| chain_step | ✅ | 含 role 字段 |
| agent.done | ✅ | 含 error 字段 |
| task_completed | ✅ | |
| error | ✅ | |
| 前端解析 (6 种现有事件) | ✅ | |
| 前端解析 (phase_change) | ❌ | |
