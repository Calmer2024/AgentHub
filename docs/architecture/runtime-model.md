# AgentHub Runtime 模型

> 本文档描述 AgentHub 当前的执行模型，包括本机 CLI runtime、云端 runtime、Run/Task/Process 状态和审批。

## Runtime 分层

```text
用户请求
  -> Run
    -> RunTask
      -> RunProcess
        -> Local CLI process 或 Cloud runtime run
```

## Local Runtime

本机桌面版运行链路：

```text
Project.workspace_path
  -> Session
  -> AgentConfig
  -> CliAgentService
  -> CliAgentAdapter
  -> cli_process_manager / cli_session_process_runtime / cli_rpc_session_runtime
  -> stdout / stderr
  -> SSE events
```

关键文件：

- `backend/app/services/single_cli_chat_stream.py`
- `backend/app/services/cli_agent_service.py`
- `backend/app/services/cli_agent_executor.py`
- `backend/app/agents/cli_adapters.py`
- `backend/app/agents/cli_runtime.py`
- `backend/app/agents/cli_session_runtime.py`
- `backend/app/agents/cli_rpc_session_runtime.py`

## Cloud Runtime

云端运行链路：

```text
Cloud Project
  -> Workspace
  -> Sandbox
  -> RuntimeRun
  -> RuntimeLog
  -> Artifact / Preview / Deployment
```

关键文件：

- `backend/app/services/cloud_agent_runtime.py`
- `backend/app/services/sandbox_service.py`
- `backend/app/services/runner_provider.py`
- `backend/app/services/cloud_workspace_provider.py`
- `backend/app/services/cloud_delivery_service.py`

## Local / Cloud 分流

聊天入口在 `backend/app/api/chat.py`：

```text
if project.workspace_mode == "cloud":
    CloudAgentRuntimeService
else:
    ChatServiceImpl
```

这表示上层产品模型一致，下层 runtime provider 不同。

## Run 状态

`runs.status` 当前用于表达一次请求整体状态：

| 状态 | 含义 |
| --- | --- |
| `queued` | 已创建，等待开始 |
| `running` | 正在执行 |
| `pausing` | 正在暂停 |
| `paused` | 等待用户审批或人工处理 |
| `cancelling` | 正在取消 |
| `cancelled` | 已取消 |
| `completed` | 已完成 |
| `failed` | 已失败 |

## Task 状态

`run_tasks.status` 当前用于表达单个任务节点状态：

| 状态 | 含义 |
| --- | --- |
| `pending` | 等待依赖或等待启动 |
| `running` | 正在执行 |
| `paused` | 等待审批 |
| `completed` | 已完成 |
| `failed` | 已失败 |
| `cancelled` | 已取消 |
| `rejected` | 审批驳回 |

## Process 状态

`run_processes` 保存底层进程信息：

```text
process_id
pid
executable
cwd
status
exit_code
```

它用于：

- 前端停止运行。
- 后端找到真实 CLI 进程。
- 调试底层 executable、cwd 和退出码。
- 关联 Agent 输出和执行 trace。

## Engine Session

`engine_sessions` 记录底层 CLI 的会话复用信息。不同 CLI 的能力不同：

| 能力 | 含义 |
| --- | --- |
| `oneshot_process` | 每轮消息启动一次进程 |
| `engine_session_resume` | 底层 CLI 有原生 session id，可通过 resume 续聊 |
| `persistent_process` | AgentHub 维护会话级常驻进程 |

相关代码：

- `backend/app/services/engine_session_service.py`
- `backend/app/services/single_cli_chat_stream.py`
- `backend/app/services/cli_agent_executor.py`

## Approval

审批由 `approval_checkpoints` 表承载。

典型链路：

```text
RunTask completed
  -> ApprovalService.create_for_completed_task_if_needed
  -> approval.created SSE
  -> 前端 ApprovalCard
  -> approve / reject
  -> Run / Task 状态更新
```

## Runtime 设计约束

1. 用户可见运行状态以 `runs` 和 `run_tasks` 为准。
2. 底层真实执行以 `run_processes` 或 `runtime_runs` 为准。
3. 本机 CLI 和云端 sandbox 共享上层 Project / Session / Message / Artifact 模型。
4. 取消、暂停、恢复必须能追溯到 Run 或 Orchestrator execution。
5. CLI 输出必须标准化为事件后再进入前端，不让前端理解各 CLI 的私有格式。

