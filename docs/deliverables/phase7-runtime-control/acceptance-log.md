# Phase 7A-7C 验收日志

**日期**: 2026-06-06
**结论**: 本轮验收通过

## 1. 人工验收结论

本轮人工验收确认以下能力达到 Phase 7A-7C 标准：

- 发送任务后会创建 run/task/process 状态，前端能看到运行控制条。
- 运行控制条提供停止按钮，停止后对话中出现明确的中止成功消息。
- 停止后输入框恢复为可输入状态，不再显示 AI 正在回复。
- 停止当前输出不会继续占用其它对话框。
- 需要人工确认的任务会在消息下方出现 ApprovalCard。
- 确认继续、驳回修改走真实 API 和持久化 checkpoint，不是静态 UI。
- ChatHeader 可看到环境体检状态，发送前会用 blockingReasons 阻断不可执行环境。
- IM 状态入口已收敛到 Agent 名称下方；消息气泡头像旁不再出现独立“正在回答/typing”状态。
- 切换到其它对话后，原对话后台输出不会丢失，会话列表会显示“对方正在输入”。
- 不同会话可以并行保留独立运行实例，不再被单个全局 streaming 状态占用。
- 群聊不再每轮自动生成中枢总结消息。
- 项目时间显示、前端本地时间与后端事件时间统一为中国时区口径。

## 2. 人工验收缺陷修复记录

缺陷：暂停本次输出后没有明确消息提示中止成功；对话框仍显示 AI 正在回复；其它所有对话框被占用，不能继续对话。

修复：

- 前端停止按钮立即 abort 当前 SSE；
- 本地 run/task/message 状态立即回退为 cancelled；
- 当前会话追加运行控制系统消息；
- 输入框立即解锁；
- 后端 `cancel_run` 持久化 cancelled 状态并追加同类系统消息；
- 增加前端回归测试覆盖“后端取消请求未返回时，本地仍能立即中止和解锁”。

二次修复：

- `useSendMessage` 不再用当前页面 active stream 过滤后台 SSE 事件，改为按 streamKey 注册状态判断；
- `SessionList` 接入 per-session runtime，在后台运行会话上展示“对方正在输入”；
- 移除普通会话切换时的重复视图 reset 和项目会话列表重复加载；
- `MessageBubble` 只接收当前消息相关 artifacts/approvals，减少切换和流式输出时的全量重渲；
- 移除聊天/产物预览同步代码高亮库，降低主包体积和渲染成本；
- `GroupChatFinalizer` 不再调用 OrchestratorSummarizer 自动生成总结。

## 3. 自动测试覆盖

新增和更新的自动测试覆盖：

```powershell
cd backend
pytest test_api/test_phase7_runtime.py test_api/test_group_chat.py
pytest test_unit/test_orchestrator_summarizer.py
```

覆盖点：

- chat 创建 run/task/process 并最终 completed；
- completed run 重复 cancel 返回 200 和原 completed 状态；
- cancelled run 不被迟到的 process completion 覆盖；
- cancel run 追加可见“本次运行已中止”消息；
- 审批 checkpoint 创建、approve、重复 reject 409；
- system health 无上下文可返回；
- 缺失 workspace 进入 blockingReasons；
- health payload 不泄露测试密钥。
- 群聊 route/task/agent/run 事件正常；
- 群聊消息正常落库；
- 群聊不再产生 `orchestrator.summary_*` SSE 或 `orchestrator_summary` 消息。

```powershell
cd frontend
npx vitest run
npm run build
```

覆盖点：

- 后端取消请求未返回时，点击停止也会立即 abort、解锁输入框并显示中止成功消息；
- chat store 的 run/task/approval 合并和本地取消回退；
- 不同会话可同时保留独立 streaming runtime；
- 后台运行会话在 SessionList 展示“对方正在输入”；
- 生产构建通过，主包约 499 KB，CodeMirror 编辑器保持懒加载 chunk。

## 4. 剩余风险

- Phase 7D 的真实 Claude Code 完整演示脚本尚未沉淀为自动化 E2E。
- `chatStore` 当前承载了 runtime/approval/systemHealth 状态，满足本轮功能验收，但后续可继续拆为独立 store。
- 审批释放下游任务已完成状态机基线，完整 Orchestrator scheduler 的多阶段自动续跑仍需后续增强。
- 环境体检只做检测和阻断，不自动安装 CLI 或修复本机权限。
