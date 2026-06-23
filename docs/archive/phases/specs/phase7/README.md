# Phase 7: 任务可控性 + 审批 + 环境体检 + 演示闭环

**版本**: v3.8
**创建日期**: 2026-06-06
**状态**: v1.0 Baseline — 7A/7B/7C 已验收，7D IM 基线与 v1.0 UI 加固已实现；7E/7F 已落地 Engine Session、Claude Code stdin JSONL 常驻进程与 Codex/OpenCode 常驻 RPC 基线；群聊已同步单聊的 Agent runtime 与 workspace Artifact 链路；7G 已完成群聊人机协作控制权诊断，待按切片修复；真实 CLI 完整自动化演示脚本待沉淀
**关联 ADR/PRD**: [ADR-0008](../../../../archive/adr/0008-revised-development-strategy.md)、[ADR-0009](../../../../archive/adr/0009-project-workspace-model.md)、[ADR-0010](../../../../archive/adr/0010-message-level-artifact-experience.md)、[PRD-02](../../../../PRD/02-Orchestrator_Engine.md)、[PRD-03](../../../../PRD/03-User_Experience.md)、[PRD-05](../../../../PRD/05-End_to_End_Product_Flow.md)、[PRD-06](../../../../PRD/06-MVP_Local_Workspace_Delivery.md)
**依赖模块**: Phase 4 消息交互闭环、Phase 5 Artifact 版本/编辑、Phase 6 Workspace Runtime + CLI Adapter + Artifact Bridge

> 2026-06-06 重构说明：旧 Phase 7 文档仍围绕右侧 Artifact Drawer、独立产物工作台和旧 Store 收尾展开，已经与当前实现路线不一致。Phase 6F 已验收的基线是：产物与代码变更作为消息级 Artifact 卡片跟随具体 assistant 消息展示，预览/编辑/版本管理通过页面级弹窗和会话文件入口完成。Phase 7 不再重新实现 Drawer，也不再恢复独立产物工作台。

---

## 1. 目标

Phase 7 的目标是把 Phase 1-6 已有的聊天、真实 CLI 执行、workspace 文件变更、消息级 Artifact 卡片、文件编辑器、代码引用和版本管理，推进到可答辩、可演示、可中断、可恢复的产品闭环。

当前仍缺的不是“产物展示入口”，而是五类体验闭环能力：

- 运行中的任务可被用户理解、取消、恢复；
- Orchestrator/Agent 的关键节点可暂停等待用户审批；
- 本机 CLI、运行时、workspace、系统模型状态可提前体检；
- 会话列表与消息操作达到 IM 软件的 v1.0 基线，而不是只停留在开发工具式列表；
- 真实 Claude Code 等 CLI 服务路径可被稳定脚本化验收。

**成功标准**（可证伪）：

- [x] 用户能在一次真实 CLI 任务运行中看到当前 run/task 状态，并能取消正在运行的 CLI 进程。
- [x] 需要人工确认的任务能生成 Approval Card；确认后继续，驳回后回到对话修订，并携带 Artifact/代码引用上下文。
- [x] `/api/system/health` 能返回 CLI Agent、Node/Python、workspace、系统模型、活跃进程的统一健康状态；前端在创建/发送关键路径前给出阻断或降级提示。
- [x] 会话列表支持搜索、置顶、归档箱、未读数、免打扰、最近活跃排序；消息支持右键菜单、转发、多选、完整时间戳。
- [x] 明亮主题辅色收敛为纯白，输入框外层透明，项目/聊天栏形成圆角卡片层级，执行过程支持全屏查看。
- [ ] MVP 演示脚本跑通：Project 绑定 workspace → 与 Claude Code 真实对话 → 生成消息级 Artifact → 编辑/引用/版本管理 → 审批继续 → 中枢总结。
- [ ] 不通过标准：重新引入独立产物工作台、右侧 Artifact Drawer，或只做静态 UI 而不接真实 API/事件/持久化状态。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
Project workspace
  → CLI Agent / Orchestrator 执行
  → ArtifactOutputBridge
  → 消息级 ArtifactCard + FileEditorModal + ArtifactVersionManager
  → [Phase 7] run/task 可控性 + Approval Card + HealthCheck
  → 真实服务 MVP 演示闭环
```

### 2.2 已完成与本阶段边界

| 分类 | 当前状态 | Phase 7 处理方式 |
|------|----------|------------------|
| 消息级 Artifact 卡片 | Phase 6F 已验收 | 作为输入基线消费，不重做 |
| file_tree / code_diff / web_preview / document UI | Phase 6F 已验收 | 审批卡片可引用这些产物 |
| 文件编辑器、代码片段引用、版本管理 | Phase 6F 已验收 | 审批驳回和演示脚本复用 |
| 独立产物工作台 | 已移除 | 不恢复 |
| 右侧 Artifact Drawer | P1 当前路线废弃 | 不进入 Phase 7 范围 |
| 任务运行状态、取消、恢复 | 未完成 | Phase 7A |
| Human-in-the-loop 审批 | 未完成 | Phase 7B |
| 统一环境体检 | 未完成 | Phase 7C |
| 演示脚本与 UX 加固 | 未完成 | Phase 7D |

### 2.3 上下游契约

| 方向 | 模块/事件/API | 本阶段的角色 |
|------|-------------|------------|
| **上游输入** | Phase 6 CLI SSE: `agent.process.*`、`agent.output`、`artifact.created` | 识别运行状态、产物、可取消进程 |
| **上游输入** | Phase 5 Artifact API: versions/diff/save/restore | 审批和演示脚本消费现有版本能力 |
| **下游产出** | `run.*`、`task.status_changed`、`approval.*`、`system.health.updated` | 前端 Store 和 UI 卡片消费 |
| **下游产出** | 新 API: runs/cancel、approval、system health | 真实服务验收与前端可控性 |
| **本阶段不通** | P2 SaaS 沙箱、一键部署、多人权限审批、完整 IDE、右侧 Drawer | 后续阶段或明确不做 |

---

## 3. 子模块索引

| 模块 | Spec 文档 | 状态 | 核心交付 |
|------|----------|------|---------|
| **7A: 运行任务可控性** | [01-runtime-task-control.md](01-runtime-task-control.md) | ✅ 验收通过 | 持久化 run/task/process 状态、取消运行、进程清理、前端运行控制条 |
| **7B: 人工审批断点** | [02-approval-checkpoints.md](02-approval-checkpoints.md) | ✅ 验收通过 | ApprovalCheckpoint 数据模型、确认/驳回 API、聊天流 Approval Card、Artifact/代码引用回流 |
| **7C: 环境体检** | [03-environment-health.md](03-environment-health.md) | ✅ 验收通过 | `/api/system/health`、CLI/Node/Python/workspace/DeepSeek/进程状态、HealthCheckCard 与发送前 guard |
| **7D: IM 体验、演示与 UX 加固** | [04-mvp-demo-ux-hardening.md](04-mvp-demo-ux-hardening.md) | 🚧 IM 基线已实现 | 会话置顶/归档/未读/免打扰/转发/多选、右键菜单、明亮主题纯白与圆角布局、执行过程全屏；真实 cc 脚本待补 |
| **7E: 上下文包与缓存策略** | [05-context-pack-and-cache-strategy.md](05-context-pack-and-cache-strategy.md) | Draft | 记录短进程 transcript 拼接的上下文/缓存风险，提出 Context Pack、Project Memory、Task Package、Engine Session 与常驻进程路线 |
| **7F: CLI Session Process Runtime** | [06-cli-session-process-runtime.md](06-cli-session-process-runtime.md) | ✅ 实现基线 | 单聊按 Session+Agent 复用常驻进程；群聊按 Session+Agent 独立 runtime 复用；Claude Code stdin JSONL、Codex/OpenCode RPC、turn 边界、并发串行、取消和恢复 |
| **7G: 群聊人机协作控制权诊断** | [07-group-chat-human-control-diagnosis.md](07-group-chat-human-control-diagnosis.md) | Draft | 诊断真实群聊验收中“想直接和产品经理聊却被迫走计划”的体验问题，定义 direct dialog、访谈等待态、手动交接和测试修改清单 |
| **7H: Orchestrator 执行中断与断点恢复** | [08-orchestrator-execution-resume.md](08-orchestrator-execution-resume.md) | Draft | 将停止与取消拆分：停止进入 interrupted，可刷新找回并通过结构化 Resume 从未完成任务继续；放弃才进入 cancelled 终态 |

2026-06-06 验收记录：7A/7B/7C 已完成实现基线并通过本轮人工验收。验收中发现的“停止输出后无明确中止提示、输入框仍显示 AI 正在回复、其它会话被全局占用”问题已修复：前端点击停止后立即 abort 当前流、本地标记 run/message 为 cancelled、追加可见“本次运行已中止成功”系统消息并解锁输入框；后端取消也会持久化 cancelled metadata 和运行控制消息。

2026-06-07 7D 实现记录：会话列表补齐 IM 基线，包括搜索、置顶分组、归档箱、未读数、免打扰和最近活跃排序；消息气泡改为右键菜单，支持引用、重新生成、Pin、复制、转发和多选；转发通过真实 API 创建目标会话消息并保留来源快照；明亮主题辅色收敛为纯白，输入框外层透明，执行过程可全屏查看。旧 `phase7-im-hardening` 交付快照目录已在 2026-06-22 文档整理中删除，当前追溯入口为本文与 [Phase 7 Dev Log](../../dev-logs/phase7-dev-log.md)。

2026-06-08 群聊同步记录：群聊 Agent 调用链路已与单聊 runtime/Artifact 基线对齐。`CliAgentExecutor` 会按真实群聊 `session_id` 与 `agent_id` 解析 EngineSession、生成群聊内专属 runtime key，并在每个 Agent 执行前创建 workspace snapshot；`GroupChatFinalizer` 将运行 metadata 与 snapshot 写入对应 Agent 消息，再由 Artifact Bridge 扫描该消息的 workspace diff、文本代码块和执行轨迹。产物绑定具体 Agent message/sourceId，不挂到 Orchestrator 总结或会话级全局位置。

---

## 4. 已删除的旧 Phase 7 内容

| 旧内容 | 删除原因 | 当前替代方案 |
|--------|----------|--------------|
| `ArtifactDrawer.tsx` / 右侧抽屉 | 与 2026-06-06 用户确认的消息级卡片路线冲突 | `MessageArtifactStrip` + `ArtifactCard` 页面级弹窗 |
| 独立产物工作台 | 已在 Phase 6F 移除并验收 | Chat Header 文件按钮打开 `SessionArtifactManager` |
| Drawer 内左右/上下 Diff 模式 | 已被 VS Code/GitHub 风格 unified diff 替代 | `DiffViewer` 统一视图 |
| Drawer 内 CodeSelector 在线编辑 | 旧组件已删除 | `FileEditorModal` + CodeMirror + 代码引用 |
| 起始/变更版本选择器 | 已确认不需要 | 最新版本固定与上一版本比较，版本管理另开专属界面 |
| “Store 收尾”泛泛条目 | 不足以指导实现 | 拆入 run/approval/health/demo 四个具体 Store 契约 |

---

## 5. Phase 7 总体验结构

```text
┌─────────────────┬───────────────────┬────────────────────────────────┐
│ ProjectSidebar   │ SessionSidebar     │ ChatWorkspace                  │
│                 │                   │ ┌────────────────────────────┐ │
│ CLI Agent 状态   │ 会话列表/搜索       │ │ ChatHeader                 │ │
│ Project 列表     │                   │ │  Search + Files + Health   │ │
│ HealthCheckCard  │                   │ ├────────────────────────────┤ │
│                 │                   │ │ MessageList                │ │
│                 │                   │ │  MessageBubble             │ │
│                 │                   │ │  RuntimeControlStrip       │ │
│                 │                   │ │  MessageArtifactStrip      │ │
│                 │                   │ │  ApprovalCard              │ │
│                 │                   │ ├────────────────────────────┤ │
│                 │                   │ │ ChatInput                  │ │
│                 │                   │ └────────────────────────────┘ │
└─────────────────┴───────────────────┴────────────────────────────────┘
```

视觉原则：

- 保持当前紧凑生产力工具风格，不做营销式 hero 或大面积装饰。
- 新增 UI 都使用 lucide 图标，不使用 emoji 或文本占位。
- 操作入口靠近上下文：运行控制在正在回答的消息/头像旁，审批在需要审批的消息下方，健康状态在左栏和 ChatHeader 提供紧凑入口。
- 所有弹层都使用页面级 portal overlay，不能被消息气泡、iframe 或滚动容器裁剪。

---

## 6. 全局验收矩阵

| 编号 | 验收项 | 对应模块 |
|------|--------|----------|
| AC-P7-01 | 开始一次真实 Claude Code 对话后，前端显示 run/task 正在运行，并能通过取消按钮终止进程 | 7A |
| AC-P7-02 | 取消后后端进程不存在，assistant 消息标记为 cancelled，输入框恢复可用 | 7A |
| AC-P7-03 | 需要审批的任务完成后生成 Approval Card，后续任务不会自动开始 | 7B |
| AC-P7-04 | 点击审批卡片主区域能打开现有 Artifact 预览/版本管理，而不是 Drawer | 7B |
| AC-P7-05 | 审批确认后任务状态变为 approved/completed，并释放下游任务 | 7B |
| AC-P7-06 | 审批驳回后 ChatInput 自动带上 Artifact/代码引用，用户可直接描述修改意见 | 7B |
| AC-P7-07 | `/api/system/health` 返回 overall + items + blockingReasons，且不暴露任何密钥值 | 7C |
| AC-P7-08 | CLI 缺失或 workspace 不可写时，创建/发送关键路径显示明确阻断提示 | 7C |
| AC-P7-09 | 会话列表置顶、归档箱、未读、免打扰、搜索、最近活跃排序均持久化并可刷新恢复 | 7D |
| AC-P7-10 | 消息右键菜单支持引用/重新生成/Pin/复制/转发/多选，且 Reply/Pin 仍影响 Agent 上下文 | 7D |
| AC-P7-11 | 执行过程可全屏查看，弹窗不被聊天容器裁剪 | 7D |
| AC-P7-12 | 真实 cc 演示脚本可在本机服务完整跑通并生成验收日志 | 7D |
| AC-P7-13 | 全量回归：backend pytest、frontend tsc/vitest、E2E smoke 均通过 | 7D |
| AC-P7-14 | 群聊同一 Agent 多轮复用群聊内专属 runtime/EngineSession，且每个 Agent 写出的 workspace 产物绑定各自消息 | 7F + Phase 6F |

---

## 7. 测试策略

| 层级 | 最低覆盖 | 说明 |
|------|----------|------|
| 后端单元 | 30 条 | run/task 状态机、approval 状态转换、health probe 聚合、取消幂等 |
| API 测试 | 20 条 | runs、cancel、approval approve/reject、system health、错误态 |
| 前端组件 | 20 条 | RuntimeControlStrip、ApprovalCard、HealthCheckCard、ChatInput 引用回流 |
| E2E | 5 场景 | 真实服务或测试 CLI：运行→取消、审批→确认、审批→驳回、健康阻断、完整 cc 演示 |
| 真实服务验收 | 1 场景 | Claude Code 真实写入 workspace，覆盖 Artifact、编辑、审批、总结 |

---

## 8. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 6/7 CLI Runtime | `cli_runtime_registry.terminate_session()`、`active_snapshots()`、`reply()`、`agent.process.*` SSE | 已就绪，统一覆盖短进程、Claude Code 会话级常驻 stdin JSONL 进程与 Codex/OpenCode 会话级常驻 RPC 进程；群聊按 `session_id + agent_id` 隔离 runtime，按真实 session 聚合控制 |
| Phase 6 Artifact Bridge | `artifact.created`、`GET /api/sessions/{id}/artifacts`、消息级 ArtifactCard | 已验收；群聊 Agent 子消息已支持 workspace diff Artifact 归属 |
| Phase 5 ArtifactService | `save`、`restore`、`versions`、`diff` | 已验收 |
| Phase 3 Orchestrator | DAG phase/task 概念、summary 事件 | 已有基础，但缺持久化 run/task |
| Agent Registry | `/api/agents`、`/api/agents/check-executable` | 已就绪，可被 Health API 聚合 |
| System LLM | `system_model_status()` | 已就绪，可被 Health API 聚合 |

---

## 9. Non-Goals

| 不做的事 | 原因 | 后续归属 |
|---------|------|----------|
| 不实现右侧 Artifact Drawer | 当前 P1 产品路线改为消息级 Artifact 卡片 + 页面级弹窗 | ADR-0010 |
| 不恢复独立产物工作台 | 已被会话文件入口和消息级卡片替代 | 无 |
| 不做多人审批权限/审计报表 | MVP 只需单用户本机流程 | P2 企业增强 |
| 不自动安装 CLI/Node/Python | 本机 CLI 由用户外部安装 | 文档/引导 |
| 不做云端沙箱/一键部署 | P1 桌面版范围外 | P2 SaaS |
| 不做完整 IDE 调试器 | 当前编辑器只承担文件编辑和代码引用 | 远期可评估 |

---

## 10. 版本历史

- v1.0 (2026-06-03): 旧版 Phase 7，围绕 Artifact Drawer、审批、环境体检、Store 收尾。
- v2.0 (2026-06-05): 补充 Phase 6F 后的 Artifact Bridge 下游预期。
- v3.0 (2026-06-06): 删除陈旧 Drawer/产物工作台方向，按当前实现基线重构为运行可控性、审批、环境体检、演示加固四个模块。
- v3.1 (2026-06-06): 同步 7A/7B/7C 实现基线与人工验收结果，7D 保持后续演示加固范围。
- v3.2 (2026-06-07): 同步 7D IM 基线、明亮主题/布局加固、消息右键菜单、转发/多选、执行过程全屏和交付快照入口。
- v3.3 (2026-06-07): 同步 v1.0.0 发布摘要入口，明确真实 cc 完整自动化演示脚本仍为后续增强项。
- v3.4 (2026-06-07): 新增 7E 上下文包与缓存策略，记录历史短进程 transcript 拼接导致的上下文爆炸与缓存不可控风险。
- v3.5 (2026-06-07): 新增 7F CLI Session Process Runtime，将 Claude Code 单聊升级为一会话一常驻 stdin JSONL 进程，并通过 `cli_runtime_registry` 统一运行时控制入口。
- v3.6 (2026-06-07): 复核 Claude Code 物理常驻口径：本机 `stream-json` 双 turn 探针确认同一存活进程可复用；Codex/OpenCode 常驻 RPC 保持实现基线。
- v3.7 (2026-06-08): 同步群聊重构：群聊按 `session_id + agent_id` 拥有独立 EngineSession/runtime，Artifact Bridge 基于每个 Agent 消息 snapshot 扫描 workspace diff 并绑定产物。
- v3.8 (2026-06-08): 新增 7G 群聊人机协作控制权诊断，明确 direct dialog、awaiting_user_input、manual handoff 和 pending plan 覆盖修复清单。
- v3.9 (2026-06-09): 新增 7H Orchestrator 执行中断与断点恢复，定义 interrupted/resume/cancel 状态机和上下文隔离要求。
