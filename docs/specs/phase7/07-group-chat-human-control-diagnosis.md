# 7G: 群聊人机协作控制权诊断与修复清单

**状态**: 诊断完成 / 核心闭环已实现 / 持续验收  
**创建日期**: 2026-06-08  
**关联**: [PRD-02](../../PRD/02-Orchestrator_Engine.md)、[PRD-03](../../PRD/03-User_Experience.md)、[ADR-0007](../../adr/0007-orchestrator-architecture.md)、[群聊调度器管家路由](../phase3/02-orchestrator/11-group-chat-steward-routing.md)、[Phase 7 README](README.md)

---

## 1. 背景

2026-06-08 真实人工验收中，用户用 AgentHub 群聊模拟“小型宠物洗护店预约介绍页”需求，期望先和产品经理反复对齐需求，再决定是否交给设计或前端。

实际体验暴露出明显控制权问题：

```text
用户: 我想做一个宠物洗护店单页预约页面。
系统: 生成 UX -> 前端 -> 验收的 plan-only DAG。

用户: 能不能先对齐一下需求，我要产品经理。
系统: 重新生成包含产品经理、UX、前端、验收的 plan-only DAG。

用户: 我只要单独和产品经理交流。
系统: 生成只有产品经理一个任务的 plan-only DAG。

用户: 你非要走任务吗，不能直接让产品经理出来吗？
系统: 放弃计划。

用户: 不能直接让产品经理出来吗？
系统: 才直接让产品经理回复。
```

这不是单个 Agent 回答质量问题，而是群聊协作产品模型的问题：当前系统过度偏向“计划生成器 + 自动流水线”，没有把“在群聊里直接叫某个成员出来连续沟通”作为一等能力。

---

## 2. 代码证据

本诊断基于当前代码与真实对话样本，关键证据如下。

### 2.1 `GroupChatStream` 的入口优先级会把待处理 plan 置于用户新意图之上

文件：[backend/app/services/group_chat_stream.py](../../../backend/app/services/group_chat_stream.py)

当前核心路径：

```text
如果 @Orchestrator -> OrchestratorPlanChat
否则如果无 @ 且存在 latest draft plan -> OrchestratorPlanChat follow-up
否则无 @ -> OrchestratorStewardChat 四档分流
否则普通 @ -> OrchestratorV2 Pipeline -> AgentExecutor
```

问题：

- 只要存在未终结 draft plan，后续无 `@` 消息会优先进入 `OrchestratorPlanChat` follow-up；
- 用户说“我只要和产品经理聊”“别走任务”“让产品经理出来”这类新控制意图，容易被解释成“修改上一版计划”；
- `discard_plan` 之后才会回到 steward，但这一步需要用户持续纠正系统，体验上像在和流程引擎拉扯。

### 2.2 `OrchestratorStewardChat` 的四档没有“直接会话”语义

文件：[backend/app/services/orchestrator_steward_chat.py](../../../backend/app/services/orchestrator_steward_chat.py)

当前 `StewardRouteType`：

```text
context_only | single_agent | mini_collab | draft_plan
```

问题：

- `single_agent` 代表“选择一个 Agent 轻量回答或处理”，仍然会进入 `OrchestratorV2` + `AgentExecutor` 的任务执行语义；
- 没有 `direct_dialog` / `agent_conversation` / `interview` 这类“拉某个 Agent 出来连续聊天”的路由类型；
- 产品经理、UX、架构师这类需要访谈和澄清的角色，会被系统当成一次性执行节点。

### 2.3 Plan schema 只有任务执行字段，没有互动策略

文件：[backend/app/domain/orchestrator_plan.py](../../../backend/app/domain/orchestrator_plan.py)

当前 task 字段包含：

```text
task_id / title / goal / required_skills / assigned_agent_id
depends_on / expected_outputs / acceptance_criteria
needs_approval / is_blocking
```

问题：

- `needs_approval` 只表达任务完成后的审批，不表达任务中途需要问用户；
- 没有 `interaction_policy`，无法区分“自动执行”“先访谈用户”“完成后等待确认交接”；
- 计划批准后，Scheduler 会把产品经理任务当成可运行节点，而不是启动一个可暂停的访谈状态。

### 2.4 `AgentExecutor` 只有执行模式，没有“等待用户回答”的任务生命周期

文件：[backend/app/services/agent_executor.py](../../../backend/app/services/agent_executor.py)

当前执行模式：

```text
single / serial / parallel / chain / dag
```

问题：

- 执行器面向“一次 Agent 调用完成后产出结果”；
- 没有 `awaiting_user_input` 事件或任务状态；
- 产品经理问完问题后，系统无法把该节点标记为“等待用户回答，不能交给下一节点”。

### 2.5 前端只有计划/执行面板，没有“正在和某 Agent 对齐”的会话状态

相关文件：

- [frontend/src/components/ChatWindow.tsx](../../../frontend/src/components/ChatWindow.tsx)
- [frontend/src/components/CollaborationPanel.tsx](../../../frontend/src/components/CollaborationPanel.tsx)
- [frontend/src/hooks/useSendMessage.ts](../../../frontend/src/hooks/useSendMessage.ts)

当前前端能展示：

- route banner；
- Draft Plan / CollaborationPanel；
- RuntimeControlStrip；
- MessageBubble；
- InteractivePromptCard。

问题：

- 没有“当前对话焦点：@产品经理，等待你回答”的状态条；
- 没有“继续让他问 / 需求已确认 / 交给下一位 / 停止自动调度”等控制按钮；
- Draft Plan 面板、DAG、原始 JSON 和执行过程容易压过用户的群聊心智。

### 2.6 现有测试把不理想体验固化成了正确行为

文件：[backend/test_api/test_group_chat.py](../../../backend/test_api/test_group_chat.py)

现有 `test_unmentioned_product_alignment_routes_to_product_manager` 断言：

```text
用户随口找产品经理
-> steward route_type = single_agent
-> 触发 orchestrator.route
-> 产品经理直接作为任务执行并完成
```

问题：

- 对“找产品经理对齐”这种访谈意图，测试期望是“直接执行 single_agent”；
- 新修复必须改写该类测试，使它断言进入 direct dialog / awaiting_user_input，而不是一次性任务完成。

---

## 3. 根因总结

### 3.1 产品模型根因

当前群聊的核心模型是：

```text
用户输入 -> 调度器判断 -> 计划或任务 -> Agent 执行 -> 下游交接
```

用户真实心智更接近：

```text
用户在群里说话 -> 指挥某个成员出来聊 -> 问答澄清 -> 用户确认 -> 再决定是否交给下一个成员
```

缺失的是“会话型协作”而不是“更聪明的计划生成”。

### 3.2 状态机根因

当前系统只有三类主状态：

```text
idle
draft_plan_pending
execution_running
```

缺少：

```text
direct_dialog_active
awaiting_user_input
ready_for_handoff
handoff_confirmed
```

因此系统无法表达“产品经理正在问你问题，暂不交给 UX/前端”。

### 3.3 任务模型根因

当前 task 同时承载三种不同概念：

- 访谈型节点：产品经理、UX 澄清需求；
- 规划型节点：架构师产出方案；
- 执行型节点：前端/后端写文件。

但数据结构和执行器只把它们当成“可执行任务”。这导致访谈型节点被错误地自动完成和交接。

### 3.4 体验呈现根因

当前 UI 把内部调度状态暴露得太重：

- plan id；
- phase；
- DAG；
- revised / discarded / plan_only；
- 原始 JSON；
- 执行过程。

这些对调试有价值，但主体验应该先服务用户：“谁在和我聊，等我做什么，下一步会不会自动交给别人”。

---

## 4. 问题清单

| 编号 | 严重级别 | 问题 | 用户影响 | 代码/文档位置 |
|------|----------|------|----------|---------------|
| GH-HC-01 | P0 | 缺少直接召唤 Agent 的会话模式 | 用户说“我要产品经理”仍被系统生成计划 | `OrchestratorStewardChat`、`GroupChatStream` |
| GH-HC-02 | P0 | 访谈型任务不能暂停等待用户回答 | 产品经理不会持续问答，批准后容易自动交给下一节点 | `orchestrator_plan.py`、`orchestrator_execution.py`、`AgentExecutor` |
| GH-HC-03 | P0 | 待处理 plan 劫持后续无 @ 消息 | 用户想换成直接聊天，却被解释为计划修改 | `GroupChatStream.has_latest_orchestrator_plan()` 分支 |
| GH-HC-04 | P0 | 审批粒度过粗 | 用户只能批准整个计划，不能确认“需求已对齐再交给 UX” | `ApprovalService`、Plan follow-up |
| GH-HC-05 | P1 | `single_agent` 同时承担轻量回答和任务执行 | 产品经理对齐、前端小改、测试审查被混成同一种路径 | `StewardRouteType`、`OrchestratorV2` |
| GH-HC-06 | P1 | Plan task 缺少互动策略字段 | 无法声明某节点必须先问用户、不能自动交接 | `PLAN_SCHEMA` |
| GH-HC-07 | P1 | UI 没有当前对话焦点 | 用户不知道现在是在和产品经理聊，还是在审批计划 | `ChatWindow`、`CollaborationPanel` |
| GH-HC-08 | P1 | 内部调试信息污染主体验 | DAG/JSON/phase 让用户感觉系统“自顾自” | `OrchestratorPlanPanel`、`CollaborationPanel` |
| GH-HC-09 | P1 | 输入框禁用策略没有区分“运行中”和“等用户回答” | 需要用户回答时可能被运行状态压住或缺少明确提示 | `ChatWindow`、`useSendMessage` |
| GH-HC-10 | P2 | 状态文案不精确 | “已完成”容易被理解为需求已完成，而实际只是计划生成完成 | 前端消息与面板文案 |
| GH-HC-11 | P2 | 测试覆盖了自动任务路径，没覆盖访谈路径 | 后续重构容易回归到“计划/执行优先” | `test_group_chat.py`、前端 store/component 测试 |

---

## 5. 目标体验

### 5.0 不硬编码意图判断

本模块不得在后端用中文关键词、正则或固定短语判断“用户是不是想找产品经理”“用户是不是要退出计划”“用户是不是确认交接”。后端只能做结构化协议解析与状态流转：

```text
Orchestrator/当前 Agent 输出 JSON route/action
  -> 后端校验 route/action 是否在白名单
  -> 后端按结构化字段流转状态
```

允许的后端确定性逻辑：

- 校验 `route_type` / `action` 是否合法；
- 校验 `selected_agent_id` 是否属于当前群聊；
- 校验 plan/task 依赖是否是合法 DAG；
- 根据已持久化的 `dialog_state` 决定后续无 @ 消息进入当前 Agent，而不是重新进 steward；
- 根据用户通过 UI 按钮发出的结构化 API 请求关闭、确认或交接 direct dialog。

禁止的后端逻辑：

- `if "产品经理" in content`；
- `if "确认" in content and "交给" in content`；
- `if "别走任务" in content`；
- 用硬编码 Agent 名称或角色名决定路由。

如果需要理解自然语言，必须由 Orchestrator Agent 或当前对话 Agent 输出结构化 JSON，例如：

```json
{
  "route_type": "direct_dialog",
  "selected_agent_ids": ["agent_pm"],
  "dialog_goal": "对齐宠物洗护店单页预约介绍页需求",
  "requires_user_input": true,
  "reason": "用户希望先单独和产品经理交流"
}
```

### 5.1 直接召唤 Agent

用户：

```text
我只要单独和产品经理交流。
```

系统：

```text
@产品经理 已加入当前对话。后续消息会先交给产品经理，直到你确认交接或退出。
```

产品经理：

```text
我先问几个关键问题。第一，这个页面主要发给新客户、老客户，还是朋友圈/社群引流？
```

此时：

- 不生成 plan；
- 不展示 DAG；
- 不自动交给 UX/前端；
- 会话进入 `direct_dialog_active + awaiting_user_input`。

### 5.2 访谈完成后手动交接

产品经理：

```text
我整理出一版需求说明。你确认后，我可以交给 UX 设计师，或者继续补充。
```

用户：

```text
需求确认，交给 UX。
```

系统才进入：

```text
direct_dialog_active -> handoff_confirmed -> mini_collab/draft_plan/next_agent
```

### 5.3 计划执行中的访谈节点

如果用户明确批准一份包含产品经理节点的 plan，产品经理节点也不应该一次性完成后自动交接。计划任务应支持：

```json
{
  "interaction_policy": "ask_user_until_confirmed",
  "handoff_policy": "manual_confirm",
  "blocks_downstream_until": "user_confirms"
}
```

执行到该节点时：

- 产品经理问问题；
- 任务状态变为 `awaiting_user_input` 或 `paused_for_user_input`；
- 下游 UX/前端保持 pending；
- 用户回答后仍回到同一个产品经理节点；
- 用户确认后才释放下游依赖。

---

## 6. 修改清单

### M1：扩展 steward 路由，增加直接会话类型

目标文件：

- `backend/app/services/orchestrator_steward_chat.py`
- `backend/app/services/group_chat_stream.py`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/types/index.ts`

建议改动：

- `StewardRouteType` 增加 `direct_dialog`；
- steward prompt 明确：
  - 用户说“我要和 X 聊”“只和 X 交流”“让 X 出来”“别走任务”时，优先 `direct_dialog`；
  - `direct_dialog` 不生成 plan，不进入 DAG，不触发下游 Agent；
  - `selected_agent_ids` 只能是一个主对话 Agent；
- `GroupChatStream` 对 `direct_dialog` 调用新的直接会话服务，而不是 `OrchestratorV2 Pipeline`；
- SSE 增加 `group.direct_dialog_started` 或复用 `agent.start` 但 metadata 标明 `dialogMode=direct`。
- 后端不得用用户文本硬编码判断 direct dialog；只能解析 steward 输出的 `route_type=direct_dialog`。

后端验收：

- “我只要和产品经理聊”不会出现 `orchestratorPlan`；
- 不出现 `orchestrator.route` 的任务执行语义；
- 产品经理消息 metadata 包含 `dialogMode=direct`、`awaitingUserInput=true`。

### M2：增加群聊会话焦点状态

目标文件：

- `backend/app/models/session.py` 或新增 `session_dialog_states` 表；
- `backend/app/services/session_service.py`;
- `backend/app/services/group_chat_stream.py`;
- 可能新增 `backend/app/services/group_dialog_state_service.py`。

建议模型：

```text
session_id
mode = direct_dialog | plan_followup | execution | idle
active_agent_id
active_agent_name
status = agent_responding | awaiting_user_input | ready_for_handoff | closed
source_message_id
expires_at 或 updated_at
metadata_json
```

关键规则：

- direct dialog 激活后，后续无 @ 消息默认交给 active agent，而不是 steward 或 plan follow-up；
- 用户显式 `@其他Agent` 时可临时绕过焦点；用户点击 UI 的“交给调度器”结构化按钮时关闭焦点；
- 有 pending draft plan 时，如果用户表达直接召唤 Agent，应允许覆盖 plan follow-up，并可自动 discard 或挂起旧 plan。

后端验收：

- 产品经理问完问题后，下一条“主要发给新客户”继续发给产品经理；
- 不重新进入 steward；
- 不修改上一版 draft plan。

### M3：为计划任务增加互动策略

目标文件：

- `backend/app/domain/orchestrator_plan.py`
- `backend/app/services/orchestrator_plan_chat.py`
- `backend/app/services/orchestrator_execution.py`
- `backend/app/services/run_service.py`
- `backend/app/models/run.py` 或 task metadata。

建议字段：

```json
{
  "interaction_policy": "auto_run | ask_user_once | ask_user_until_confirmed | approval_after_output",
  "handoff_policy": "auto | manual_confirm",
  "awaits_user_input": false,
  "blocks_downstream_until": "task_completed | user_confirms"
}
```

Orchestrator plan prompt 必须说明：

- 需求澄清、产品访谈、UX 访谈、架构对齐等任务默认可选择 `ask_user_until_confirmed`；
- 这类任务的目标不是“一次性写完文档”，而是先向用户提问；
- 下游任务必须等待 `user_confirms` 后释放；
- 用户回答后要回到同一任务、同一 Agent，而不是重新生成新计划。

兼容规则：

- 旧 plan 缺字段时默认 `auto_run`；
- 产品经理、UX 需求澄清类任务默认倾向 `ask_user_until_confirmed + manual_confirm`；
- `needs_approval` 保持任务完成后的审批，不替代中途用户输入。

后端验收：

- 批准包含产品经理访谈节点的计划后，只启动产品经理；
- 产品经理输出问题后任务状态不是 `completed`，而是 `awaiting_user_input`；
- 下游任务不启动；
- 用户确认“需求已确认”后才把该任务置为 completed 并释放下游。

### M4：增加用户输入等待态与恢复 API

目标文件：

- `backend/app/services/orchestrator_execution.py`
- `backend/app/api/orchestrator.py`
- `backend/app/services/group_chat_stream.py`
- `frontend/src/api/client.ts`

建议事件/API：

```text
SSE: task.awaiting_user_input
SSE: group.direct_dialog_waiting
POST /api/orchestrator/executions/{execution_id}/tasks/{task_id}/confirm
POST /api/sessions/{session_id}/group-dialog/close
```

关键规则：

- 等待用户输入不是失败，也不是审批驳回；
- 用户回答应进入同一 Agent 的上下文；
- 用户确认交接才释放下游。

### M5：前端增加“当前对话焦点”体验

目标文件：

- `frontend/src/components/ChatWindow.tsx`
- `frontend/src/components/CollaborationPanel.tsx`
- `frontend/src/components/MessageBubble.tsx`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/stores/chatStore.ts`
- 可能新增 `frontend/src/components/GroupDialogFocusBar.tsx`。

建议 UI：

```text
当前正在和 @产品经理 对齐需求
[确认并继续调度] 或 [交给调度器]
```

交互规则：

- `awaiting_user_input` 时输入框必须可用；
- header/status 显示“等待你回答 @产品经理”；
- 计划内访谈节点显示“确认并继续调度”，释放下游依赖；
- 普通 direct dialog 显示“交给调度器”，只关闭当前焦点，下一条无 @ 消息重新进入 Orchestrator；
- Draft Plan 的原始 JSON 默认折叠到调试视图；
- “已完成”文案按语义区分为“计划已生成”“等待你确认”“等待你回答”“节点已完成”。

### M6：调整 pending plan 优先级

目标文件：

- `backend/app/services/group_chat_stream.py`
- `backend/app/domain/orchestrator_plan.py`

建议规则：

- 有 pending draft plan 时，不再无条件截获所有无 @ 消息；
- 先让 Orchestrator Agent 输出结构化 `action`：
  - `approve_plan` / `revise_plan` / `discard_plan` -> plan follow-up；
  - `start_direct_dialog` -> 关闭或挂起 plan，进入 direct dialog；
  - `start_new_route` -> discard/hide old plan 后重新 steward。
- 后端只解析结构化 `action`，不得根据用户文本关键词判断上述分支。

验收：

- 用户在 draft plan 后说“我只要单独和产品经理交流”，不会生成“只有产品经理任务的新计划”；
- 系统应给出“已暂停当前计划，切换到 @产品经理 单独对齐”。

### M7：测试重写与新增

后端测试：

- 改写 `test_unmentioned_product_alignment_routes_to_product_manager`：
  - 期望 `direct_dialog`；
  - 期望产品经理进入 `awaiting_user_input`；
  - 不期望 `orchestrator.route` 任务执行；
  - 不期望 draft plan。
- 新增 `test_pending_plan_can_be_overridden_by_direct_dialog_request`。
- 新增 `test_direct_dialog_followup_goes_to_active_agent_without_steward`。
- 新增 `test_direct_dialog_close_returns_next_turn_to_steward`。
- 新增 `test_interview_task_blocks_downstream_until_user_confirms`。
- 新增 `test_user_confirm_handoff_releases_next_task`。
- 新增 `test_explicit_mention_product_manager_can_enter_direct_dialog`。

前端测试：

- `GroupDialogFocusBar` 展示当前 Agent、等待状态和操作按钮；
- `awaiting_user_input` 时 ChatInput 不被 active run 禁用；
- Draft Plan 原始 JSON 默认折叠；
- 点击“需求已确认”会发送结构化 handoff/resume 请求或等价消息。

---

## 7. 修改优先级

| 顺序 | 切片 | 价值 | 风险 |
|------|------|------|------|
| 1 | M1 + M2：direct dialog + 会话焦点 | 立即修复“不能直接叫产品经理出来” | 中等，需要新状态但不碰 DAG 执行深处 |
| 2 | M6：pending plan 优先级调整 | 修复 plan 劫持用户新意图 | 中等，需保护 approve/revise/discard 现有路径 |
| 3 | M5：前端焦点条与文案 | 显著改善用户控制感 | 低到中 |
| 4 | M3 + M4：计划任务互动策略 | 修复批准计划后访谈节点自动交接 | 高，涉及 execution 状态机 |
| 5 | M7：全量回归测试 | 锁住体验，不再回退 | 低 |

建议先做 1-3，人工验收通过后再做 4。否则一次性改 Scheduler、UI、路由，回归面过大。

---

## 8. 人工验收脚本

### 用例 A：直接叫产品经理出来

输入：

```text
我经营一家小型宠物洗护店，想做一个可以发给客户的单页预约介绍页面。先不要做页面，我只想单独和产品经理对齐需求。
```

期望：

- Orchestrator 不生成 DAG；
- 产品经理直接出现；
- 产品经理问 3-6 个问题；
- 界面显示“正在和 @产品经理 对齐需求 / 等待你回答”；
- 输入框可继续输入；
- 不自动交给 UX/前端。

### 用例 B：连续追问

输入：

```text
主要发给新客户和朋友圈引流，服务有基础洗护、精致洗护、猫咪洗护和剪指甲。
```

期望：

- 不进入调度器；
- 不生成新计划；
- 产品经理继续追问价格、预约规则、门店信息或表单字段；
- 消息归属仍是 @产品经理。

### 用例 C：确认后再交接

输入：

```text
这些需求确认了，交给 UX 设计师出页面结构。
```

期望：

- 产品经理 direct dialog 关闭或进入 ready_for_handoff；
- UX 才开始工作；
- 如果需要多人协作，先生成小型计划并等待确认；
- 不出现产品经理自动把未确认需求交给下一轮的情况。

### 用例 D：pending plan 覆盖

步骤：

1. 先让系统生成一个完整 plan；
2. 不批准；
3. 输入：

```text
这版先别执行，我只要和产品经理聊。
```

期望：

- 旧 plan 被挂起/放弃/折叠；
- 不生成“只有产品经理一个任务的新 plan”；
- 直接进入 @产品经理 对话。

### 用例 E：计划中的访谈节点

步骤：

1. 明确要求“先产品经理问我，确认后再 UX，再前端”；
2. 批准计划。

期望：

- 只启动产品经理节点；
- 产品经理问问题后任务进入等待用户；
- UX 和前端不启动；
- 用户确认后才释放 UX。

---

## 9. 自动化验证命令

后续每个切片修复后至少运行：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest test_api\test_group_chat.py test_api\test_orchestrator_execution.py -q
```

```powershell
cd frontend
npx tsc --noEmit
npx vitest run
```

涉及执行状态机的切片再补：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest test_api test_unit -q
```

真实服务验收仍按项目规则执行：清理旧进程、启动当前后端/前端、验证根路径/OpenAPI/前端根路径/API 代理，再跑上述人工用例。

---

## 10. 非目标

- 不恢复旧的“无 @ 自动全量执行”；
- 不把所有群聊消息都交给调度器生成计划；
- 不在第一轮实现复杂可视化 DAG 编辑器；
- 不改变 AgentHub 的 CLI Wrapper 架构；
- 不要求访谈 Agent 永远不写文件，但默认访谈模式不得写 workspace，除非用户明确要求进入产出阶段。
