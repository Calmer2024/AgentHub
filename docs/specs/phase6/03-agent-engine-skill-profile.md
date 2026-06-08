# 03 Agent Engine + Toolset Profile

**状态**: 已更新  
**关联 ADR**: [ADR-0011](../../adr/0011-agent-engine-skill-model.md)  
**关联 PRD**: [PRD-01](../../PRD/01-Architecture_Adapter.md), [PRD-02](../../PRD/02-Orchestrator_Engine.md), [PRD-04](../../PRD/04-Data_API_Contracts.md)  
**依赖**: Phase 6 CLI Adapter 基线、Agent 设置面板、Project workspace runtime

---

## 1. 背景

Phase 6 已经接入 Claude Code、Codex、OpenCode 等真实 CLI 工具，但产品语言必须继续避免把底层 CLI 工具直接叫作 Agent。

旧版本使用 `Primary Skill + Auxiliary Skills` 表达 Agent 能力，并提供一组产品内置 Skill。该模型已被弃用：用户自定义 Agent 不再区分主 Skill 和辅助 Skill，而是绑定一组工具集；内置专家身份也不再藏在 Skill prompt 里，而是完整沉淀为 Agent 模板。

---

## 2. 目标

### 2.1 产品目标

- 用户看到的是“前端工程师 / 系统架构师 / UX/UI设计师 / 调度器”，不是裸的“Claude Code / Codex”。
- 用户自定义 Agent 时只配置工具集，不理解主辅 Skill 层级。
- 添加 Agent 面板提供专家模板，模板职责清晰、边界不重叠，并默认使用 Codex Engine。
- Agent 可以设置头像：6 种预设头像 + 用户上传图片。
- 面向开发者的调度器测试台从正式聊天界面移出，成为独立可进入页面。

### 2.2 技术目标

- 在 `agent_configs` 上新增 `toolset` 和 `avatar` 字段。
- 保留旧 `primary_skill / auxiliary_skills` 作为内部兼容字段，不作为用户配置模型。
- `GET /api/skills` 只返回本机 `SKILL.md` 扫描结果。
- Prompt 组装按 System Prompt → Rules → 本机工具集 → Context Policy 的顺序执行。
- 前端 Agent 表单展示工具集、头像、Engine、上下文策略和运行参数。

---

## 3. 术语和边界

| 概念 | 当前定义 |
|------|----------|
| Engine | `claude_code` / `codex` / `opencode` / `custom` |
| System Prompt | 用户定义的 Agent 身份、业务边界和职责范围 |
| Rules | 用户定义的长期行为规则、说话风格和基本原则 |
| Toolset | Agent 绑定的一组工具条目；当前只从本机 Skill 目录扫描 |
| Local Skill | 本机 `SKILL.md`，可注入 Prompt；不等同于产品内置专家模板 |
| Context Policy | 上下文注入策略，第一版使用枚举/默认值 |
| Avatar | Agent 头像，支持 `preset:*` 或上传图片 data URL |
| Agent Profile | 用户保存后的可见好友，即 System Prompt + Rules + Toolset + Avatar + Context Policy + Runtime Config + Engine |
| Orchestrator Agent | 特殊 Agent Profile，负责计划、分流和 DAG 建议 |

---

## 4. 数据模型

### 4.1 `agent_configs` 增量字段

保留现有字段：

```text
agent_type
cli_tool
executable
init_args
env_vars
description
system_prompt
rules
primary_skill        # 内部兼容字段
auxiliary_skills     # 内部兼容字段
context_policy
```

新增字段：

```sql
ALTER TABLE agent_configs ADD COLUMN toolset TEXT DEFAULT '[]' NOT NULL;
ALTER TABLE agent_configs ADD COLUMN avatar TEXT DEFAULT '' NOT NULL;
```

说明：

- `toolset` 是 JSON array of local Skill id 或模板能力标签。
- `avatar` 保存 6 种预设头像 ID（如 `preset:blue`），或上传图片的 data URL。
- 旧字段暂时保留，用于 Orchestrator 内部识别和旧测试兼容。

### 4.2 添加 Agent 内置模板

内置模板展示在“添加 Agent”配置卡片内，不自动进入好友列表。用户选择模板并保存后，才创建为真实 Agent。模板默认使用 Codex Engine：

| Agent | Context Policy | Toolset 标签 |
|-------|----------------|--------------|
| 产品经理 | `planning_only` | product_strategy / scope_control / acceptance_criteria |
| UX/UI设计师 | `planning_only` | interaction_flow / visual_system / ux_state_coverage |
| 测试工程师 | `review_only` | risk_based_testing / api_regression / frontend_ux_testing |
| 前端工程师 | `workspace_coding` | react_typescript / state_management / responsive_ui |
| 后端工程师 | `workspace_coding` | fastapi_service / domain_logic / integration_testing |
| 数据库工程师 | `workspace_coding` | schema_design / migration_safety / query_integrity |
| 系统架构师 | `planning_only` | system_boundary / contract_design / architecture_decision |

旧数据处理：

- 旧版本自动 seed 出来的 `前端工程师 / 后端工程师 / 测试工程师 / 数据库工程师 / 系统架构师 / 产品经理 / UX/UI设计师` 专家好友会被归档，不继续占用好友列表。
- `需求分析师`、`文档专家` 归档，不再作为内置模板。
- 用户手动创建的同名自定义 Agent 不按名称粗暴归档，只有旧模板角色键匹配时才隐藏。

---

## 5. 本机 Skill Registry

`GET /api/skills` 只读扫描本机目录：

```text
%USERPROFILE%\.agents\skills
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

产品不再提供内置 Skill。`api_designer`、`ux_designer`、`frontend_engineer` 等旧内置 Skill 从 API 和前端选择项中移除。

---

## 6. API 契约

### 6.1 AgentConfigRead

```ts
interface AgentConfig {
  id: string;
  name: string;
  description: string;
  systemPrompt: string;
  rules: string;
  agentType: "cli_wrapper";
  cliTool: "claude_code" | "codex" | "opencode" | "custom";
  executable: string | null;
  initArgs: string[];
  envVars: Record<string, string>;
  toolset: string[];
  avatar: string;
  contextPolicy: "workspace_coding" | "planning_only" | "review_only" | string;
}
```

### 6.2 Create / Update

```ts
interface AgentConfigCreate {
  name: string;
  description?: string;
  systemPrompt?: string;
  rules?: string;
  toolset?: string[];
  avatar?: string;
  cliTool?: "claude_code" | "codex" | "opencode" | "custom";
  executable?: string | null;
  initArgs?: string[];
  envVars?: Record<string, string>;
  contextPolicy?: string;
}
```

旧 `primarySkill / auxiliarySkills` payload 暂时兼容，但前端不再发送。

### 6.3 Skill 列表 API

```http
GET /api/skills
```

返回本机 Skill：

```json
[
  {
    "id": "local-fixture-skill",
    "name": "local-fixture-skill",
    "description": "Local fixture skill for registry tests.",
    "tags": ["fixture"],
    "source": "filesystem",
    "path": "C:/Users/.../SKILL.md"
  }
]
```

---

## 7. Prompt Assembly

组装顺序：

```text
1. Engine base instruction
2. Agent System Prompt
3. Agent Rules
4. Local Tool prompt（toolset 中能在本机 SkillRegistry 命中的条目）
5. Agent Toolset 标签摘要（未命中本机 Skill 的条目）
6. Context Policy instruction
7. Task-specific instruction / role prompt
8. User transcript
```

缺失策略：

- `toolset` 为空：不注入工具 prompt。
- `toolset` 包含未知 id：作为标签摘要注入，不报错。
- 本机 Skill ID 重名时，本机目录扫描结果按最后加载覆盖。

---

## 8. 前端改造

### 8.1 Agent 设置面板

配置项：

```text
模板（仅添加 Agent 时显示）
  - 产品经理 / UX/UI设计师 / 测试工程师 / 前端工程师 / 后端工程师 / 数据库工程师 / 系统架构师

基础信息
  - 头像：6 种预设 + 上传图片
  - 显示名称
  - 备注

身份与规则
  - System Prompt
  - Rules

能力配置
  - Engine
  - Toolset（本机 Skill 多选）
  - Context Policy

启动命令
  - executable
  - init args
  - env vars
```

不再展示“主 Skill / 辅助 Skills”。

### 8.2 Agent 列表展示

好友列表展示 Agent 自己的头像、名称、Engine 状态和工具集数量，不再用底层 Engine 图标代表 Agent 身份。

### 8.3 开发者页面

“调度器测试台”从主聊天界面移除，改为独立开发者页面：

```text
#/dev/orchestrator
```

主侧栏不再显示调度器测试台入口。

---

## 9. 验收标准

### 后端

- `GET /api/agents` 返回 `toolset / avatar / contextPolicy / systemPrompt / rules`。
- `POST /api/agents` 可保存 `toolset / avatar`。
- `PATCH /api/agents/{id}` 可更新 `toolset / avatar`。
- 默认活跃好友不自动包含 7 个专家模板；专家模板只在添加 Agent 面板中出现。
- 旧“需求分析师 / 文档专家”和旧版本自动 seed 的专家模板不再作为活跃默认好友出现。
- `GET /api/skills` 只返回本机 Skill，且 source 为 `filesystem`。
- Prompt assembly 能注入本机 Skill prompt，并把未知 toolset 条目作为标签摘要。

### 前端

- Agent 设置面板只展示工具集，不展示主 Skill / 辅助 Skill。
- 添加 Agent 面板可选择 7 个专家模板，选择后预填身份、规则、工具集、头像和 Codex Engine。
- 可选择 6 种预设头像。
- 可上传图片头像并立即预览。
- 保存后列表和聊天头像使用 Agent 自己的头像。
- 主界面不再内嵌调度器测试台。
- `#/dev/orchestrator` 可进入开发者调度器页面。

### 文档/概念

- CONTEXT、ADR-0011、本 Spec 对 Agent Profile 的定义一致。
- 文档中不再把内置专家身份描述为 Skill 组合。
