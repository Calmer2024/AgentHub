# 11: 群聊调度器管家路由

**状态**: 已交付基线 / 已通过人工验收
**创建日期**: 2026-06-07
**更新日期**: 2026-06-08
**关联**: [01-architecture.md](01-architecture.md)、[02-agent-selection.md](02-agent-selection.md)、[10-real-agent-execution](10-real-agent-execution/)、[Phase 7 Context Pack](../../phase7/05-context-pack-and-cache-strategy.md)、[Phase 7 CLI Session Runtime](../../phase7/06-cli-session-process-runtime.md)

---

## 1. 背景

当前群聊中用户不 `@Agent`、也不 `@调度器` 直接发送消息时，会进入旧的 `OrchestratorV2` 自动路由链路。该链路会基于意图和成员 Agent 标签选择一个或多个 Agent，并可能直接启动真实 CLI Agent 执行。

这个行为能跑，但用户心智不稳定：

- 用户可能只是补充背景，系统却启动真实 Agent；
- 用户没有显式选择“谁来做”或“是否开始执行”；
- 简单问题、轻量讨论、复杂长流程都混在同一个自动路由入口；
- 多 Agent 真实执行可能消耗大量 token、写文件、产生长气泡；
- 后续要做 Context Pack 与缓存优化时，必须先明确“不 @”消息的语义。

因此需要把“不 @”从“直接自动执行”改为“调度器管家先做轻量意图分流”。

---

## 2. 目标行为

群聊输入分三类：

| 用户输入 | 入口 | 目标行为 |
|---------|------|----------|
| `@调度器 ...` | Plan-first 调度器 | 生成 draft plan，或处理上一版计划的批准、修改、放弃 |
| `@具体Agent ...` | 指定 Agent | 让被点名 Agent 直接回复/执行；多个普通 Agent 按 @ 顺序串行，并把前序产出注入后序 Agent |
| 同时 `@调度器` 和其它 Agent | Plan-first 调度器 | 调度器优先接管，其它被 @ Agent 只作为候选、顺序或约束输入，不直接启动 |
| 不 `@` | 调度器管家 | 先做轻量意图分流，再决定是否记录、单 Agent、多人小协作或生成计划 |

核心原则：

```text
不 @ = 交给调度器管家判断
不 @ ≠ 直接自动拉 Agent 执行
```

多 @ 的责任边界：

- 后端以请求体中的 `mentionIds` 作为显式 @ 的唯一权威来源；正文里的裸 `@名字` 只作为普通文本，不能用于兜底识别调度器或普通 Agent；
- 前端必须在 `@` 输入时展示可选 Agent 列表，并在用户选择后提交结构化 `mentionIds`；如果群成员仍在加载，要给出可见 loading/空状态，不能让用户误以为 @ 功能失效；
- 多个普通 Agent 被 @ 时，系统按用户 @ 顺序串行执行，后一个 Agent 能看到前一个 Agent 的完整产出摘要；
- 只要 @ 列表中包含 Orchestrator 调度器，本轮就进入 Plan-first，不再把调度器当成普通执行 Agent；
- 调度器生成的 plan 必须声明每个任务的输入、输出、依赖、验收标准和责任边界，避免上游 Agent 代做下游 Agent 的工作。

---

## 3. 四档分流

### 3.1 档位 A：只记录上下文

适用输入：

```text
这个项目所有文档都用中文。
先别急着写代码。
补充一下，数据库先用 SQLite。
以后前端尽量保持简洁一点。
```

行为：

- 持久化用户消息；
- 更新 Project Memory / session memory；
- 不启动普通 Agent；
- 不创建 DAG execution；
- 不写 workspace 文件；
- 调度器可返回一条极短确认，例如“已记录到群聊上下文”。

验收：

- 不产生普通 Agent 气泡；
- 不产生 run/task 执行项，或 run 以 `context_only` / `completed` 轻量状态结束；
- 后续任务的 Context Pack 能看到该约束。

### 3.2 档位 B：单 Agent 快速响应

适用输入：

```text
后端看看这个 API 怎么设计？
前端帮我看下这个页面布局。
测试专家看看这里怎么验收。
```

行为：

- 调度器选择 1 个最合适的 Agent；
- 创建轻量 task；
- 允许 Agent 回复或小范围执行；
- 不生成完整 draft plan；
- 前端显示 1 个 Agent 气泡和运行控制条。

约束：

- 默认不允许大规模文件修改；
- 如果意图涉及多文件修改或长流程，升级到档位 D；
- Agent 输出应短，优先给建议或小补丁。

验收：

- route 结果只有 1 个 Agent；
- 不出现 draft plan 面板；
- 用户可停止本次运行；
- 刷新后消息、trace、产物条可恢复。

### 3.3 档位 C：多 Agent 小协作

适用输入：

```text
前后端一起看看这个接口怎么接。
产品和前端讨论一下这个表单怎么设计。
后端和测试看看这个 bug。
```

行为：

- 调度器选择 2-3 个 Agent；
- 不直接启动这些 Agent；
- 转交 Plan-first 调度器生成一份小型 draft plan；
- draft plan 复用完整 DAG 契约，必须声明每个节点的输入、输出、依赖、验收标准和责任边界；
- 用户确认后才由 Scheduler 按 DAG 执行。

约束：

- 参与 Agent 数量默认不超过 3；
- 计划任务数默认控制在 2-3 个；
- 前序 Agent 只交付本节点产物与交接说明，不代做下游 Agent 的职责；
- 如果需要设计、实现、测试、文档完整链路，升级到档位 D。

验收：

- 用户批准前不出现普通 Agent 气泡；
- 出现 draft plan 面板，且候选执行 Agent 优先来自管家选择的 2-3 个 Agent；
- draft plan 中每个任务都带 `expected_outputs`、`acceptance_criteria` 和 `depends_on`；
- 用户批准后才创建 execution，并可停止、刷新恢复。

### 3.4 档位 D：复杂任务生成计划

适用输入：

```text
帮我做一个家庭资产管理系统，前后端都要能跑。
把这个项目完整重构一下。
实现一套报销系统，包括数据库、API、前端和测试。
```

触发条件：

- 多阶段工作；
- 涉及多个 Agent；
- 涉及多文件修改；
- 预计运行时间长或 token 成本高；
- 需要用户确认范围、产物、验收标准；
- 具有破坏性或高风险操作。

行为：

- 调度器生成 draft plan；
- 展示计划面板；
- 等待用户批准；
- 批准后才创建 execution；
- execution 按 DAG/Scheduler 推进。

验收：

- 不直接启动普通 Agent；
- 用户批准前所有任务为 draft/pending；
- 用户说“执行/可以/批准”后才创建 execution；
- execution 可停止，状态可刷新恢复。

---

## 4. Plan-first 后续状态机

只要会话存在“最新且未终结”的 draft plan，后续无 `@` 消息不再进入四档管家分流，而是直接交给 Orchestrator Agent 处理上一版计划的跟进意图。调度器必须输出结构化动作或新计划，后端不得用用户文本硬编码判断。

```text
idle
  -> draft_pending        生成 draft plan

draft_pending
  -> approved            Orchestrator 输出 action=approve_plan，后端创建 execution
  -> revised             Orchestrator 输出新 draft plan，旧 plan 标记 revised，新 plan 进入 draft_pending
  -> discarded           Orchestrator 输出 action=discard_plan，旧 plan 关闭

approved / revised / discarded
  -> idle                不再拦截后续无 @ 消息；下一条无 @ 重新进入管家四档分流
```

状态含义：

| 状态 | 含义 | 后续入口 |
|------|------|----------|
| `draft_pending` | 最新计划正在等待用户批准、修改或放弃 | 继续交给 Plan-first follow-up |
| `approved` | 用户已批准，Scheduler 已按 DAG 执行或正在执行 | 退出 plan follow-up |
| `revised` | 旧计划已被新计划取代 | 新计划成为唯一待处理计划 |
| `discarded` | 用户放弃、取消或开启无关新话题，旧计划关闭 | 退出 plan follow-up |

### 4.1 follow-up 输出契约

批准计划：

```json
{
  "action": "approve_plan",
  "target_plan_id": "plan_xxx",
  "reason": "为什么判断用户是在批准执行"
}
```

放弃计划：

```json
{
  "action": "discard_plan",
  "target_plan_id": "plan_xxx",
  "reason": "为什么判断用户是在放弃这版计划"
}
```

修改计划：直接输出新的 draft plan JSON，结构仍符合 plan-only DAG 契约。后端会把旧 plan 标记为 `revised`，把新 plan 作为唯一待处理计划。

---

## 5. 调度器管家输出契约

建议后端内部先引入一个轻量分类结果：

```json
{
  "route_type": "context_only | single_agent | mini_collab | draft_plan",
  "confidence": 0.0,
  "reason": "为什么选择该档位",
  "selected_agents": ["agent_id"],
  "task_brief": "短任务描述",
  "requires_approval": false,
  "risk_level": "low | medium | high"
}
```

前端不一定直接展示完整 JSON，但调试面板应能看到该结果。

---

## 6. 默认安全策略

当分类不确定时，优先选择更保守档位：

```text
不确定是否需要执行 -> context_only 或询问用户
不确定单 Agent 还是多人 -> single_agent
不确定小协作还是长流程 -> draft_plan
涉及文件大改 / 多阶段 / 高成本 -> draft_plan
```

调度器管家不得在不 @ 的情况下直接启动大规模 DAG。

---

## 7. 与 Context Pack 的关系

调度器管家分类结果会影响 Context Pack 构建：

| route_type | Context Pack 策略 |
|------------|-------------------|
| `context_only` | 更新 Project Memory，不构建 Agent 执行包 |
| `single_agent` | 构建单 Agent 小任务包，只带最新用户消息、相关记忆和少量引用 |
| `mini_collab` | 构建小型 draft plan 生成包，候选 Agent 限定为管家选中的 2-3 个角色 |
| `draft_plan` | 构建计划生成包，重点包含目标、约束、候选 Agent、验收要求 |

这能避免“不 @”消息把完整群聊 transcript 直接灌给多个 Agent。

---

## 8. 实现切片

### Step 1：可见调度器管家

- 新增 `OrchestratorStewardChat`；
- 输入：content、mentions、member_agents、session/project memory 摘要；
- 输出：四档 route decision；
- 由真实 Orchestrator Agent 输出结构化 JSON，后端只解析 `route_type`、候选 Agent、任务摘要和风险信息，不用用户文本硬编码判断。

### Step 2：GroupChatStream 接入

- `mentions` 为空时先走 steward router；
- `context_only` 直接返回短确认；
- `single_agent` 构造受限 `AgentCall`；
- `mini_collab` 转交 `OrchestratorPlanChat` 生成小型 draft plan；
- `draft_plan` 转交 `OrchestratorPlanChat` 生成计划。

### Step 3：前端展示

- 聊天流中显示轻量状态：“调度器管家已记录 / 已分派给 @后端专家 / 建议生成计划”；
- 调试信息先放 trace 或 execution debug，不污染主 UI。

### Step 4：测试

- 覆盖四档输入样例；
- 验证复杂任务不会直接启动真实 Agent；
- 验证 context_only 不产生普通 Agent 气泡；
- 验证 single_agent 可停止、可刷新恢复；
- 验证 mini_collab 只生成 draft plan，用户批准前不启动普通 Agent。
- 验证 draft plan 后续 approve / revise / discard 都由 Orchestrator Agent 结构化输出驱动。
- 验证 discarded 后下一条无 @ 消息重新进入管家四档分流。

### Step 5：群聊 Agent 执行链路同步

路由与 Plan-first 只决定“谁来做、是否需要计划/审批”。一旦进入普通 Agent 执行，群聊必须复用与单聊一致的 CLI runtime、EngineSession、运行控制和 Artifact Bridge 能力，但作用域不同：

```text
单聊 runtime scope = private session + agent
群聊 runtime scope = group session + agent
```

当前实现要求：

- `CliAgentExecutor` 接收真实 `AsyncSession`，通过 `EngineSessionService` 按 `session_id + agent_config_id` 解析或创建 EngineSession；
- 支持常驻协议的 CLI 在群聊内使用稳定 `runtime_key = session_id:agent:agent_id`，同一群聊同一 Agent 多轮复用，不复用用户私聊进程；
- 每个 Agent 调用前创建 workspace snapshot，并把 `workspaceSnapshotId`、`workspacePath`、`engineRuntime`、`engineSession`、`processId` 合并进 Agent 事件 metadata；
- `GroupChatFinalizer` 持久化每个 Agent 子消息后，用该消息的 snapshot 调用 Artifact Bridge；
- Artifact 绑定对应 Agent messageId，Agent 身份通过 `message.sourceId` 追溯，不挂到 Orchestrator 总结消息。

验收：

- 同一群聊同一 Agent 连续两轮，第二轮 `engineSession.mode=resume`，runtime metadata 标记复用语义；
- 两个 Agent 在同一群聊中分别写入 workspace 文件时，产物分别挂到各自 Agent 消息；
- `/api/agents/runtime/processes?sessionId=...` 能按真实群聊 session 聚合查看/清理活跃 runtime。

---

## 9. 非目标

- 不要求调度器管家每次都调用真实 LLM；
- 不要求不 @ 时一定生成 draft plan；
- 不要求恢复旧的“无 @ 自动全量路由执行”行为；
- 不解决全部 Context Pack 实现，只定义路由入口语义。

---

## 10. 当前已交付基线

当前代码已变为：

```text
不 @
  -> OrchestratorStewardChat 可见调度器回合
  -> 真实 Orchestrator Agent 输出 route decision
  -> context_only / single_agent / mini_collab / draft_plan
  -> 按档位记录、单 Agent 执行，或进入 Plan-first 等待确认
```

Plan-first 跟进已支持：

```text
draft_pending
  -> approve_plan   创建 execution，Scheduler 按 DAG 异步推进
  -> discard_plan   关闭旧 plan，下一条无 @ 重新进入管家分流
  -> 新 draft plan   旧 plan 标记 revised，新 plan 成为唯一待处理计划
```

本轮人工验收认可的边界：

- `context_only` 会产生 Orchestrator 调度器可见回复，不再出现“没人理我”的体验；
- `mini_collab` 不直接启动多个 Agent，而是复用 Plan-first 小型 DAG；
- 有待处理 draft plan 时，后续无 @ 的“允许执行/修改/取消/换话题”都交给 Orchestrator Agent 输出结构化动作；
- 多个普通 @ 仍按 @ 顺序串行；多个 @ 中包含调度器时，调度器优先接管并生成/跟进 plan。
- 显式 @ 已收敛为结构化 `mentionIds` 协议；手输正文里的 `@Orchestrator` 但未携带 `mentionIds` 时，按无 @ 管家分流处理。
- 普通 Agent 执行已同步单聊 runtime/Artifact 链路：群聊内每个 Agent 拥有专属 EngineSession/runtime 和 workspace snapshot，产物绑定具体 Agent 子消息。
