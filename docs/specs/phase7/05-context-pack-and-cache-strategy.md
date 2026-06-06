# 05: Context Pack 与缓存策略

**状态**: Draft
**创建日期**: 2026-06-07
**关联**: [Phase 6 CLI Adapter](../phase6/01-cli-adapter.md)、[Phase 7 Runtime Control](01-runtime-task-control.md)、[ADR-0007 Orchestrator Architecture](../../adr/0007-orchestrator-architecture.md)、[ADR-0011 Agent Engine Skill Model](../../adr/0011-agent-engine-skill-model.md)

---

## 1. 问题摘要

当前 AgentHub 的真实 CLI Agent 执行方式是“每轮启动一个 CLI 进程，手动拼接上下文后喂给它”。这让单聊和群聊都能跑通，但它没有充分利用 Claude Code / Codex 等底层 Engine 可能具备的会话续接、上下文缓存或长期记忆能力。

当前单聊路径可概括为：

```text
用户发送消息
  -> AgentHub 持久化用户消息
  -> 从数据库取 session history
  -> ContextManager 裁剪并组装 messages
  -> CliAgentService 渲染 transcript prompt
  -> 启动新的 claude/codex/opencode 进程
  -> CLI 输出流式回传
  -> AgentHub 持久化 assistant 消息
  -> CLI 进程结束
```

当前群聊路径可概括为：

```text
用户发送群聊消息
  -> AgentHub 持久化用户消息
  -> 取群聊 history
  -> OrchestratorV2 组装上下文并选择 Agent / 规划执行模式
  -> 每个被选 Agent 启动独立 CLI 进程
  -> DAG/chain 后续任务通过 SharedContext 注入上游输出
  -> Agent 输出持久化并进入后续上下文
  -> CLI 进程结束
```

这意味着：AgentHub 当前主要依赖“自己拼 prompt”来模拟连续对话，而不是显式复用底层 CLI Engine 的会话状态。

---

## 2. 当前实现事实

### 2.1 单聊不是持久 CLI 会话

单聊由 `SingleCliChatStream` 处理。它每轮调用 `CliAgentService.stream()`，后者根据 Agent 配置选择 CLI Adapter，并把组装后的 messages 渲染成纯文本 transcript。

当前 Claude Code 默认参数是 `claude -p --output-format stream-json ...` 形态，没有显式使用 `--continue`、`--resume` 或 AgentHub 自己维护的 Engine session id。

因此单聊的“连续性”来自：

- AgentHub 数据库里的历史消息；
- `ContextManager` 对历史消息的裁剪和拼接；
- workspace 文件系统中的持久文件；
- Agent Profile / Skill / system prompt 每轮重新注入。

不应假设它来自：

- 同一个 Claude Code 进程长期存活；
- Claude Code 自己的上一轮对话状态被 AgentHub 显式恢复；
- 底层模型缓存稳定命中完整历史。

### 2.2 群聊更容易上下文膨胀

群聊每轮可能产生多个 Agent 输出。当前 `OrchestratorV2` 把历史消息交给 `ContextManager` 组装，`ExecutionPlanner` 为每个 `AgentCall` 复制一份 `input_messages`。

DAG 模式中，`SharedContext` 会在每个任务完成后把输出追加到共享消息流；有依赖的下游任务还会额外收到依赖任务的完整产出片段。

这保证了下游 Agent 能看到上游工作，但也带来几个问题：

- 一轮用户请求可能生成多条长 Agent 消息，下一轮上下文增长速度高于单聊；
- 上游输出被直接注入 prompt，可能重复进入多个下游 Agent；
- 并行 Agent 的 prompt 前缀因为任务、上游输出和裁剪差异而分叉；
- 当 token 预算触发裁剪时，prompt 前缀可能变化，进一步降低缓存稳定性。

### 2.3 当前缓存命中不可控

Provider / Engine 层面的 prompt cache 命中通常依赖“前缀稳定”。当前 AgentHub 的稳定部分主要是：

```text
AgentHub Agent Profile
Primary Skill / Auxiliary Skills
Agent system prompt
Context Policy
```

高频变化部分包括：

```text
历史 transcript
最新用户消息
上游 Agent 输出
DAG task brief
artifact scan 摘要
错误日志和 trace
被裁剪后的消息边界
```

所以可以合理判断：当前除了 Agent Profile / Skill 这一小段外，缓存命中不应被乐观估计。群聊场景因为多 Agent、多任务、多上游输出，命中会更差。

---

## 3. 风险清单

| 风险 | 影响 | 当前严重度 |
|------|------|------------|
| 上下文线性或超线性增长 | token 成本升高、延迟变长、模型注意力被稀释 | 高 |
| 缓存命中不可预测 | 真实运行成本和速度不可控，压测结果波动大 | 高 |
| 单聊“连续对话”是假连续 | 用户以为 Agent 记得上下文，实际依赖拼接和裁剪 | 中高 |
| 群聊协作靠长文本传递 | 下游 Agent 容易漏读、误读、重复读上游输出 | 高 |
| prompt 前缀不稳定 | Engine 级缓存难以命中，尤其 DAG/并行场景 | 高 |
| Agent 输出直接进入上下文 | 一次失败/啰嗦输出会污染后续多轮 | 中高 |
| 文件系统与聊天上下文职责混淆 | Agent 不知道应读文件还是读聊天摘要 | 中 |
| 无上下文可观测性 | 很难解释某个 Agent 为什么没看到某条信息 | 高 |

---

## 4. 目标原则

### 4.1 不再把完整聊天流当主上下文

聊天流的第一职责是 UI 展示、审计、搜索和用户体验。Agent 执行上下文应该由专门的 Context Pack 构建，而不是简单把 session transcript 拼起来。

### 4.2 稳定前缀最大化

应该把最稳定、最可能复用的内容放在 prompt 前半段：

```text
AgentHub 固定协议
Agent Profile
Skill prompt
项目固定上下文
协作协议
输出格式
```

把每轮变化的内容放在后半段：

```text
本轮任务
最新用户指令
上游摘要
相关文件路径
错误日志
验收标准
```

### 4.3 Agent 间交接以产物和摘要为主

多 Agent 不应该靠“读完整群聊历史”协作，而应该靠：

- task work package；
- `HANDOFF.md` / `task_result.json`；
- artifact id / file path；
- 上游任务短摘要；
- 项目级 memory；
- 必要时由 Agent 自己按路径读取文件全文。

### 4.4 原始输出默认不长期注入

Agent 的完整长输出应该持久化用于审计和 UI 展示，但默认只把摘要、文件引用和关键决策注入后续 Agent。全文注入必须有明确触发条件：

- 用户 pin；
- 当前任务显式依赖；
- 调度器判定强相关；
- 下游 Agent 请求读取。

---

## 5. 建议架构：Context Pack Builder

新增一个显式的上下文构建层，替代“直接拼 transcript”的默认策略。

```text
Message History
Artifacts
Runs / Tasks
Project Memory
Pinned / Reply References
Workspace File Index
        |
        v
ContextPackBuilder
        |
        v
ContextPack
        |
        v
CliAgentService / OrchestratorExecution
```

建议结构：

```text
ContextPack {
  stable_prefix: {
    agent_profile,
    skill_prompts,
    collaboration_protocol,
    output_contract
  },
  project_memory: {
    goal,
    constraints,
    decisions,
    architecture_notes,
    current_status
  },
  task_brief: {
    task_id,
    task_title,
    role,
    acceptance_criteria,
    allowed_scope
  },
  dependency_context: {
    upstream_summaries,
    required_artifact_refs,
    required_file_refs
  },
  live_context: {
    latest_user_request,
    reply_reference,
    pinned_messages,
    recent_relevant_messages
  },
  retrieval_policy: {
    files_to_read_first,
    artifacts_to_open,
    messages_not_included_reason
  }
}
```

渲染到 CLI prompt 时，顺序必须稳定：

```text
1. AgentHub 固定协议
2. Agent Profile + Skills
3. 项目记忆摘要
4. 协作协议 / 文件交接协议
5. 当前任务包
6. 上游摘要与引用路径
7. 最新用户请求
8. 附加上下文 / 错误日志
```

---

## 6. 单聊改进方向

### 6.1 短期：显式 Context Pack

单聊继续每轮启动 CLI 进程，但不要再直接把完整 history 渲染成 transcript。改为：

```text
稳定前缀:
  Agent Profile + Skills + Context Policy

项目记忆:
  当前项目目标、关键文件、近期决策

本轮上下文:
  最新用户消息
  reply 引用
  pinned 消息
  最近少量相关消息
  相关 artifact/file refs
```

这样单聊仍然可控，且 prompt 前缀更稳定。

### 6.2 中期：Engine Session Resume 能力探测

为每个 CLI Adapter 增加 `supports_session_resume` 能力声明：

```text
ClaudeCodeAdapter:
  supports_session_resume: 待验证
  session_id_strategy: adapter-owned

CodexAdapter:
  supports_session_resume: 待验证

OpenCodeAdapter:
  supports_session_resume: 待验证
```

如果某个 CLI 能安全复用会话，则 AgentHub 可记录：

```text
engine_session_id
agent_id
project_id
session_id
last_turn_id
created_at / updated_at
```

但这必须经过真实测试，不能假设所有 CLI 都支持同样的 resume 语义。

### 6.3 长期：单聊双模式

单聊可以支持两种策略：

| 模式 | 说明 | 适用 |
|------|------|------|
| Stateless Context Pack | 每轮新进程，AgentHub 控制完整上下文 | 稳定、可审计、跨 CLI 一致 |
| Engine Session Resume | 复用底层 CLI 会话状态，AgentHub 只发增量 | 单 Agent 长对话、缓存/记忆收益明确时 |

默认应先保守使用 Stateless Context Pack。Resume 模式必须有可观测性和一键重置能力。

---

## 7. 群聊改进方向

### 7.1 不 @ 消息先交给调度器管家

群聊中用户不 @ 时，不应直接自动路由给多个 Agent 执行。完整行为规范见 [群聊调度器管家路由](../../phase3/02-orchestrator/11-group-chat-steward-routing.md)。从上下文管理角度，该入口应先做轻量分类：

```text
普通群聊消息
  -> 调度器管家轻量判断
  -> 只记录上下文 / 单 Agent 快速响应 / 多 Agent 小协作 / 生成 draft plan
```

复杂任务或涉及文件修改的长流程必须生成计划并等待用户确认。这样可以避免“不 @”消息把完整群聊 transcript 直接灌给多个 Agent，也为后续 Context Pack 构建提供稳定入口。

### 7.2 DAG Agent 输入改为任务包

每个 DAG task 不再拿完整共享消息流，而是拿：

```text
稳定前缀
项目记忆
当前 task brief
直接依赖任务摘要
必要 artifact/file refs
最新用户确认
```

下游若需要上游全文，优先读取上游产物文件，而不是由调度器把全文塞进 prompt。

### 7.3 SharedContext 降级为摘要索引

当前 `SharedContext` 把上游输出追加到 messages，并对依赖任务注入最多 3000 字符的完整产出。建议改为：

```text
SharedContext {
  task_summaries: Map<task_id, summary>
  artifact_refs: Map<task_id, artifact_refs>
  file_refs: Map<task_id, file_refs>
  risks: Map<task_id, risk_notes>
}
```

默认传摘要和引用。只有强相关依赖才注入片段。

---

## 8. 项目记忆设计

新增项目级 Memory，作为长期上下文压缩层。

建议最小结构：

```text
ProjectMemory {
  project_goal: string
  user_preferences: string[]
  constraints: string[]
  decisions: Decision[]
  current_architecture: string
  important_files: FileRef[]
  open_questions: string[]
  recent_execution_summary: string
}
```

更新时机：

- 调度器计划生成后；
- DAG execution completed 后；
- 用户显式说“记住/以后都/项目要求”；
- Artifact 产生或关键文件变更后；
- 审批通过或驳回后。

Memory 必须短、小、结构化，不能变成另一个无限增长 transcript。

---

## 9. 可观测性要求

每次 Agent 执行都应能查看 Context Pack 摘要：

```text
context_pack_id
estimated_tokens
stable_prefix_tokens
project_memory_tokens
task_brief_tokens
dependency_tokens
live_context_tokens
included_messages_count
excluded_messages_count
included_artifacts
included_files
truncated: true/false
cache_prefix_hash
```

前端调试入口可先只显示 JSON，不进入主聊天 UI。

这样才能回答：

- 这个 Agent 到底看到了什么？
- 哪些消息被排除？
- 为什么缓存可能没命中？
- 为什么下游 Agent 没看到上游细节？

---

## 10. 分阶段落地计划

### 阶段 A：记录现状与加指标

- 为单聊和群聊生成 `context_pack_debug` metadata。
- 记录每次 prompt 的 token 估算、消息数量、前缀 hash。
- 不改变运行行为，只增加可观测性。

验收：

- 每条真实 Agent 消息可在 trace/debug 中看到本轮上下文构成。
- 能比较连续两轮的 prefix hash 是否一致。

### 阶段 B：单聊 Context Pack 化

- 单聊从“完整 transcript”改为 Context Pack 渲染。
- 默认只注入最新用户消息、reply、pin、最近相关消息和项目记忆。
- 原始历史仍保留在数据库和 UI。

验收：

- 单聊连续 5 轮 token 增长不再线性追随完整历史。
- Agent 仍能通过 project memory 和 pin 回答关键上下文。

### 阶段 C：群聊 Task Package 化

- DAG task 输入由 `SharedContext.messages` 改为 task package。
- 上游输出默认摘要化，文件/Artifact 用引用传递。
- 调度器生成每个 task 的 `HANDOFF.md` 或 `task_result.json`。

验收：

- 同一 DAG 后续任务 prompt 不包含所有上游全文。
- 下游 Agent 仍能找到并读取必要产物。

### 阶段 D：Engine Resume 评估

- 针对 Claude Code、Codex、OpenCode 分别测试 resume 能力。
- 明确各 CLI 的 session id、cwd、权限、历史隔离、取消恢复语义。
- 只有通过验收的 Adapter 才启用可选 resume。

验收：

- resume 模式可开关；
- 可重置 Engine session；
- 出错时可回退到 Stateless Context Pack。

---

## 11. 非目标

- 本文不要求立即实现 Engine session resume。
- 本文不要求删除现有 `ContextManager`。
- 本文不要求把所有 Agent 输出都写成文档。
- 本文不改变消息 UI 的审计和展示职责。
- 本文不承诺 provider 级缓存一定命中；只定义 AgentHub 应如何提高稳定前缀和可观测性。

---

## 12. 决策建议

下一步不应直接重写全部上下文系统。建议先做最小闭环：

```text
Context Pack Debug Metadata
  -> 单聊 Context Pack Builder
  -> 群聊 Task Package
  -> Project Memory
  -> Engine Resume 能力探测
```

这样可以先看清 prompt 构成和缓存前缀稳定性，再逐步降低 token 成本和协作噪声。

当前最重要的产品判断是：

> 多 Agent 协作的记忆主干应该属于 AgentHub，而不是寄希望于每个底层 CLI Engine 的隐式会话记忆。

底层 Engine resume 可以作为优化层，但不能作为 AgentHub 协作正确性的基础。
