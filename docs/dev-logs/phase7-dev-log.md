# Phase 7 Dev Log

**日期**: 2026-06-06 ~ 2026-06-07
**阶段**: Phase 7A-7F
**状态**: 7A 运行任务可控性、7B 人工审批断点、7C 环境体检实现基线已通过人工验收；7D 已完成 IM 基线、明亮主题与 v1.0 UI 加固；7E 已落地 Claude Code / Codex / OpenCode Engine Session Adapter 闭环；7F 已落地 Claude Code stdin JSONL 常驻进程与 Codex MCP / OpenCode ACP 常驻 RPC 基线，真实 CLI E2E 脚本仍待沉淀

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

## 2.2 7D IM 体验与 v1.0 UI 加固

2026-06-07 继续实现 IM 软件增强项和明亮主题收敛：

- 会话列表补齐搜索、置顶、归档箱、最近活跃排序、未读数和免打扰；置顶会话进入独立分组，归档对话进入顶部归档入口。
- 后端扩展 `sessions` 表：`is_pinned`、`archived_at`、`unread_count`、`last_read_at`、`is_muted`，并新增迁移 018/019。
- `SessionService` 新增 `mark_read()`、`forward_messages()` 和 pin/archive/mute 更新语义；`GET /api/sessions` 默认隐藏归档会话，支持 `includeArchived`。
- 消息右键菜单成为主要操作入口，支持引用回复、重新生成、Pin、复制、转发、多选，并通过 portal 解决遮挡和层级问题。
- 转发不做前端假状态：`POST /api/sessions/forward` 会在目标会话创建真实 user 消息，并保存 `forwardSource` 快照。
- 消息气泡底部显示完整中国时区时间戳；Agent 名称标签去掉绿点与下边框，改为独立颜色和加粗文本。
- 明亮主题辅色从浅蓝收敛为纯白；项目栏/聊天栏按飞书式大圆角容器包裹小圆角栏；输入框外层保持透明并悬浮。
- 文件区域取消局部圆角卡片包裹，改为覆盖工作区；diff/code block/Artifact 卡片保留少量辅助色以增强可读性。
- `ExecutionTracePanel` 新增全屏查看弹窗，复用执行时间线和状态统计。

本轮文档补充：

- `docs/deliverables/phase7-im-hardening/README.md`
- `docs/deliverables/phase7-im-hardening/implementation-snapshot.md`
- `docs/deliverables/phase7-im-hardening/acceptance-log.md`
- `docs/specs/phase7/04-mvp-demo-ux-hardening.md`

## 2.3 群聊调度器管家与 Plan-first 状态机收敛

2026-06-07 继续修复群聊无 @ 和小型多 Agent 协作的责任边界：

- 无 @ 群聊消息不再直接进入旧 OrchestratorV2 自动执行链路，而是先由可见的 Orchestrator 调度器 Agent 输出四档分流：`context_only`、`single_agent`、`mini_collab`、`draft_plan`。
- `context_only` 会持久化调度器回复和 `stewardDecision` metadata，用户补充“所有文档都用中文”等约束时不再出现“没人理我”的空反馈。
- `mini_collab` 复用 Plan-first DAG 契约，只生成小型 draft plan，用户批准前不启动多个普通 Agent。
- 会话存在最新待处理 draft plan 时，后续无 @ 消息直接交给 Orchestrator Agent 做 follow-up，不再重新进入四档分流；批准、修改、放弃均由调度器结构化 JSON 驱动，后端不硬编码用户文本。
- `approve_plan` 会创建 execution 并按 DAG 调度真实 CLI Agent；执行阶段补齐串行交接约束，前序 Agent 只交付本节点产物与交接说明，后序 Agent 基于依赖产物继续。
- `discard_plan` 会把旧 plan 标记为 `discarded`，下一条无 @ 消息重新回到调度器管家分流。
- 多个普通 @ 保留直接串行执行语义，并按用户 @ 顺序注入前序产出；只要 @ 列表包含 Orchestrator 调度器，本轮就进入 Plan-first，由调度器解释其它被 @ Agent 的候选关系和顺序。
- 显式 @ 的权威来源收敛为请求体里的 `mentionIds`：前端输入 `@` 时即使群成员仍在加载，也会弹出可见提示并在选择 Agent 后提交结构化 mentions；后端不再根据正文里的裸 `@名字` 兜底识别调度器，避免手输文本误触发 Plan-first。

## 2.4 7E CLI Engine Session 复用与适配器策略

2026-06-07 针对“单 Agent 私聊没有充分利用底层 CLI 自己的会话/缓存能力”的问题，完成后端最小闭环，并反思上一轮把 Claude Code 特性写成公共布尔开关的设计过浅：

- 新增 `engine_sessions` 表与 `EngineSession` 模型，显式保存 `session_id / agent_config_id / cli_tool / workspace_path / engine_session_id`。
- `CliAgentAdapter` 新增 `EngineSessionResumePolicy`，由各 Adapter 声明自己的原生命令策略、首轮启动策略、session id 来源和是否支持调用方指定 ID；公共层只负责 invocation 决策、持久化与可观测性。
- Claude Code 改为吃满原生 `--session-id <uuid>`：首轮由 AgentHub 分配稳定 UUID 并传入 Claude Code，后续通过 `engine_sessions -> claude --resume <session_id>` 复用。即使 Claude result 未返回 `session_id` metadata，成功完成后也会用 AgentHub 分配的 ID 兜底持久化；同时规范化 `claude -p --output-format stream-json` 参数，避免误带 `--no-session-persistence`。
- Codex 使用 `thread/session JSON event -> engine_sessions -> codex exec resume <session_id> -`，并过滤只属于 `codex exec` 的参数，保留 config/json/审批类 resume 可用参数。
- OpenCode 使用 `session JSON event -> engine_sessions -> opencode run --session <session_id>`，并清理旧的 `--continue / --session` 参数，避免 session id 被误当成用户 prompt。
- 单聊第二轮起若存在 active engine session，则进入 resume 模式；此时不再重复灌完整 AgentHub transcript，只发送当前轮、引用和 Pin 等显式上下文，避免底层 CLI 已有会话记忆与 AgentHub 历史拼接重复。
- 每条 Agent 消息 metadata 会记录 `engineSessionPolicy` 与 `engineSession`，便于审计某轮是否使用 CLI 原生会话能力、使用的策略和捕获来源。
- 群聊 DAG task 仍保持任务包隔离，避免不同任务共享隐式私聊记忆。
- 自动化覆盖 Claude/Codex/OpenCode 参数规范化、session metadata 捕获、三家两轮单聊复用和迁移表存在性；真实 CLI E2E 仍需补脚本验收。

## 2.5 7F Claude Code 常驻进程运行时

2026-06-07 针对“仅靠 `--resume` 仍然是每轮短进程 invocation，不是真正长连接”的问题，完成运行时层重构：

- 新增 `CliSessionProcessRuntime`，专门管理一会话一常驻 CLI 子进程，维护 stdin/stdout/stderr pump、per-session turn lock、turn line buffer 和进程 snapshot。
- `CliProcessManager` 回归短进程职责，只负责一次性 subprocess lifecycle；常驻进程状态不再混在短进程管理器内部。
- 新增 `cli_runtime_registry` 作为上层统一门面，`reply/terminate/terminate_session/active_snapshots` 同时覆盖短进程和常驻进程；`RunService`、环境体检、交互回复 API、调度取消均改走该门面。
- Claude Code Adapter 的常驻路径改为 `claude -p --output-format stream-json --input-format stream-json`，每轮 prompt 渲染为 Claude SDK user message JSONL，读取到 `type=result` 后产出 `agent.process.turn_completed`，进程继续保留。
- 同一 AgentHub session 的并发 turn 通过 session lock 串行化，避免两个用户请求交错写入同一个 stdin；不同 AgentHub session 仍使用不同子进程，互不共享状态。
- 如果常驻子进程已退出，下一轮会清理旧 handle、重启新进程并标记 `recovered=true`；当前不承诺恢复崩溃前未完成的半轮输出。
- 新增 [06-cli-session-process-runtime.md](../specs/phase7/06-cli-session-process-runtime.md)，把常驻进程模式、取消、交互提示、恢复和非目标写成正式规格。

## 3. 关键决策

- run/task/process 属于运行时控制层，不放进 ArtifactService，也不只保存在前端 streaming boolean。
- 取消必须是“用户可见状态变更 + 进程终止 + 输入框释放”的完整闭环。
- 审批卡片继续采用消息级 Artifact 心智，不恢复右侧 Drawer 或独立产物工作台。
- 环境体检是当前本机状态快照，不写入数据库；任何敏感配置只返回布尔或状态摘要。
- Phase 7D 的 IM 能力必须尽量落到真实 API/数据库状态，不能只做前端装饰；Reply/Pin 继续保留真实 Agent 上下文注入。
- 明亮主题的辅色基线改为纯白，彩色只保留在读者需要区分信息层级的可视化卡片中。
- Engine resume 和 Session Process Runtime 是 Adapter 能力，不是 AgentHub 协作正确性的基础；单聊可用 Claude Code 自己的会话记忆和常驻进程，群聊仍优先依赖显式 task package、workspace 文件和可审计消息。
- 群聊无 @ 的默认心智改为“发给调度器管家”，但不强约束每条消息都必须生成计划；能记录上下文或单 Agent 处理的轻量消息保持轻便。
- 小型多 Agent 协作不再走临时执行链路，统一复用 Plan-first 的输入、输出、依赖和验收约束，避免职责越界。
- Phase 7D-7F 真实 CLI 演示脚本、UI 截图审计、Context Pack Builder 和 Store 进一步按领域拆分仍是 v1.0 后续风险项，不阻塞已完成的 IM/Engine Session/Session Process/群聊调度器基线说明。

### 3.1 Claude Code 物理常驻复核

2026-06-07 后续用本机 `claude.exe -p --verbose --input-format stream-json --output-format stream-json --session-id <uuid>` 做双 turn 探针：首轮写入 SDK user message JSONL，读取 `type=result` 后不关闭 stdin，再写第二轮 user message；同一进程产出第二个 `type=result`。据此恢复 Claude Code 会话级常驻能力：

- Claude Code 使用 `--session-id <uuid>` 绑定底层原生 Engine session，同时由 `CliSessionProcessRuntime` 保持同一个 `claude -p` 进程。
- 同一 AgentHub 私聊第二轮命中同一个 `processId`，`agent.process.started` metadata 标记 `persistentProcess=true/reused=true`，不再再次 spawn Claude Code。
- 如果常驻进程已退出，下一轮会用已有 `engine_sessions.engine_session_id` 与 `--resume <session_id>` 拉起新进程，并标记 `recovered=true`。
- Codex `mcp-server` 与 OpenCode `acp` 的 JSON-RPC 常驻运行时保持不变；三家 CLI 的常驻协议不同，但业务层统一通过 `cli_runtime_registry` 观察、回复和终止。

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
  - 无 @ 轻量请求由可见 Orchestrator 调度器先做 steward 判断；
  - context_only 消息持久化为调度器回复；
  - 旧群聊缺少 Orchestrator 成员时自动恢复默认调度器；
  - mini_collab 生成有边界的小型 draft plan，批准前不启动普通 Agent；
  - draft plan 的无 @ 批准、放弃、修改均绕过 steward，交给 Plan-first follow-up；
  - 多 Agent DAG 执行按任务依赖推进，文档专家和架构师等下游职责不会被上游 Agent 代做。
  - 裸文本 `@Orchestrator` 但缺少 `mentionIds` 时按普通无 @ 管家分流处理，不硬编码识别为调度器提及。
- `backend/test_api/test_sessions.py`
  - 免打扰、标记已读、消息转发 API。
- `backend/test_unit/test_session_service.py`
  - 归档默认隐藏、置顶排序、取消归档、免打扰/已读、转发创建真实消息与来源快照。
- `backend/test_api/test_migrations.py`
  - 会话 IM 状态字段迁移存在性。
- `frontend/src/components/SessionList.test.tsx`
  - 置顶分组、未读/免打扰、归档箱、取消归档。
- `frontend/src/components/MessageActions.test.tsx`
  - 右键菜单、转发和多选入口。
- `frontend/src/components/MessageBubble.test.tsx`
  - 气泡右键菜单、多选控件、完整时间戳和 Agent 名称样式。
- `backend/test_unit/test_cli_adapter_runtime.py`
  - Claude Code 参数规范化、首轮 `--session-id` 绑定、`--resume` 参数清理、`result.session_id` 元数据捕获；
  - Codex `exec resume <session_id> -` 参数迁移、thread/session metadata 捕获；
  - OpenCode `run --session <session_id>` 参数清理、session metadata 捕获；
  - fixture subprocess 验证常驻进程同 session 复用、不同 session 隔离、子进程死亡后下一轮恢复、同 session 并发 turn 串行化、交互式 stdin 回写。
- `backend/test_api/test_chat.py`
  - Claude Code 首轮使用 AgentHub 分配的 `engine_session_id`，Codex / OpenCode 第一轮捕获 engine session，第二轮复用 `engine_session_id` 并只发送当前轮增量上下文。
  - Claude Code 没有返回 result metadata 时，成功路径仍会持久化 AgentHub 分配的 session id 并进入第二轮 resume。
- `backend/test_unit/test_migration_runner.py`
  - `engine_sessions` 迁移表存在性。

本轮验证命令：

```powershell
cd frontend; npx vitest run; npm run build
cd backend; pytest test_api/test_phase7_runtime.py test_api/test_group_chat.py
cd backend; pytest test_unit/test_orchestrator_summarizer.py
cd backend; pytest test_unit/test_cli_adapter_runtime.py test_unit/test_migration_runner.py test_api/test_chat.py -q
cd backend; python -m pytest test_unit/test_cli_adapter_runtime.py -q
cd backend; python -m pytest test_api/test_chat.py -q
```

群聊调度器收敛后的轻量回归命令：

```powershell
cd backend; pytest test_api/test_group_chat.py -q
cd frontend; npx vitest run src/api/client.test.ts src/hooks/useSendMessage.test.ts src/components/ChatInput.test.tsx
```

7D 回归建议命令：

```powershell
cd backend; python -m pytest test_unit/ test_api/ -q
cd frontend; npx tsc --noEmit; npx vitest run; npm run build
```

## 5. 交接入口

后续接手优先从这些文件开始：

- `backend/app/services/run_service.py`
- `backend/app/agents/cli_session_runtime.py`
- `backend/app/agents/cli_runtime_registry.py`
- `backend/app/services/approval_service.py`
- `backend/app/services/system_health_service.py`
- `backend/app/services/single_cli_chat_stream.py`
- `backend/app/services/group_chat_stream.py`
- `backend/app/services/orchestrator_steward_chat.py`
- `backend/app/services/orchestrator_plan_chat.py`
- `frontend/src/components/RuntimeControlStrip.tsx`
- `frontend/src/components/ApprovalCard.tsx`
- `frontend/src/components/HealthCheckCard.tsx`
- `frontend/src/stores/chatStore.ts`
- `docs/deliverables/phase7-runtime-control/README.md`
- `frontend/src/components/SessionList.tsx`
- `frontend/src/components/MessageActions.tsx`
- `frontend/src/components/MessageBubble.tsx`
- `frontend/src/components/ExecutionTracePanel.tsx`
- `backend/app/services/session_service.py`
- `docs/deliverables/phase7-im-hardening/README.md`

Phase 7F 之后的下一步是把真实 Claude Code 演示脚本、截图审计和完整回归矩阵补齐，并继续推进 Context Pack Builder 与 Store 领域拆分；常驻进程真实长跑验收应单独记录。
