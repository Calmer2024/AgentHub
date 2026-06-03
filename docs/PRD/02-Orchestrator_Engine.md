# 需求规格说明书 (PRD)：02 - 核心引擎与 DAG 调度逻辑 (Orchestrator Engine)

## 1. 文档定位
本文档面向**核心业务逻辑研发**、**AI 算法/Prompt 工程师**。
如果说底层 CLI Agent 是 AgentHub 的“手脚”，那么 Orchestrator（协调器）就是平台唯一的“大脑”。本文档详细规定了 Orchestrator 如何处理宏大需求，如何避免大模型在长上下文中崩溃，以及如何实现类似 GitHub Actions 的工业级流水线调度。

---

## 2. 核心挑战：大模型物理上限的突破 (Breaking the LLM Limits)

### 2.1 一万行代码的诅咒
无论底层挂载的是多么先进的工具（哪怕是真正的 Claude Code），物理学规律决定了一次单向推断（Inference）存在极其严格的上下文窗口（Context Window）限制和输出 token 上限（Max Output Tokens，通常不超过 8192）。
*   **错误做法**：将“写一个淘宝网”直接作为 Prompt 喂给单个 Agent，期待它吐出所有的前后端代码。这必定导致代码截断、逻辑错乱。
*   **AgentHub 破局之道**：**分而治之 (Divide and Conquer)**。引入绝对中心化的 Orchestrator。大需求进来，Orchestrator 第一步永远不是写代码，而是“写排期表”。

---

## 3. Work Breakdown Structure (WBS) 任务拆解器

### 3.1 意图拦截与宏观拆解
当用户在群聊中输入大段需求后，请求首先打到 Orchestrator。
Orchestrator 本身是一个无状态的纯 LLM API 调用者（建议使用最聪明的模型如 GPT-4o 或 Claude 3.5 Sonnet）。

*   **System Prompt 设定**：
    > “你是一个硅谷顶级的软件架构师和敏捷教练（Scrum Master）。你的任务不是写代码，而是将用户庞大、模糊的业务需求，拆解为一系列严密的、细粒度的开发任务。每个任务必须能够由单个工程师在短时间内独立完成。你需要明确指出每个任务需要哪种特定技能的 Agent（如：UI设计师、前端、DBA、后端），以及这些任务之间的绝对先后依赖关系。”

### 3.2 结构化输出契约 (JSON DAG)
Orchestrator 解析需求后，必须向后端返回符合强校验 Schema 的 JSON 数组。这个数组在数学上构成了一个 **有向无环图 (Directed Acyclic Graph, DAG)**。

**样例数据结构**：
```json
{
  "tasks": [
    {
      "task_id": "T1",
      "name": "需求澄清与 PRD 编写",
      "agent_role": "产品经理",
      "dependencies": [],
      "requires_human_approval": true
    },
    {
      "task_id": "T2",
      "name": "数据库表结构设计 (SQL)",
      "agent_role": "架构师",
      "dependencies": ["T1"],
      "requires_human_approval": true
    },
    {
      "task_id": "T3",
      "name": "鉴权模块后端开发 (FastAPI)",
      "agent_role": "后端专家",
      "dependencies": ["T2"],
      "requires_human_approval": false
    },
    {
      "task_id": "T4",
      "name": "登录注册页前端开发 (React)",
      "agent_role": "前端专家",
      "dependencies": ["T1", "T2"],
      "requires_human_approval": false
    },
    {
      "task_id": "T5",
      "name": "前后端联调与单元测试",
      "agent_role": "测试专家",
      "dependencies": ["T3", "T4"],
      "requires_human_approval": false
    }
  ]
}
```

---

## 4. 状态机引擎与调度执行 (State Machine Engine)

拆解出上述 DAG 后，AgentHub 的后端即化身为一个**状态机流转引擎**（类似 Apache Airflow 的简化版）。

### 4.1 任务节点状态枚举 (Task States)
在数据库 `tasks` 表中，每个子任务必须且只能处于以下 5 种状态之一：
1.  **`PENDING` (等待中)**：任务尚未开始。要么是因为前置依赖（Dependencies）未完成，要么是正在排队。
2.  **`RUNNING` (执行中)**：Orchestrator 已经启动了对应的底层 CLI Agent 进程，正在监听其输出。
3.  **`PAUSED` (挂起等待审批)**：CLI Agent 工作完成，但由于配置了 `requires_human_approval = true`，流水线暂停，等待人类用户的指令。
4.  **`COMPLETED` (已完成)**：任务彻底成功，将释放下游任务的阻塞。
5.  **`FAILED` (失败)**：CLI Agent 崩溃，或被用户主动中止。流水线在此断裂。

### 4.2 调度循环算法 (The Scheduler Loop)
后端需要一个独立于 HTTP 响应的后台轮询机制（或事件驱动机制）：
1.  **扫描 PENDING**：检查所有状态为 `PENDING` 的任务。
2.  **依赖解析**：对于每一个 `PENDING` 任务，检查其 `dependencies` 列表中指向的所有任务是否都达到了 `COMPLETED` 状态。
3.  **并发启动**：一旦某个任务的依赖全部清空，立即将其置为 `RUNNING`，并通过 `CLI Adapter` 唤醒对应的 Agent 进程开始干活。（注意：`T3` 和 `T4` 在上述 JSON 中由于互不依赖，应当被**并发拉起**）。

---

## 5. 人机握手：深度集成 Human-in-the-loop

**这是区别于“玩具级”Agent 的核心特征。**

### 5.1 断点审批机制 (Approval Checkpoint)
在真实工程中，一旦架构设计（T2）做错了，后面的代码全白写。因此：
*   当 T2 (架构师) 完成输出（生成了一份 Markdown 的架构图）后，引擎检查到 `requires_human_approval: true`。
*   任务状态由 `RUNNING` 转为 `PAUSED`。
*   **前端交互**：聊天流中自动追加一条特殊消息卡片，带有显眼的【确认批准并进入下一阶段】和【驳回重写】按钮。
*   用户可以在输入框继续和架构师聊天（“表结构少了一个 create_time 字段，加上”），架构师会在 T2 的上下文中继续修改。
*   直到用户点击【确认批准】，引擎才会把 T2 标记为 `COMPLETED`，进而触发后续 T3 和 T4 的执行。

### 5.2 灾难恢复与断点续传 (Resumability)
如果 T4 在执行过程中，由于本地 Node.js 环境缺失导致底层 Agent 崩溃退出，状态变更为 `FAILED`。
*   系统绝对不能把整个大项目判死刑。
*   前端展示“节点故障”卡片。用户可以在宿主机安装好 Node.js 后，点击卡片上的【重试】。引擎只需将 T4 重新拨回 `RUNNING` 即可，T1、T2、T3 的历史资产完好无损。

---

## 6. 上下文定向注入 (Directed Context Injection)

大锅饭模式（把所有人的聊天记录全部塞给下一个 Agent）会极度浪费 Token 算力并引发幻觉。
Orchestrator 在拉起下游任务（如 T5 测试）时，必须执行**定向投影（Projection）**：
*   **仅传递结论，不传递废话**：T5 启动时，Orchestrator 不会给它看 T1-T4 之间数万字的废话沟通记录。它只会把 T3 和 T4 最终生成的代码产物（Artifacts），加上原始的用户需求，精确地注入到 T5 的系统上下文（System Prompt）中。
*   这种克制的上下文管理，是大规模工程能持续滚动的唯一解法。

---

## 7. Orchestrator 与 Artifact 闭环

Orchestrator 不只负责“谁来回复”，还必须负责让复杂任务的关键阶段产生可审阅、可编辑、可追踪的 Artifact。否则用户只能看到一串 Agent 文字，无法完成启动文档要求的“产物内联、预览和操作”。

### 7.1 Task 输出契约

每个拆解任务都应带有输出预期：

```json
{
  "task_id": "T4",
  "name": "登录注册页前端开发",
  "agent_role": "前端专家",
  "dependencies": ["T1", "T2"],
  "requires_human_approval": false,
  "expected_outputs": [
    {
      "type": "artifact",
      "artifact_type": "web_preview",
      "title_hint": "LoginPage"
    }
  ]
}
```

`expected_outputs` 用于：
- 指导 Agent 输出结构化结果，而不是只输出长 Markdown。
- 帮助 Adapter/ArtifactService 判断哪些输出应变成 Artifact。
- 帮助前端在任务完成时展示 Artifact Card 或审批卡片。

### 7.2 任务完成规则

任务从 `RUNNING` 进入 `COMPLETED` 前必须满足：

| 任务类型 | 完成条件 |
|---|---|
| 纯文本/调研任务 | 写入最终 Agent 消息或中枢总结 |
| Artifact 任务 | 至少创建一个关联 `task_id` 的 Artifact，或显式输出“无产物原因” |
| 审批任务 | 创建可审阅 Artifact 或摘要，并进入 `PAUSED` 等待用户确认 |

### 7.3 审批与 Artifact 绑定

当 `requires_human_approval=true`：
- 前端 Approval Card 必须能打开对应 Artifact 或任务摘要。
- 用户驳回时，后续指令默认引用该任务的最新 Artifact。
- 用户确认时，Orchestrator 将该 Artifact 版本作为下游任务的定向上下文。

### 7.4 编辑回流

用户在 Artifact Drawer 中发起局部修改后，Orchestrator 应把新版本视为该任务的最新产出。下游任务使用最新版 Artifact，而不是使用最初生成版本。
