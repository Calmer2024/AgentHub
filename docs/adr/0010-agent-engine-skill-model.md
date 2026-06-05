# ADR-0010: Agent = Engine + Skills 建模

**Date**: 2026-06-05
**Status**: Proposed
**Related**: [PRD-01](../PRD/01-Architecture_Adapter.md), [PRD-02](../PRD/02-Orchestrator_Engine.md), [ADR-0007](0007-orchestrator-architecture.md), [ADR-0009](0009-project-workspace-model.md)

## Context

Phase 6 已经把 AgentHub 的底层执行模式从 HTTP LLM API 转向本机 CLI Wrapper：Claude Code、Codex、OpenCode 由后端作为真实子进程启动，并以 Project workspace 作为 cwd 执行。

这个阶段解决了“怎么运行真实 Agent 工具”的问题，但也带来了新的概念偏差：

- 当前 UI 和代码容易把 `Claude Code`、`Codex`、`OpenCode` 直接称为 Agent。
- 数据模型里的 `agent_configs` 更像 CLI 进程配置：`cli_tool / executable / init_args / env_vars`。
- Orchestrator 目前主要通过 `description + system_prompt` 做标签匹配，能力来源隐式、不可解释、不可稳定复用。
- 用户真正想创建的是“前端专家”“架构专家”“评审专家”“调度器”这类角色，而不是裸的 Claude Code 或 Codex。

因此需要一次概念升级：CLI 工具不是 Agent 本身，而是 Agent 的执行引擎。

## Decision

AgentHub 从现在起采用以下领域模型：

```text
Engine
  = Claude Code / Codex / OpenCode / custom CLI
  = 负责真实执行、工具调用、文件读写、stdout/stderr 输出

Skill
  = 可复用能力定义
  = 包含能力标签、职责说明、Prompt 片段、适用场景

Agent Profile
  = Engine + Skill Bindings + Context Policy + Runtime Config
  = 用户可见的“AI 好友 / 专家”
```

也就是说：

```text
Claude Code 不是前端专家。
Claude Code Engine + frontend_engineer Skill 才是前端专家 Agent。
```

调度器同样遵循这个模型：

```text
Orchestrator Agent
  = Engine + orchestrator_planner Skill + planning_only Context Policy
```

Orchestrator 不再被理解成一套完全特殊的硬编码能力，而是一个绑定了调度器 Skill 的特殊 Agent Profile。第一版可以仍由后端服务调用它，但产品和领域语言上必须把它归入同一模型。

## Terminology

| Term | Meaning |
|------|---------|
| Engine | 底层执行引擎，如 `claude_code`、`codex`、`opencode`、`custom_cli` |
| Skill Pool | 全局可复用 Skill 集合，第一版可以内置，后续支持目录扫描和用户自定义 |
| Primary Skill | 一个 Agent 的主职责，决定它被调度时的主要身份 |
| Auxiliary Skills | Agent 的辅助能力，用于补充框架、语言、审查、测试、预览等能力 |
| Context Policy | 上下文组装策略，控制注入哪些历史、文件、Artifact、前驱任务产出 |
| Agent Profile | 用户可见 Agent，好友列表里的一个联系人 |
| Orchestrator Agent | 绑定调度器 Skill 的 Agent Profile，只负责产出计划或调度指令 |
| Scheduler / Executor | 后端读取 Plan/DAG 后真正启动 Agent 任务的服务，不等同于 Orchestrator Agent |

## Model Shape

第一版 Agent Profile 的目标结构：

```json
{
  "id": "agent_claude_frontend",
  "name": "前端专家",
  "engine": {
    "type": "claude_code",
    "executable": "claude",
    "init_args": ["-p", "--output-format", "stream-json"]
  },
  "primary_skill": "frontend_engineer",
  "auxiliary_skills": ["react", "typescript", "tailwind", "web_preview"],
  "context_policy": "workspace_coding"
}
```

调度器 Agent 的目标结构：

```json
{
  "id": "agent_orchestrator_planner",
  "name": "调度器",
  "engine": {
    "type": "claude_code"
  },
  "primary_skill": "orchestrator_planner",
  "auxiliary_skills": ["task_decomposition", "dag_planning", "agent_assignment"],
  "context_policy": "planning_only"
}
```

## Prompt Assembly Rule

发送消息给 Agent Profile 时，最终 Prompt 必须由稳定顺序组装，避免 Skill 和任务上下文互相污染：

```text
1. Engine base instruction
2. Agent primary skill prompt
3. Auxiliary skill prompts
4. Agent custom system prompt / user note
5. Project/session/context policy injection
6. Task-specific instruction
7. User message
```

第一版不要求 Skill 动态检索。Agent Profile 已绑定的 Skill 直接参与组装。

## Orchestrator Implications

PRD-02 中的 Orchestrator 输出 DAG/WBS 的核心方向保持不变，但 Plan 里的 Agent 分配字段需要升级：

```json
{
  "task_id": "T2",
  "title": "实现报销单列表前端",
  "required_skills": ["frontend", "react"],
  "assigned_agent_id": "agent_claude_frontend",
  "assignment_reason": "命中 frontend_engineer 主 Skill 和 react 辅助 Skill"
}
```

核心原则：

- Plan 层必须描述 `required_skills`，用于解释任务需要什么能力。
- Plan 层可以推荐或指定 `assigned_agent_id`，用于第一版执行。
- Scheduler/Executor 可以在目标 Agent 不可用时，根据 `required_skills` 寻找替代 Agent。
- 调试台必须展示“任务需要的 Skill”和“最终分配的 Agent Profile”。

## Implementation Strategy

第一版采用渐进落地，不引入过度复杂的 Skill 管理系统。

### Step 1: Schema Extension

在现有 `agent_configs` 上增量增加字段：

- `primary_skill VARCHAR`
- `auxiliary_skills TEXT`，JSON array
- `context_policy VARCHAR`

保留现有 CLI 字段：

- `cli_tool`
- `executable`
- `init_args`
- `env_vars`

### Step 2: Built-in Skill Registry

新增轻量 Skill Registry，第一版可用代码内置或 markdown 文件加载：

```json
{
  "id": "frontend_engineer",
  "name": "前端工程师",
  "tags": ["frontend", "react", "ui"],
  "prompt": "你负责前端界面、组件、交互和样式实现..."
}
```

第一版不做完整 Skill CRUD，不做市场，不做复杂权限。

### Step 3: Agent Configuration UI

Agent 设置面板从“CLI 好友配置”升级为“Agent Profile 配置”：

- Engine：Claude Code / Codex / OpenCode / Custom
- Display Name：前端专家、架构专家、调度器
- Primary Skill：单选
- Auxiliary Skills：多选
- Context Policy：下拉或默认
- Advanced Runtime：executable / init args / env vars

### Step 4: Runtime Prompt Assembly

`CliAgentService` 在渲染 CLI prompt 之前加载 Agent 绑定的 Skill，并按 Prompt Assembly Rule 组装系统上下文。

### Step 5: Orchestrator Matching

`AgentSelector` 和调试台从 `description/system_prompt` 隐式匹配升级为 Skill 显式匹配：

1. `@mention` 精确指定最高优先级
2. `required_skills` 命中 primary skill
3. `required_skills` 命中 auxiliary skills
4. fallback 到 name/description/system_prompt

## Consequences

### Positive

- 用户心智更清楚：Claude Code 是引擎，前端专家是 Agent。
- Orchestrator 分配理由可解释：因为任务需要某些 Skill，而某个 Agent 绑定了这些 Skill。
- 后续可扩展用户自定义 Agent：用户只是在 Engine 上绑定不同 Skill。
- Orchestrator 自身也能被复用和调试：它只是一个特殊 Agent。

### Costs

- 需要迁移 `agent_configs` 表和 API/前端类型。
- 需要维护第一版内置 Skill Pool。
- Prompt 组装链路需要更明确的顺序和测试。
- 旧文档里“CLI Agent = Agent”的说法需要逐步修订，但 archive 和历史 planning 文档不回填。

## Non-Goals

第一版不做：

- Skill 市场
- 用户自定义 Skill 编辑器
- Skill 版本管理
- Skill 权限系统
- 自动 Skill 检索/RAG
- Orchestrator 自动执行完整 DAG 状态机

这些都留给 Agent Profile 模型跑通后再做。

## Status Notes

本 ADR 是对 ADR-0009 的补充，而不是否定。ADR-0009 解决“Agent 如何作为 CLI 进程运行”；ADR-0010 解决“用户可见 Agent 如何由 Engine + Skills 构成”。
