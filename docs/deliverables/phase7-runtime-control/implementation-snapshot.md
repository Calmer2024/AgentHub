# Phase 7A-7C 实现快照

**日期**: 2026-06-06
**状态**: 验收通过

## 1. 后端运行控制

本轮新增 Phase 7 运行时数据模型与服务：

- `backend/app/models/run.py`
- `backend/app/services/run_service.py`
- `backend/app/api/runs.py`
- `backend/migrations/016_phase7_runtime_approval.sql`

新增表：

- `runs`：一次用户请求或群聊协作的运行记录；
- `run_tasks`：run 下的 Agent/task 状态；
- `run_processes`：CLI runtime process 与 run/task 的绑定关系；
- `approval_checkpoints`：人工审批断点。

`RunService.cancel_run()` 是取消闭环的核心：它会把 run 标记为 cancelling，按 processId 终止进程；没有 process 记录时按 session 终止活跃进程；随后把未完成 task/process 标记为 cancelled，合并当前 assistant message metadata，并追加来源为“运行控制”的系统消息。

## 2. CLI 流接入

单聊路径 `single_cli_chat_stream.py` 在执行前创建 run/task，收到 `agent.process.started` 后绑定 process，完成后按成功、失败、取消、审批暂停更新 run/task 状态。SSE 新增：

- `run.status_changed`
- `task.status_changed`
- `approval.created`

群聊路径 `group_chat_stream.py` 为 Orchestrator 拆出的每个 Agent call 创建 task，并将真实 process event 绑定到对应 task。需要审批时，最后一个 task 可进入 paused 并创建 checkpoint。

## 3. 审批断点

`ApprovalService` 提供：

- pending checkpoint 幂等创建；
- approve：checkpoint 变为 approved，task 变为 completed，run 从 task 状态重新汇总；
- reject：checkpoint 变为 rejected，记录 reason/codeReference，task 变为 rejected；
- message metadata 同步 `approvalCheckpointId` 与 `approvalStatus`。

API：

- `GET /api/sessions/{sessionId}/approvals`
- `GET /api/approvals/{checkpointId}`
- `POST /api/approvals/{checkpointId}/approve`
- `POST /api/approvals/{checkpointId}/reject`

## 4. 环境体检

`SystemHealthService` 聚合当前本机环境快照：

- CLI Agent executable 状态；
- Codex 本机配置状态；
- Node/Python runtime；
- Project workspace 是否存在、可读、可写；
- DeepSeek 系统模型是否配置；
- 当前活跃 CLI 进程数。

API：

- `GET /api/system/health`
- `POST /api/system/health/check`

返回结构包含 `overall`、`items`、`blockingReasons`，敏感配置只返回布尔或状态摘要，不返回 API key/token。

## 5. 前端体验

新增组件：

- `RuntimeControlStrip`：显示 run 状态、task 名称、耗时和停止按钮；
- `ApprovalCard`：显示审批标题、摘要、关联 Artifact、确认/驳回；
- `HealthCheckCard`：显示环境就绪/警告/阻断状态与刷新入口；
- `ArtifactReviewModal`：审批卡片打开关联 Artifact 预览时复用消息级 Artifact 心智。

`useSendMessage` 在发送前调用 `checkSystemHealth()`，存在 blockingReasons 时阻断发送。SSE 收到 run/task/approval 事件后 upsert 到 store，并在切换会话时通过 REST 拉取 runs/approvals 恢复状态。

## 6. 取消回退修复

本轮人工验收指出：暂停输出后 UI 仍显示 AI 正在回复，所有对话框被占用。修复后：

- `ChatWindow.handleCancelRun()` 先调用 `cancelRunLocally()`，再异步请求后端取消；
- `cancelRunLocally()` 调用当前 SSE abort，清空 activeStreamKey/activeRunId/activeStreamAbort/isStreaming；
- 当前 message metadata 写入 `runStatus: "cancelled"`；
- 当前会话追加“本次运行已中止成功，可以继续发送新消息。”系统消息；
- 任务和运行状态本地同步为 cancelled；
- 后端请求失败时仅显示提示，不重新锁住输入框。

## 7. 本轮 UX / 并行 / 性能加固

在 7A-7C 验收通过后，本轮继续处理对话体验与并发运行问题：

- ChatHeader 成为唯一 IM 状态入口：运行中显示“对方正在输入”，消息气泡内不再显示独立 typing 状态。
- 后台会话流式输出按 `streamKey/sessionId` 写回原会话缓存，切换到其它对话不会丢失正在生成的消息、trace、artifact 或 approval 事件。
- `chatStore` 支持不同会话同时保留独立 `activeStreamKey`、`activeRunId`、abort handler 和 runtime 状态；会话列表会给后台运行会话显示“对方正在输入”。
- 禁用群聊收尾自动中枢总结：后端不再发送 `orchestrator.summary_*`，也不再落库 `orchestrator_summary` 消息。
- 前端切换性能优化：普通会话切换不再重复 reset，不再因为 `currentSessionId` 变化反复拉取整个项目会话列表；消息气泡改为接收预索引后的相关 artifacts/approvals。
- 移除聊天正文和产物文本预览里的同步 `react-syntax-highlighter`，保留轻量 `<pre><code>` 展示；CodeMirror 仍只在文件编辑器打开时懒加载。主包从约 1.13 MB 降至约 499 KB。
- 非数据库事件时间改为明确 `Asia/Shanghai` / `+08:00` 输出，前端显示继续使用统一中国时区工具。
