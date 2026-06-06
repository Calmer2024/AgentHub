# 11: 群聊调度器管家路由

**状态**: Draft
**创建日期**: 2026-06-07
**关联**: [01-architecture.md](01-architecture.md)、[02-agent-selection.md](02-agent-selection.md)、[10-real-agent-execution](10-real-agent-execution/)、[Phase 7 Context Pack](../../phase7/05-context-pack-and-cache-strategy.md)

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
| `@调度器 ...` | Plan-first 调度器 | 生成 draft plan 或处理计划批准/修改 |
| `@具体Agent ...` | 指定 Agent | 让被点名 Agent 直接回复/执行，必要时作为补充轮 |
| 不 `@` | 调度器管家 | 先做轻量意图分流，再决定是否记录、单 Agent、多人小协作或生成计划 |

核心原则：

```text
不 @ = 交给调度器管家判断
不 @ ≠ 直接自动拉 Agent 执行
```

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
- 生成短任务包；
- 可并行或短串行；
- 不进入完整 DAG 审批；
- 可生成一条简短中枢总结。

约束：

- 参与 Agent 数量默认不超过 3；
- 默认不允许跨阶段长流程；
- 如果需要设计、实现、测试、文档完整链路，升级到档位 D。

验收：

- 前端显示 2-3 个 Agent 气泡或短协作面板；
- 不出现完整 draft plan 审批；
- 任务完成后有简短总结；
- Context Pack 中只注入必要摘要和文件引用，不注入完整群聊 transcript。

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

## 4. 调度器管家输出契约

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

## 5. 默认安全策略

当分类不确定时，优先选择更保守档位：

```text
不确定是否需要执行 -> context_only 或询问用户
不确定单 Agent 还是多人 -> single_agent
不确定小协作还是长流程 -> draft_plan
涉及文件大改 / 多阶段 / 高成本 -> draft_plan
```

调度器管家不得在不 @ 的情况下直接启动大规模 DAG。

---

## 6. 与 Context Pack 的关系

调度器管家分类结果会影响 Context Pack 构建：

| route_type | Context Pack 策略 |
|------------|-------------------|
| `context_only` | 更新 Project Memory，不构建 Agent 执行包 |
| `single_agent` | 构建单 Agent 小任务包，只带最新用户消息、相关记忆和少量引用 |
| `mini_collab` | 为每个 Agent 构建独立小任务包，上游默认摘要化 |
| `draft_plan` | 构建计划生成包，重点包含目标、约束、候选 Agent、验收要求 |

这能避免“不 @”消息把完整群聊 transcript 直接灌给多个 Agent。

---

## 7. 实现切片

### Step 1：后端分类器

- 新增 `GroupStewardRouter` 或等价服务；
- 输入：content、mentions、member_agents、session/project memory 摘要；
- 输出：四档 route decision；
- 先用规则 + Agent 技能标签实现，不必立即接 LLM。

### Step 2：GroupChatStream 接入

- `mentions` 为空时先走 steward router；
- `context_only` 直接返回短确认；
- `single_agent` / `mini_collab` 构造受限 `AgentCall`；
- `draft_plan` 转交 `OrchestratorPlanChat` 生成计划。

### Step 3：前端展示

- 聊天流中显示轻量状态：“调度器管家已记录 / 已分派给 @后端专家 / 建议生成计划”；
- 调试信息先放 trace 或 execution debug，不污染主 UI。

### Step 4：测试

- 覆盖四档输入样例；
- 验证复杂任务不会直接启动真实 Agent；
- 验证 context_only 不产生普通 Agent 气泡；
- 验证单 Agent 和 mini_collab 可停止、可刷新恢复。

---

## 8. 非目标

- 不要求调度器管家每次都调用真实 LLM；
- 不要求不 @ 时一定生成 draft plan；
- 不要求恢复旧的“无 @ 自动全量路由执行”行为；
- 不解决全部 Context Pack 实现，只定义路由入口语义。

---

## 9. 当前差距

当前代码仍是：

```text
不 @
  -> OrchestratorV2 自动 AgentSelector
  -> ExecutionPlanner
  -> AgentExecutor 可能直接启动真实 Agent
```

目标代码应变为：

```text
不 @
  -> 调度器管家 route decision
  -> context_only / single_agent / mini_collab / draft_plan
  -> 按档位执行或等待用户确认
```

该差距应作为下一阶段优先修复项。
