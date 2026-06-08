# 7H Orchestrator 执行中断与断点恢复

**状态**: Draft → 本轮实现基线  
**日期**: 2026-06-09  
**关联**: PRD-02、PRD-05、Phase 7A 运行控制、Phase 7G 群聊人机协作控制权

---

## 1. 背景

群聊计划执行可能持续数分钟甚至更久。用户手动停止、刷新页面、后端服务重启或 CLI 进程异常退出时，当前实现会把运行标记为 `cancelled` 或丢失内存态 Scheduler。用户再发送“继续”时，系统会退回普通群聊调度，导致：

- 原 DAG 的完成/未完成任务状态丢失。
- T1/T2/T3 的结构化交接不再作为唯一上下文。
- Agent 收到聊天长日志、执行 trace、`rg --files` 原始输出等噪音。
- UI 仍显示历史执行面板，但无法可靠恢复。

这不是单个 Agent 输出问题，而是 Orchestrator Execution 没有把“中断后可恢复”作为一等状态。

---

## 2. 目标

本模块补齐本机 MVP 的最小断点恢复闭环：

1. 用户点击执行面板“停止”时，默认进入 `interrupted`，不是 `cancelled`。
2. `interrupted` 是可恢复状态，刷新页面后仍能看到“继续执行 / 放弃执行”。
3. 后端服务重启后，持久化快照中的 `running/pending/cancelling` 执行会被标记为 `interrupted`，避免假装仍在运行。
4. “继续执行”必须调用结构化 Resume API，不经过普通群聊调度器。
5. Resume 只从未完成任务继续；已完成任务不重跑。
6. 恢复任务只注入 Plan、任务状态、上游 summary、任务工作包和 workspace，不注入聊天长日志、raw trace 或全量文件列表。

---

## 3. 状态机

### 3.1 Execution 状态

| 状态 | 含义 | 可操作 |
|------|------|--------|
| `running` | Scheduler 正在推进 DAG | 中断 |
| `awaiting_user_input` | 等待用户回答/确认 | 确认继续、放弃 |
| `interrupted` | 用户停止、服务重启或运行丢失后的可恢复中断 | 继续执行、放弃执行 |
| `completed` | 全部任务完成 | 无 |
| `failed` | 执行失败 | 后续可扩展重试 |
| `cancelled` | 用户明确放弃本次执行 | 无 |

### 3.2 Task 状态

| 状态 | 含义 |
|------|------|
| `completed` | 已完成，不会在 Resume 中重跑 |
| `interrupted` | 中断时正在运行或即将运行，Resume 时转回 `pending` |
| `pending` | 等待依赖完成 |
| `awaiting_user_input` | 等待用户确认，Resume 不应跳过确认 |
| `cancelled` | 用户明确放弃后终止 |

---

## 4. API 契约

### 4.1 中断执行

`POST /api/orchestrator/executions/{execution_id}/interrupt`

行为：

- 终止当前 execution 关联的 CLI 进程。
- 将 execution 标记为 `interrupted`。
- 将当前 `running/cancelling` task 标记为 `interrupted`。
- 将 runtime run 标记为 `paused`，不是 `cancelled`。
- 写入 execution 快照。

### 4.2 恢复执行

`POST /api/orchestrator/executions/{execution_id}/resume`

行为：

- 若内存 registry 中没有 execution，从持久化快照恢复。
- 若持久化快照仍是 `running/pending/cancelling`，先转为 `interrupted` 再恢复。
- 将 `interrupted` task 转为 `pending`。
- execution 转为 `running`。
- 从第一个依赖满足的未完成任务继续调度。

### 4.3 放弃执行

`POST /api/orchestrator/executions/{execution_id}/cancel`

行为：

- 作为终态取消使用。
- 将未完成 task 标记为 `cancelled`。
- runtime run 标记为 `cancelled`。

---

## 5. 前端行为

### 5.1 ExecutionPanel

- `running/pending/cancelling`：显示“停止”，调用 `interrupt`。
- `interrupted`：显示“继续执行”和“放弃执行”。
- `cancelled/completed/failed`：不显示运行按钮。
- `interrupted` 状态必须有醒目但不惊吓的说明：任务已中断，可从断点继续。

### 5.2 普通聊天

本轮基线不实现自然语言“继续”的自动接管。若当前会话存在 `interrupted` execution，用户应通过 ExecutionPanel 的结构化按钮恢复。后续可扩展为聊天输入前 guard。

---

## 6. 上下文隔离要求

恢复任务时，Agent Prompt 只能包含：

- 当前 Plan JSON。
- 当前 task 的目标、验收标准、预期输出。
- 已完成上游 task 的 summary / resultMessageId / handoff 路径。
- 当前任务工作包路径和项目 workspace 路径。

禁止包含：

- 完整聊天长日志。
- `agent.process.*` raw trace。
- `rg --files` 全量输出。
- `node_modules`、构建缓存等无关文件列表。

---

## 7. 验收标准

- AC-7H-01：点击执行面板“停止”后，execution 状态为 `interrupted`，未完成任务不再被标成 `cancelled`。
- AC-7H-02：刷新后仍能从持久化快照看到 `interrupted` 执行面板。
- AC-7H-03：点击“继续执行”后，已完成任务不重跑，第一个未完成任务继续运行。
- AC-7H-04：后端重启导致内存 registry 丢失时，`resume` 能从持久化快照恢复执行。
- AC-7H-05：点击“放弃执行”后，execution 才进入 `cancelled` 终态。
- AC-7H-06：Resume 后下游 Agent 的上游上下文来自 task summary/HANDOFF，而不是聊天长日志。

---

## 8. Non-Goals

- 不恢复被杀掉的同一个物理 CLI 进程 stdout 流。
- 不做跨机器或云端分布式恢复。
- 不做自然语言“继续”的自动意图劫持。
- 不做每条命令级 checkpoint replay。

