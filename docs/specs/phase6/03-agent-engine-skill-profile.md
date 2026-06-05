# 03 Agent Engine + Skill Profile

**状态**: 实施中
**关联 ADR**: [ADR-0010](../../adr/0010-agent-engine-skill-model.md)
**关联 PRD**: [PRD-01](../../PRD/01-Architecture_Adapter.md), [PRD-02](../../PRD/02-Orchestrator_Engine.md), [PRD-04](../../PRD/04-Data_API_Contracts.md)
**依赖**: Phase 6 CLI Adapter 基线、Agent 设置面板、Project workspace runtime

---

## 1. 背景

Phase 6 已经接入 Claude Code、Codex、OpenCode 等真实 CLI 工具，但当前产品语言仍容易把这些 CLI 工具直接叫作 Agent。

这不符合 AgentHub 接下来的调度方向。用户真正要配置和调度的是：

```text
前端专家
后端专家
架构专家
代码审查专家
调度器
```

这些不是裸 CLI 工具，而是：

```text
Agent Profile = Engine + Skills + Context Policy
```

因此本 Spec 的目标是先完成 Agent 概念升级，让好友列表里的每个联系人都变成明确的 Agent Profile。调度器接入放到下一阶段，但它也必须遵循同一模型：调度器是绑定 `orchestrator_planner` Skill 的特殊 Agent。

---

## 2. 目标

### 2.1 产品目标

- 用户看到的是“前端专家 / 架构专家 / 调度器”，不是裸的“Claude Code / Codex”。
- 用户可以理解一个 Agent 由哪个 Engine 驱动、绑定了哪些 Skill。
- 调度器后续能基于 Skill 做可解释分配。
- 第一版不引入复杂 Skill 管理系统，先从本机 Skill Pool 只读加载，跑通模型。

### 2.2 技术目标

- 在现有 `agent_configs` 上增量增加 Skill Profile 字段。
- 保持现有 CLI Adapter 不推翻，`cli_tool/executable/init_args/env_vars` 继续作为 Engine runtime config。
- 增加轻量 Skill Registry，内置基础 Skill，并扫描本机 `SKILL.md`。
- 单聊和群聊执行前按稳定顺序组装 Skill prompt。
- AgentSelector 支持 Skill 显式匹配。

---

## 3. 术语和边界

| 概念 | 第一版定义 |
|------|------------|
| Engine | `claude_code` / `codex` / `opencode` / `custom` |
| Skill | 可复用能力定义，包含 id/name/tags/prompt；第一版来自内置列表 + 本机 Skill Pool |
| Primary Skill | Agent 的主职责，最多一个 |
| Auxiliary Skills | Agent 的辅助能力，可多个 |
| Context Policy | 上下文注入策略，第一版使用枚举/默认值 |
| Agent Profile | 用户可见好友，即 Engine + Skill bindings |
| Orchestrator Agent | 使用 `orchestrator_planner` Primary Skill 的特殊 Agent |
| Scheduler/Executor | 读取 Plan/DAG 并启动任务的后端服务，不是 Agent Profile 本身 |

---

## 4. 数据模型

### 4.1 `agent_configs` 增量字段

现有字段保留：

```text
agent_type
cli_tool
executable
init_args
env_vars
description
system_prompt
```

新增字段：

```sql
ALTER TABLE agent_configs ADD COLUMN primary_skill VARCHAR DEFAULT '';
ALTER TABLE agent_configs ADD COLUMN auxiliary_skills TEXT DEFAULT '[]' NOT NULL;
ALTER TABLE agent_configs ADD COLUMN context_policy VARCHAR DEFAULT 'workspace_coding' NOT NULL;
```

说明：

- `cli_tool` 在产品语言中对应 Engine。
- `primary_skill` 是 Skill id。
- `auxiliary_skills` 是 JSON array of Skill id。
- `context_policy` 第一版只做枚举字符串，不做复杂 JSON。

### 4.2 默认迁移策略

内置 CLI Agent 迁移为基础 Profile：

| 原 Agent | Engine | Primary Skill | Auxiliary Skills | Context Policy |
|----------|--------|---------------|------------------|----------------|
| Claude Code | `claude_code` | `general_coding` | `["workspace_editing"]` | `workspace_coding` |
| Codex | `codex` | `general_coding` | `["workspace_editing"]` | `workspace_coding` |
| OpenCode | `opencode` | `general_coding` | `["workspace_editing"]` | `workspace_coding` |

用户后续可以把 Claude Code Engine 配成“前端专家”、把 Codex Engine 配成“代码审查专家”。

---

## 5. Skill Registry

### 5.1 第一版 Skill Pool

第一版 Skill Pool 由两部分组成：

```text
内置基础 Skill
  + 用户本机 Skill 目录
```

默认本机目录：

```text
%USERPROFILE%\.agents\skills
```

在当前开发机上就是：

```text
C:\Users\czh\.agents\skills
```

可通过环境变量覆盖或追加：

```text
AGENTHUB_SKILL_ROOTS=C:\Users\czh\.agents\skills;D:\my-extra-skills
```

每个 Skill 目录约定包含：

```text
skill-id/
  SKILL.md
```

`SKILL.md` 可带 YAML 风格 front matter：

```markdown
---
name: frontend-design
description: Create distinctive frontend interfaces.
tags: frontend, ui, design
---

这里是注入给 Agent 的完整 Skill prompt。
```

如果本机 Skill ID 和内置 Skill ID 重名，本机 Skill 覆盖内置 Skill。这样用户可以用自己的 Skill Pool 替换默认行为。

内置基础 Skill：

| Skill ID | Name | Tags | Purpose |
|----------|------|------|---------|
| `general_coding` | 通用工程师 | `code`, `workspace`, `implementation` | 默认代码任务 |
| `frontend_engineer` | 前端工程师 | `frontend`, `react`, `ui`, `css` | 前端界面和交互 |
| `backend_engineer` | 后端工程师 | `backend`, `api`, `database`, `python` | API、数据库、服务端逻辑 |
| `architect` | 架构师 | `architecture`, `design`, `schema`, `plan` | 方案、架构、数据模型 |
| `code_reviewer` | 代码审查 | `review`, `test`, `security`, `quality` | 审查、测试、安全 |
| `workspace_editing` | Workspace 编辑 | `file`, `diff`, `workspace` | 文件读写、diff、项目目录操作 |
| `web_preview` | Web 预览 | `preview`, `html`, `vite`, `web` | 预览和 Web 产物 |
| `orchestrator_planner` | 调度器规划 | `orchestrator`, `dag`, `plan`, `assignment` | 只产出计划和 DAG |

### 5.2 Skill 数据结构

```python
@dataclass
class SkillDefinition:
    id: str
    name: str
    description: str
    tags: list[str]
    prompt: str
```

### 5.3 暂不做

- 用户自定义 Skill CRUD
- Skill 版本
- Skill 市场
- Skill 自动检索
- Skill 权限

注意：第一版已经支持读取用户本机目录中的 `SKILL.md`，但不提供 Web UI 编辑、创建、删除 Skill。

---

## 6. API 契约

### 6.1 AgentConfigRead 增加字段

```ts
interface AgentConfig {
  id: string;
  name: string;
  description: string;
  systemPrompt: string;
  agentType: "cli_wrapper";
  cliTool: "claude_code" | "codex" | "opencode" | "custom";
  executable: string | null;
  initArgs: string[];
  envVars: Record<string, string>;
  primarySkill: string;
  auxiliarySkills: string[];
  contextPolicy: "workspace_coding" | "planning_only" | "review_only" | string;
}
```

### 6.2 Create / Update 增加字段

```ts
interface AgentConfigCreate {
  name: string;
  description?: string;
  systemPrompt?: string;
  cliTool?: "claude_code" | "codex" | "opencode" | "custom";
  executable?: string | null;
  initArgs?: string[];
  envVars?: Record<string, string>;
  primarySkill?: string;
  auxiliarySkills?: string[];
  contextPolicy?: string;
}
```

### 6.3 Skill 列表 API

新增：

```http
GET /api/skills
```

返回：

```json
[
  {
    "id": "frontend_engineer",
    "name": "前端工程师",
    "description": "负责前端界面、交互、组件和样式实现",
    "tags": ["frontend", "react", "ui", "css"],
    "source": "builtin",
    "path": null
  }
]
```

第一版 API 只读，不提供创建/编辑/删除。

---

## 7. Prompt Assembly

### 7.1 组装顺序

`CliAgentService` 在调用 adapter 前组装最终 system prompt：

```text
1. Engine base instruction
2. Primary skill prompt
3. Auxiliary skill prompts
4. Agent custom systemPrompt
5. Context policy instruction
6. Task-specific instruction / role prompt
7. User transcript
```

### 7.2 Skill 缺失策略

- `primarySkill` 为空：使用 `general_coding`。
- `auxiliarySkills` 中存在未知 id：忽略，并在执行轨迹或后端日志记录 warning。
- `orchestrator_planner` 必须配 `planning_only` context policy；若未配置，后端仍按 `planning_only` 兜底。

### 7.3 Orchestrator Skill 约束

`orchestrator_planner` prompt 必须强调：

- 只产出计划，不直接改文件。
- 输出符合 Plan JSON / DAG schema。
- 每个任务必须包含 `required_skills`。
- 可以给出 `assigned_agent_id`，但必须说明原因。
- 不自动执行子 Agent。

---

## 8. Agent Selection

当前 AgentSelector 使用 `description + system_prompt` 做标签匹配。升级后优先级为：

1. `@mention` 精确匹配 Agent id。
2. `required_skills` 命中 `primary_skill` 或 primary skill tags。
3. `required_skills` 命中 `auxiliary_skills` 或 auxiliary skill tags。
4. fallback 到 `name + description + system_prompt`。
5. 再 fallback 到可用 Agent 列表。

评分建议：

| 命中项 | 分数 |
|--------|------|
| exact mention | 9999 |
| primary skill id 精确命中 | 100 |
| primary skill tag 命中 | 50 |
| auxiliary skill id 精确命中 | 30 |
| auxiliary skill tag 命中 | 15 |
| name/description/systemPrompt 命中 | 5 |

---

## 9. 前端改造

### 9.1 Agent 设置面板

现有 `AgentCliForm` 改成 Agent Profile 配置：

```text
基础信息
  - 显示名称
  - 备注

能力配置
  - Engine
  - Primary Skill
  - Auxiliary Skills
  - Context Policy

启动命令
  - executable
  - init args
  - env vars
```

UI 文案避免继续把 Claude Code / Codex 叫成好友本身：

- 推荐：“使用 Claude Code Engine 的前端专家”
- 避免：“Claude Code Agent”

### 9.2 Agent 列表展示

好友列表展示：

```text
前端专家
Engine: Claude Code
Skill: frontend_engineer + react/typescript
Status: ready
```

### 9.3 调试台预留

调度器调试台后续展示：

- Candidate Agent Profiles
- Engine
- Primary Skill
- Auxiliary Skills
- Required Skills 命中情况
- Assignment Reason

本 Spec 不要求本轮接入完整调度器。

---

## 10. 验收标准

### 后端

- `GET /api/agents` 返回 `primarySkill / auxiliarySkills / contextPolicy`。
- `POST /api/agents` 可保存 Skill Profile 字段。
- `PATCH /api/agents/{id}` 可更新 Skill Profile 字段。
- `GET /api/skills` 返回内置 Skill + 本机 Skill Pool 列表，并标明 `source/path`。
- 未配置 skill 的旧 Agent 自动 fallback 到 `general_coding`。
- Prompt assembly 包含 primary skill 和 auxiliary skill prompt；本机 `SKILL.md` 的正文可被注入。
- AgentSelector 能按 Skill 命中排序。

### 前端

- Agent 设置面板能选择 Engine、Primary Skill、Auxiliary Skills、Context Policy。
- 保存后刷新列表仍能看到 Skill 信息。
- 不再把 Claude Code/Codex/OpenCode 文案作为最终 Agent 身份。
- 现有 executable 检测、Codex 配置托管、启动参数保存不回归。

### 文档/概念

- PRD/CONTEXT/README 中的术语更新为 Engine + Skill 模型。
- ADR-0010 与本 Spec 能解释为什么调度器也是 Agent 的一种。

---

## 11. 后续接调度器

本 Spec 完成后，再做 Orchestrator Agent 接入：

```text
用户需求
  -> Orchestrator Agent (orchestrator_planner Skill)
  -> Plan JSON / DAG
  -> 后端 validate plan
  -> Scheduler 根据 required_skills 匹配 Agent Profile
  -> Executor 启动对应 Engine
```

调度器第一版仍然可以先只产出计划，不自动执行。执行闭环、审批、重试、断点续传放到后续 Spec。
