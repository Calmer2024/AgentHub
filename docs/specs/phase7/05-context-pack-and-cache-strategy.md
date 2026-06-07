# 05: Context Pack 与缓存策略

**状态**: Draft（Claude Code / Codex / OpenCode Engine Session Adapter 闭环已落地；Claude Code stdin JSONL、Codex MCP、OpenCode ACP Session Process Runtime 已实现基线）
**创建日期**: 2026-06-07
**关联**: [Phase 6 CLI Adapter](../phase6/01-cli-adapter.md)、[Phase 7 Runtime Control](01-runtime-task-control.md)、[ADR-0007 Orchestrator Architecture](../../adr/0007-orchestrator-architecture.md)、[ADR-0011 Agent Engine Skill Model](../../adr/0011-agent-engine-skill-model.md)

---

## 1. 问题摘要

历史上 AgentHub 的真实 CLI Agent 执行方式是“每轮启动一个 CLI 进程，手动拼接上下文后喂给它”。这让单聊和群聊都能跑通，但它没有充分利用 Claude Code / Codex 等底层 Engine 可能具备的会话续接、上下文缓存或长期记忆能力。

2026-06-07 的当前基线已经分两层缓解该问题：

- Engine Session Adapter：为 Claude Code / Codex / OpenCode 记录和复用底层 Engine session id；
- CLI Session Process Runtime：为 Claude Code stdin JSONL、Codex MCP、OpenCode ACP 维护真正的会话级常驻进程、turn 边界和进程复用。

因此本文后续的“每轮新进程”主要指历史基线、群聊 DAG task、未启用常驻进程的 CLI，以及常驻进程崩溃后的恢复性重启；Claude/Codex/OpenCode 单聊常驻路径不属于这个短进程模型。

历史单聊短进程路径可概括为：

```text
用户发送消息
  -> AgentHub 持久化用户消息
  -> 从数据库取 session history
  -> ContextManager 裁剪并组装 messages
  -> CliAgentService 渲染 transcript prompt
  -> 启动新的 claude/codex/opencode invocation
  -> CLI 输出流式回传
  -> AgentHub 持久化 assistant 消息
  -> CLI 进程结束
```

当前群聊路径仍保持任务级进程隔离，可概括为：

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

这意味着：AgentHub 的上下文治理仍不能只寄希望于底层 CLI 的隐式记忆。单聊可以利用 Engine Session 和已确认协议的常驻进程降低重复上下文；群聊协作正确性仍必须依赖 AgentHub 自己的 Context Pack、task package、workspace 文件和可审计消息。

---

## 2. 当前实现事实

### 2.1 单聊连续性：Engine Session + Session Process

单聊由 `SingleCliChatStream` 处理。它每轮仍创建 AgentHub run/task/message 运行记录。Claude Code 首轮通过 `--session-id <uuid>` 绑定底层 Claude 会话，并由 `CliSessionProcessRuntime` 保持 `claude -p --input-format stream-json --output-format stream-json --verbose` 进程；后续 turn 直接向同一 stdin JSONL 进程写入 user message。Codex / OpenCode 则通过 `CliRpcSessionRuntime` 命中或创建会话级常驻 RPC 进程。

历史实现中 Claude Code 默认参数是 `claude -p --output-format stream-json ...` 形态，没有显式使用 `--continue`、`--resume` 或 AgentHub 自己维护的 Engine session id。

2026-06-07 已完成两层闭环：AgentHub 新增 `engine_sessions`，由 `EngineSessionService` 为支持调用方指定 ID 的 CLI 生成稳定 Engine session invocation；随后新增 `CliSessionProcessRuntime` 与 `CliRpcSessionRuntime`，让 Claude Code、Codex、OpenCode 单聊在 AgentHub 侧真正维护长连接。Claude Code 首轮直接使用原生 `--session-id <uuid>` 绑定 AgentHub 会话身份；若常驻子进程死亡，下一轮才用 `--resume <session_id>` 恢复。resume / 常驻模式下只发送当前轮、引用和 Pin 等显式上下文，避免把 AgentHub 历史 transcript 重复灌给已恢复的 CLI 会话。

因此单聊的“连续性”现在分为三层：

- 冷启动层：AgentHub 数据库里的历史消息、`ContextManager` 裁剪、workspace 文件系统、Agent Profile / Skill / system prompt；
- Engine session 层：首轮由 AgentHub 分配 UUID 并传给 `claude --session-id <uuid>`，`engine_sessions.engine_session_id` 指向底层 Claude Code 会话；Codex / OpenCode 通过各自 JSON event 捕获原生 session id；
- Session process 层：Claude Code 私聊由 AgentHub 保持一会话一常驻 stdin JSONL 进程；Codex / OpenCode 私聊由 AgentHub 保持一会话一常驻 RPC 进程。三者都按 turn 串行发送 request/message、读取明确 turn 边界，进程死掉后下一轮自动重启并标记 `recovered=true`；
- 增量 prompt 层：resume / 常驻进程只注入当前轮、reply 引用和 Pin 消息。

仍不应假设：

- 常驻进程崩溃后能恢复半轮未完成输出；当前只承诺下一轮重启并标记 `recovered=true`；
- 所有 CLI 都具备相同协议形状；Claude Code 是 stdin JSONL，Codex/OpenCode 是 JSON-RPC；
- 群聊 DAG task 可以安全共享私聊 Engine session；
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

单聊不应再直接把完整 history 渲染成 transcript。即使底层 CLI 具备原生会话或常驻进程能力，AgentHub 仍应把每轮输入收敛为显式 Context Pack：

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

这样单聊在原生会话或常驻进程中仍然可审计，且 prompt 前缀更稳定。

### 6.2 中期：Engine Session Resume 能力探测

为每个 CLI Adapter 增加 `EngineSessionResumePolicy` 能力声明。这里不能只用布尔值，因为三家 CLI 的原生续接入口、session id 来源和参数清理规则都不同：

```text
ClaudeCodeAdapter:
  supports_session_resume: 已启用
  session_id_strategy: AgentHub assigned UUID -> claude --session-id <uuid> -> engine_sessions -> claude --resume <session_id>

CodexAdapter:
  supports_session_resume: 已接入自动化覆盖
  session_id_strategy: thread/session JSON event -> engine_sessions -> codex exec resume <session_id> -

OpenCodeAdapter:
  supports_session_resume: 已接入自动化覆盖
  session_id_strategy: session JSON event -> engine_sessions -> opencode run --session <session_id>
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

已完成 Claude Code / Codex / OpenCode 的 Adapter 参数构造、session metadata 捕获和单聊两轮复用自动化测试。Claude Code 额外覆盖了 `--session-id` 首轮绑定和“没有 result metadata 也能用 AgentHub 分配的 session id 进入第二轮 resume”的回归场景。真实 CLI E2E 仍需分别补充，因为三者在 cwd 过滤、权限继承、历史隔离、取消恢复和并发交错场景上的行为不能互相推断。

### 6.3 当前：CLI Session Process Runtime

详见 [06-cli-session-process-runtime.md](06-cli-session-process-runtime.md)。当前基线：

- Claude Code 单聊启用一会话一常驻 stdin JSONL 进程，并用原生 `--session-id` / 崩溃恢复时的 `--resume` 绑定底层会话；
- Codex / OpenCode 单聊启用一会话一常驻 RPC 进程；
- `CliSessionProcessRuntime` 维护 stdin/stdout/stderr pump、turn line buffer 和 per-session lock；
- `CliRpcSessionRuntime` 维护 JSON-RPC request/response、notification queue 和 per-session lock；
- 进程 snapshot 暴露 `mode=session/rpc_session`、`protocol`、`turnActive`、`reused`、`recovered`；
- 取消、交互回复、环境体检统一走 `cli_runtime_registry`，同时覆盖短进程和常驻进程。

### 6.4 长期：单聊多模式

单聊可以支持两种策略：

| 模式 | 说明 | 适用 |
|------|------|------|
| Stateless Context Pack | 每轮新进程，AgentHub 控制完整上下文 | 稳定、可审计、跨 CLI 一致 |
| Engine Session Resume | 复用底层 CLI 会话状态，AgentHub 只发增量 | 单 Agent 长对话、缓存/记忆收益明确时 |
| Session Process Runtime | AgentHub 持有一会话一进程的 stdin/stdout 或 JSON-RPC 长连接 | 已确认 turn 边界协议的 CLI，例如 Claude Code stdin JSONL、Codex MCP、OpenCode ACP |

默认策略应按 Adapter 能力选择。Claude Code/Codex/OpenCode 私聊当前启用 Session Process Runtime；不支持可靠 turn 边界的 CLI 继续使用短进程 + Engine Session Resume。所有模式都必须有可观测性和一键重置能力。

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

### 阶段 D：Engine Session Adapter 评估

- Claude Code：已完成 `--session-id` 首轮绑定、`--resume` 后续复用和 Adapter 最小闭环，后续补真实 CLI E2E 脚本。
- Codex：已接入 `codex exec resume <session_id> -` Adapter 策略，后续补真实 CLI E2E 脚本。
- OpenCode：已接入 `opencode run --session <session_id>` Adapter 策略，后续补真实 CLI E2E 脚本。
- 明确各 CLI 的 session id、cwd、权限、历史隔离、取消恢复语义。
- 只有通过真实验收的 Adapter 才默认启用产品级可选 resume；自动化参数覆盖不等同于真实 CLI 长跑验收。

验收：

- resume 模式可开关；
- 可重置 Engine session；
- 出错时可回退到 Stateless Context Pack。

### 阶段 E：CLI Session Process Runtime

- 已新增 [06-cli-session-process-runtime.md](06-cli-session-process-runtime.md)。
- 已完成 Claude Code stdin JSONL 单聊一会话一常驻进程、turn lock、`type=result` turn 边界、取消和死进程下一轮恢复。
- 已完成 Codex MCP / OpenCode ACP 单聊一会话一常驻 RPC 进程、turn lock、JSON-RPC turn 边界、取消和死进程下一轮恢复。

验收：

- Claude Code/Codex/OpenCode 同一 session 两轮复用同一 processId；
- 不同 session 使用不同 processId；
- 同一 session 并发 turn 串行执行；
- 子进程死亡后下一轮 `recovered=true`；
- Claude Code metadata 同时记录同一 `engine_session_id` 与复用的常驻 `processId`。

---

## 11. 非目标

- 本文不要求把 Engine session resume 扩展到所有 CLI。
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
  -> Engine Session Adapter
  -> Claude Code Session Process Runtime
```

这样可以先看清 prompt 构成和缓存前缀稳定性，再逐步降低 token 成本和协作噪声。

当前最重要的产品判断是：

> 多 Agent 协作的记忆主干应该属于 AgentHub，而不是寄希望于每个底层 CLI Engine 的隐式会话记忆。

底层 Engine session 和会话级常驻进程可以作为单聊优化层，但不能作为 AgentHub 多 Agent 协作正确性的基础。
