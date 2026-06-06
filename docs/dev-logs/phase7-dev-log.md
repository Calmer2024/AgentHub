# Phase 7 Dev Log

**日期**: 2026-06-06
**阶段**: Phase 7A-7C
**状态**: 7A 运行任务可控性、7B 人工审批断点、7C 环境体检实现基线已通过本轮人工验收；并完成一轮对话 UX、并行运行与前端性能修复

---

## 1. 本阶段完成内容

本轮按 Phase 7 规格完成前三个核心模块：

- 新增运行状态持久化：`runs`、`run_tasks`、`run_processes`，覆盖单聊和群聊 CLI 执行。
- 新增运行控制 API：`GET /api/sessions/{id}/runs`、`GET /api/runs/{id}`、`POST /api/runs/{id}/cancel`、tasks/processes 查询。
- 单聊 CLI 流和群聊流接入 `run.started`、`run.status_changed`、`task.status_changed`、进程绑定和完成状态同步。
- 新增取消闭环：后端终止 run 下进程或 session 活跃进程，写入 cancelled metadata，并追加可见的运行控制系统消息。
- 新增 `approval_checkpoints` 表与 ApprovalService，支持 pending_review、approved、rejected 状态转换。
- 新增审批 API：列表、详情、approve、reject；重复审批返回 409，空驳回原因返回 400。
- 单聊和群聊支持通过 `requiresHumanApproval` metadata 生成 Approval Checkpoint，并在关联消息下方渲染 ApprovalCard。
- 新增统一环境体检：`SystemHealthService` 聚合 CLI Agent executable、Codex 本机配置、Node/Python、workspace、DeepSeek 系统模型、活跃 CLI 进程。
- 新增 `/api/system/health` 与 `/api/system/health/check`，并保证返回 payload 不暴露 API key/token。
- 前端 ChatHeader 接入 `HealthCheckCard`，发送前执行 health guard；blockingReasons 存在时阻断发送并显示原因。
- 前端 `RuntimeControlStrip` 显示运行状态、任务、耗时和停止按钮。
- 前端 `ApprovalCard` 提供关联 Artifact 入口、确认继续、驳回修改。
- 前端 Store 增加 run/task/approval/health 状态，并按 session 恢复运行与审批数据。

## 2. 人工验收缺陷与修复

本轮人工验收发现一个 P0 体验缺陷：

- 用户点击停止后，对话中没有明确消息提示“中止成功”；
- 输入框仍显示 AI 正在回复；
- 其它会话也被全局占用，用户不能继续对话；
- 实际表现像隐藏了按钮，但没有完成中止和回退。

已修复：

- 点击停止后前端立即调用当前 SSE abort，并本地回退 run/message 状态为 `cancelled`；
- `ChatInput` 立即恢复可输入状态，顶部状态从“对方正在输入”恢复为 Agent 状态；
- 当前会话追加“本次运行已中止成功，可以继续发送新消息。”系统消息；
- 后端 `RunService.cancel_run()` 会终止进程、取消 task/process、合并 message metadata，并持久化一条来源为“运行控制”的系统消息；
- 即使后端取消请求未返回，前端也会先完成本地解锁，避免所有对话框被一次长请求占用。

## 2.1 UX / 并行 / 性能二次修复

本轮继续修复人工验收后的 7 个前端体验问题：

- 对话气泡内不再渲染 Agent 头像旁的独立 typing 状态；IM 唯一状态入口收敛到 ChatHeader 的 Agent 名称下方。
- 左侧项目标题已统一为“项目”，好友标题保留图标入口。
- 后端事件时间 `china_now_iso()`、workspace snapshot 与前端本地时间工具统一为 `Asia/Shanghai` / `+08:00` 口径。
- 群聊收尾不再自动生成 `orchestrator.summary_*` 中枢总结事件，也不再写入 `orchestrator_summary` 消息。
- SSE 回调从“当前活动会话”解耦为按 `streamKey/sessionId` 写回原会话缓存，切到其它对话后后台输出不会丢失。
- 不同会话可各自保留独立 stream/run/abort，后台会话继续运行；会话列表会显示“对方正在输入”提示。
- 优化会话切换性能：移除普通会话切换时的重复 reset，避免 `loadSessionsForProject` 因 `currentSessionId` 变化反复拉取；消息气泡改为接收预索引后的 artifacts/approvals；移除聊天/产物预览中的同步 `react-syntax-highlighter`，主包从约 1.13 MB 降至约 499 KB。

## 3. 关键决策

- run/task/process 属于运行时控制层，不放进 ArtifactService，也不只保存在前端 streaming boolean。
- 取消必须是“用户可见状态变更 + 进程终止 + 输入框释放”的完整闭环。
- 审批卡片继续采用消息级 Artifact 心智，不恢复右侧 Drawer 或独立产物工作台。
- 环境体检是当前本机状态快照，不写入数据库；任何敏感配置只返回布尔或状态摘要。
- Phase 7D 继续处理演示脚本、UI 截图审计和 Store 进一步按领域拆分，不阻塞 7A-7C 验收结论。

## 4. 验证状态

本阶段新增自动化覆盖：

- `backend/test_api/test_phase7_runtime.py`
  - chat 创建 run/task/process 并完成；
  - completed run cancel 幂等；
  - cancelled run 不被迟到的 process completion 覆盖；
  - cancel run 追加可见运行控制消息；
  - 显式审批请求创建 checkpoint，approve 成功，重复 reject 返回 409；
  - system health 无上下文时返回系统快照且不泄露密钥；
  - 缺失 workspace 进入 blockingReasons。
- `frontend/src/components/ChatWindow.test.tsx`
  - 后端取消请求不返回时，点击停止也会立即中止本地回复、调用 abort、解锁输入框并显示中止成功消息。
- `frontend/src/components/SessionList.test.tsx`
  - 后台运行会话在列表中展示“对方正在输入”。
- `frontend/src/stores/chat.test.ts`
  - run/task/approval 状态合并与取消回退；
  - 不同会话可同时保留独立 streaming runtime。
- `backend/test_api/test_group_chat.py`
  - 群聊仍保留 route/task/agent events 和消息落库，但不再产生中枢总结事件或总结消息。

本轮验证命令：

```powershell
cd frontend; npx vitest run; npm run build
cd backend; pytest test_api/test_phase7_runtime.py test_api/test_group_chat.py
cd backend; pytest test_unit/test_orchestrator_summarizer.py
```

## 5. 交接入口

后续接手优先从这些文件开始：

- `backend/app/services/run_service.py`
- `backend/app/services/approval_service.py`
- `backend/app/services/system_health_service.py`
- `backend/app/services/single_cli_chat_stream.py`
- `backend/app/services/group_chat_stream.py`
- `frontend/src/components/RuntimeControlStrip.tsx`
- `frontend/src/components/ApprovalCard.tsx`
- `frontend/src/components/HealthCheckCard.tsx`
- `frontend/src/stores/chatStore.ts`
- `docs/deliverables/phase7-runtime-control/README.md`

Phase 7D 的下一步是把真实 Claude Code 演示脚本、截图审计和完整回归矩阵补齐。
