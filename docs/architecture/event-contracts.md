# AgentHub 事件契约

> 本文档描述当前事件类型和用途。具体 payload 以代码为准，本文用于答辩、调试和新增事件前的导航。

## 事件通道

AgentHub 当前有三类事件通道：

| 通道 | 用途 | 主要文件 |
| --- | --- | --- |
| SSE | 聊天请求内的流式 token、运行状态、Artifact、审批、Orchestrator 状态 | `backend/app/api/chat.py`, `frontend/src/api/client.ts` |
| WebSocket | Session 级广播和心跳，辅助推送消息更新 | `backend/app/api/ws.py`, `backend/app/api/ws_manager.py` |
| EventBus | 后端内部解耦事件，用于 workspace、artifact、runtime、deployment、audit 等生命周期 | `backend/app/event_bus/` |

## SSE 事件

聊天 SSE 由 `/api/sessions/{session_id}/chat` 返回。

前端消费入口：

```text
frontend/src/api/client.ts#createChatStream
frontend/src/hooks/useSendMessage.ts
```

常见事件：

| 事件 | 用途 |
| --- | --- |
| `run.started` | 创建运行记录 |
| `run.status_changed` | 更新 Run 状态 |
| `task.status_changed` | 更新 Task 状态 |
| `approval.created` | 创建审批节点 |
| `approval.status_changed` | 审批状态变化 |
| `session.title_updated` | 自动标题更新 |
| `orchestrator.route` | 群聊 Agent 路由结果 |
| `orchestrator.steward_decision` | Orchestrator 管家分流决策 |
| `orchestrator.plan_execution_created` | 计划执行创建 |
| `orchestrator.task_started` | 协作任务开始，含 tasks / dag |
| `orchestrator.chain_step` | 链式步骤状态 |
| `orchestrator.phase_change` | DAG phase 状态变化 |
| `orchestrator.summary_started` | 中枢总结开始 |
| `orchestrator.summary_delta` | 中枢总结 token |
| `orchestrator.summary_completed` | 中枢总结完成 |
| `orchestrator.task_completed` | 编排任务完成 |
| `agent.start` | 群聊 Agent 消息开始 |
| `agent.process.started` | CLI 进程启动 |
| `agent.process.completed` | CLI 进程完成 |
| `agent.process.turn_completed` | 常驻进程本轮完成 |
| `agent.output` | Agent 输出 chunk / token |
| `agent.trace.delta` | 执行轨迹增量 |
| `interactive_prompt` | CLI 交互确认提示 |
| `artifact.scan.started` | Artifact 扫描开始 |
| `artifact.created` | Artifact 创建 |
| `artifact.scan.completed` | Artifact 扫描完成 |
| `artifact.detection_failed` | Artifact 检测失败 |
| `error` | 全局错误 |

## WebSocket 事件

WebSocket 路径：

```text
/ws/sessions/{session_id}
```

当前能力：

- Session 级连接管理。
- 30 秒心跳 `ping`。
- 后端向当前 session 广播事件。
- 前端可回复 `pong` 保活。

## EventBus 事件

后端内部事件定义位于 `backend/app/event_bus/event_types.py`。

事件分组：

| 分组 | 事件示例 |
| --- | --- |
| Message | `message.created`, `message.streaming`, `message.completed` |
| Orchestrator | `orchestrator.task.started`, `orchestrator.task.completed`, `orchestrator.plan.paused`, `orchestrator.plan.resumed` |
| Agent | `agent.call.started`, `agent.call.completed`, `agent.process.started`, `agent.process.completed`, `agent.process.timeout` |
| Project / Workspace | `project.created`, `workspace.created`, `workspace.file_changed`, `workspace.diff_ready`, `workspace.snapshot.created` |
| Artifact | `artifact.detected`, `artifact.created`, `artifact.updated`, `artifact.detection_failed`, `artifact.rendered` |
| Build / Preview / Deployment | `build.started`, `preview.created`, `deployment.queued`, `deployment.published`, `deployment.failed` |
| Runtime / Sandbox | `sandbox.created`, `sandbox.ready`, `runtime.log`, `quota.exceeded`, `workspace.sync.completed` |
| Collaboration | `comment.created`, `attachment.created`, `message.forwarded`, `notification.created`, `git.sync.completed` |
| Audit / Team | `audit.recorded`, `team.member.added` |

## 新增事件规则

1. 如果事件只在一次聊天请求内消费，优先用 SSE。
2. 如果事件需要跨请求推送给当前 Session，使用 WebSocket。
3. 如果事件用于后端内部生命周期解耦，使用 EventBus。
4. 事件名称使用小写点分命名，例如 `artifact.created`。
5. 前端展示所需字段应稳定，不要依赖 CLI 私有输出格式。
6. 新增事件后同步更新本文件和相关前端 normalizer。

