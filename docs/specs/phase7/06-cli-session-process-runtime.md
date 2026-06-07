# 06: CLI Session Process Runtime

**状态**: Implementation Baseline
**创建日期**: 2026-06-07
**关联**: [Phase 6 CLI Adapter](../phase6/01-cli-adapter.md)、[7A Runtime Control](01-runtime-task-control.md)、[7E Context Pack](05-context-pack-and-cache-strategy.md)、[ADR-0011 Agent Engine Skill Model](../../adr/0011-agent-engine-skill-model.md)

---

## 1. 目标

本模块把 CLI 单聊的运行时能力拆成两层：底层 Engine 原生会话复用，以及真正的会话级常驻进程。只有 CLI 明确暴露可驱动的多 turn 长连接协议时，AgentHub 才声明“一个对话一个物理 CLI 进程”。

目标语义：

```text
一个 AgentHub 私聊 Session
  -> Adapter 先声明能力：native engine session resume 或 persistent process
  -> persistent process: 后端长期持有 stdin/stdout/stderr
  -> 每轮用户消息作为一个 turn 写入对应协议
  -> 读取 stdout / JSON-RPC response 直到明确 turn 边界
  -> 只有 persistent process 才承诺进程继续存活，等待下一轮 turn
```

本模块不要求多个 AgentHub 会话共享同一个底层进程。相反，隔离原则是：

```text
one AgentHub session = one CLI session process
```

---

## 2. 架构边界

### 2.1 新增运行时层

新增两类会话级常驻运行时：

- `CliSessionProcessRuntime`: 服务确认为 stdin JSONL 长连接的 CLI。Claude Code `-p --input-format stream-json --output-format stream-json --verbose` 已通过本机双 turn 探针确认，可作为会话级常驻进程驱动。
- `CliRpcSessionRuntime`: 服务 Codex MCP server、OpenCode ACP 这类 JSON-RPC 长连接。

```text
CliAgentAdapter
  -> CliSessionProcessRuntime.stream_turn()
       -> ensure session process
       -> write prompt to stdin
       -> read stdout/stderr queue
       -> stop at turn boundary
       -> keep process alive

CliAgentAdapter
  -> CliRpcSessionRuntime.stream_turn()
       -> ensure session process
       -> JSON-RPC initialize
       -> call per-turn method/tool
       -> read notifications + response
       -> stop at JSON-RPC response turn boundary
       -> keep process alive
```

短进程仍由 `CliProcessManager.stream()` 管理：

```text
CliProcessManager = 一次 invocation 的 subprocess 管理
CliSessionProcessRuntime = 一会话一常驻 stdin JSONL 进程管理
CliRpcSessionRuntime = 一会话一常驻 JSON-RPC 进程管理
CliRuntimeRegistry = 上层统一门面，合并查看/回复/终止三类进程
```

业务层不得直接判断某个进程属于短进程还是常驻进程。运行取消、交互回复和环境体检统一通过 `cli_runtime_registry`。

### 2.2 Adapter 能力声明

Adapter 通过 `PersistentProcessPolicy` 声明是否支持常驻进程。

当前基线：

| CLI | 常驻进程策略 | 状态 |
|-----|--------------|------|
| Claude Code | `claude -p --input-format stream-json --output-format stream-json --verbose`，首轮带 `--session-id <uuid>`，续轮在同一 stdin JSONL 进程内写入 user message；进程死亡后下一轮用 `--resume <session_id>` 恢复 | 已接入 |
| Codex | `codex mcp-server`，MCP stdio JSON-RPC，首轮 `tools/call codex`，续轮 `tools/call codex-reply`，以 tool response 作为 turn 边界 | 已接入 |
| OpenCode | `opencode acp`，ACP JSON-RPC，`session/new` 后每轮 `session/prompt`，以 response `stopReason` 作为 turn 边界 | 已接入 |
| Custom | 默认短进程，避免无法判断 turn 边界 | 不启用 |

---

## 3. 行为规格

### 3.1 首轮启动

```text
用户发送第一条消息
  -> SingleCliChatStream 创建 run/task/message runtime
  -> CliAgentService 选择对应 Adapter
  -> Adapter 根据 PersistentProcessPolicy 选择协议
  -> ClaudeCodeAdapter.prepare_persistent_invocation()
       - 规范化 `-p`
       - 强制 `--output-format stream-json`
       - 强制 `--input-format stream-json`
       - 强制 `--verbose`
       - 首轮带 `--session-id <AgentHub assigned uuid>`
       - prompt 渲染为 Claude SDK user message JSONL
  -> CodexAdapter.prepare_persistent_rpc_invocation()
       - 启动 `codex mcp-server`
       - 首轮调用 MCP tool `codex`
       - 记录 `structuredContent.threadId`
  -> OpenCodeAdapter.prepare_persistent_rpc_invocation()
       - 启动 `opencode acp`
       - 初始化后 `session/new`
       - 每轮调用 `session/prompt`
  -> Claude Code / Codex / OpenCode 会话运行时启动常驻子进程
  -> SSE: agent.process.started
```

### 3.2 后续 turn

```text
同一 AgentHub session 再发送消息
  -> Claude Code / Codex / OpenCode 会话运行时命中现有 process handle，不重启子进程
  -> 写入本轮 user message 或 JSON-RPC request
  -> SSE: agent.process.started { persistentProcess: true, reused: true }
  -> 读取到协议 turn 边界
  -> SSE: agent.process.turn_completed
  -> 子进程保留
```

### 3.3 并发隔离

- 不同 AgentHub session 使用不同子进程，互不共享 stdin/stdout。
- 同一 AgentHub session 内使用 session lock 串行化 turn。
- 第二轮请求到达时，如果第一轮仍未读到 turn 边界，第二轮等待，不与第一轮 prompt 交错写入 stdin。
- 常驻进程 snapshot 暴露 `mode=session` / `mode=rpc_session`、`protocol`、`turnActive`、`reused/recovered` 等调试字段。

### 3.4 交互提示

常驻进程继续复用 CLI Adapter 的输出解析和 `PromptInterceptor`：

```text
stdout 输出确认提示
  -> adapter 产出 interactive_prompt
  -> 前端 POST /sessions/{id}/interactive_reply
  -> cli_runtime_registry.reply(processId, "y"|"n")
  -> 常驻进程 stdin 写入确认回复
```

### 3.5 取消

运行取消必须覆盖常驻进程：

```text
POST /api/runs/{runId}/cancel
  -> RunService.cancel_run()
  -> cli_runtime_registry.terminate(processId) 或 terminate_session(sessionId)
  -> 若命中常驻进程，CliSessionProcessRuntime 终止子进程并解除等待中的 stdout queue
  -> run/task/process 标记 cancelled
  -> 追加可见运行控制系统消息
```

### 3.6 进程死掉后的恢复

如果 session 已记录的常驻进程不存在或 returncode 非空：

```text
下一轮 turn
  -> CliSessionProcessRuntime 清理旧 handle
  -> 使用同一 session/agent/workspace 配置重新启动子进程
  -> SSE: agent.process.started { persistentProcess: true, recovered: true }
  -> 本轮 prompt 写入新进程
```

恢复不等于恢复正在执行中的半轮输出。当前保证的是“下一轮可自动拉起新进程并继续会话”，不是“崩溃前未完成 turn 精确续跑”。

---

## 4. 跨模块契约

### 4.1 后端模块

| 模块 | 职责 |
|------|------|
| `backend/app/agents/cli_runtime.py` | 短进程 subprocess lifecycle，只服务一次 invocation |
| `backend/app/agents/cli_session_runtime.py` | 会话级 stdin JSONL 常驻进程 lifecycle、stdin/stdout 长连接、turn lock、死进程恢复 |
| `backend/app/agents/cli_rpc_session_runtime.py` | 会话级 JSON-RPC 常驻进程 lifecycle、MCP/ACP framing、request/response 关联、通知队列、turn lock |
| `backend/app/agents/cli_runtime_registry.py` | 上层统一门面：active snapshots、interactive reply、terminate，覆盖短进程、stdin 常驻进程和 RPC 常驻进程 |
| `backend/app/agents/cli_adapters.py` | Adapter 声明常驻能力，解析 stdout/stderr 为 `CliEvent` |
| `backend/app/services/run_service.py` | 运行状态持久化与取消编排，不直接依赖某个具体运行时实现 |

### 4.2 事件

| 事件 | 说明 |
|------|------|
| `agent.process.started` | 每个 turn 都会发出；常驻进程 metadata 包含 `persistentProcess/persistentProtocol/reused/recovered` |
| `agent.output` | 与短进程一致，仍由 Adapter 解析 stdout/stderr |
| `interactive_prompt` | 与短进程一致，processId 指向常驻进程 |
| `agent.process.turn_completed` | 常驻进程 turn 边界；进程仍存活 |
| `agent.process.completed` | 子进程自然退出或短进程结束 |
| `agent.process.timeout` | turn 等待 stdout 超时，运行时终止子进程 |

---

## 5. 验收标准

- [x] AC-7F-01: Claude Code Adapter 使用 `--session-id` 绑定原生 Engine session，并通过 stdin JSONL 常驻进程复用同一 AgentHub 私聊进程。
- [x] AC-7F-02: 支持常驻协议的 CLI 同一 session 连续两轮复用同一 processId，第二轮 `reused=true`。
- [x] AC-7F-03: 不同 session 使用不同 processId。
- [x] AC-7F-04: 同一 session 并发两轮不会交错写入 stdin，第二轮等待第一轮 `result` 后执行。
- [x] AC-7F-05: 子进程死掉后下一轮自动拉起新 processId，并标记 `recovered=true`。
- [x] AC-7F-06: interactive reply 可写回常驻进程 stdin。
- [x] AC-7F-07: run cancel 可终止常驻进程，进程列表不残留。
- [x] AC-7F-08: `/api/agents/runtime/processes` 与 system health 能同时看到短进程和常驻进程。
- [x] AC-7F-09: 业务层通过 `cli_runtime_registry` 终止/回复/查询进程，不直接绑定某个底层运行时。
- [x] AC-7F-10: Codex Adapter 声明 MCP JSON-RPC 常驻能力，并通过 `codex` / `codex-reply` tool response 建立 turn 边界和 threadId 续轮。
- [x] AC-7F-11: OpenCode Adapter 声明 ACP JSON-RPC 常驻能力，并通过 `session/new` / `session/prompt` 建立 turn 边界和 sessionId 续轮。

---

## 6. 测试策略

### 6.1 单元测试

`backend/test_unit/test_cli_adapter_runtime.py` 覆盖：

- 真实 fixture subprocess 的 stdin/stdout 流；
- 交互式确认 stdin 回写；
- Claude Code 原生 session 与 stdin JSONL 常驻 invocation 参数规范化；
- 常驻进程同 session 复用；
- 不同 session 隔离；
- 子进程死亡后的下一轮恢复；
- 同 session 并发 turn 串行化。
- Codex MCP fixture subprocess 的首轮 `codex`、续轮 `codex-reply`；
- OpenCode ACP fixture subprocess 的 `session/new`、`session/prompt` 和 `session/update` 解析。

### 6.2 API 测试

`backend/test_api/test_chat.py` 覆盖：

- 单聊 chat 流仍能完成消息持久化；
- Claude Code 单聊复用同一 session process，metadata 同时记录 persistent process 与 engine session resume 信息；
- run/process rows 能记录常驻 processId；
- Engine session resume metadata 与常驻进程 metadata 可共存。

### 6.3 仍需真实 CLI E2E

自动化 fixture 只能证明 AgentHub 运行时逻辑正确。真实 Claude Code / Codex / OpenCode 仍需补本机 E2E：

```text
创建 Project
  -> 创建 Claude Code / Codex / OpenCode Agent 私聊
  -> 各连续两轮真实写入/读取 workspace
  -> 中途取消一轮
  -> 第三轮确认同会话进程恢复或重启后可继续
  -> 验证 Artifact Bridge 和运行控制消息
```

---

## 7. 非目标

- 不让多个 AgentHub session 共享同一个 Claude Code 进程。
- 不把群聊 DAG task 绑定到用户私聊常驻进程。
- 不承诺进程崩溃后恢复半轮未完成输出。
- 不把 Codex/OpenCode 强行塞进 Claude stdin JSONL 运行时；二者只通过各自官方/公开协议入口接入。
- 不把聊天 transcript 当成唯一上下文主干；Context Pack 仍是后续上下文治理方向。
