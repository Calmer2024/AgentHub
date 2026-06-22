# ADR-0011: Agent Profile = System Prompt + Rules + Toolset + Engine 建模

**日期**: 2026-06-05
**更新**: 2026-06-08
**状态**: Accepted
**相关**: [PRD-01](../PRD/01-Architecture_Adapter.md), [PRD-02](../PRD/02-Orchestrator_Engine.md), [ADR-0007](0007-orchestrator-architecture.md), [ADR-0009](0009-project-workspace-model.md)

## 背景

Phase 6 已经把 AgentHub 的底层执行模式从 HTTP LLM API 转向本机 CLI Wrapper：Claude Code、Codex、OpenCode 由后端作为真实子进程启动，并以 Project workspace 作为 cwd 执行。

此前的 Agent Profile 模型把能力拆成 `Primary Skill + Auxiliary Skills`，并内置了 `api_designer`、`ux_designer`、`frontend_engineer` 等技能模板。这个模型在实践中带来三个问题：

1. 用户配置自定义 Agent 时需要理解主 Skill / 辅助 Skill 的人为层级。
2. “产品经理 / 前端工程师 / UX 设计师”等身份被拆散在 Skill prompt 里，导致身份重合、边界模糊。
3. 内置 Skill 和本机 Skill Pool 混在一起，用户很难判断哪些是自己可控的本地能力。

因此需要把“身份模板”和“本机工具集”拆开：内置专家是添加 Agent 时可套用的完整模板；用户自定义能力只来自本机 `SKILL.md` 工具集。

## 决策

AgentHub 当前采用以下领域模型：

```text
Engine
  = Claude Code / Codex / OpenCode / custom CLI
  = 负责真实执行、工具调用、文件读写、stdout/stderr 输出

Toolset
  = Agent 绑定的一组工具条目
  = 当前只从用户本机 Skill 目录扫描 SKILL.md，产品不再提供内置 Skill 列表

Agent Profile
  = System Prompt + Rules + Toolset + Context Policy + Runtime Config + Engine + Avatar
  = 用户可见的“AI 好友 / 专家”
```

也就是说：

```text
Codex 不是前端工程师。
前端工程师是一个完整 Agent 模板；用户在添加 Agent 面板中选择该模板后，才会创建为可见 Agent Profile，默认由 Codex Engine 执行，可选绑定本机工具集。
```

调度器同样遵循这个模型：

```text
Orchestrator Agent
  = 特殊 Agent Profile
  = System Prompt + Rules 中定义计划、分流、DAG 输出约束
```

内部仍暂时保留 `primary_skill / auxiliary_skills` 数据列，作为旧调度链路识别 Orchestrator 和角色匹配的兼容字段；它们不再作为用户配置模型暴露。

## Built-In Agent Templates

添加 Agent 面板内置 7 个职责不重叠的专家模板。模板不会自动进入好友列表；用户选择并保存后，才成为真实 Agent。模板默认都使用 Codex Engine：

| Agent | 责任边界 |
|-------|----------|
| 产品经理 | 产品目标、用户场景、范围边界、优先级、验收标准 |
| UX/UI设计师 | 信息架构、任务流、界面布局、交互反馈、视觉一致性 |
| 测试工程师 | 测试策略、风险建模、自动化验证、回归检查、验收报告 |
| 前端工程师 | React 组件、状态管理、界面实现、响应式布局、浏览器验证 |
| 后端工程师 | API、业务服务、权限边界、数据校验、异步流程、后端测试 |
| 数据库工程师 | 数据模型、迁移脚本、索引约束、一致性、查询性能 |
| 系统架构师 | 系统边界、模块拆分、接口契约、技术取舍、演进路径 |

旧的“需求分析师”“文档专家”不再作为内置模板保留；旧版本已经自动 seed 到好友列表里的专家模板会被归档。用户真正创建的同名自定义 Agent 不受影响。

## API Shape

Agent API 新增用户侧字段：

```json
{
  "toolset": ["local-skill-id"],
  "avatar": "preset:blue"
}
```

`GET /api/skills` 只返回本机 Skill 目录扫描结果：

```text
%USERPROFILE%\.agents\skills
AGENTHUB_SKILL_ROOTS 覆盖或追加的目录
```

产品不再返回内置 Skill，例如 `api_designer`、`ux_designer`、`frontend_engineer`。

## Prompt Assembly Rule

发送消息给 Agent Profile 时，最终 Prompt 必须由稳定顺序组装：

```text
1. Engine base instruction
2. Agent System Prompt：身份、业务边界、职责范围
3. Agent Rules：长期行为规则、说话风格、基本原则
4. 本机工具集 prompt（仅当 toolset 中的条目能在本机 SKILL.md 中找到）
5. Toolset 标签摘要（无法解析为本机 Skill 的能力标签只作为标签）
6. Project/session/context policy injection
7. Task-specific instruction
8. User message
```

Toolset 不定义 Agent 身份。Agent 的身份和边界必须来自 System Prompt 与 Rules。

## 影响

### Positive

- 自定义 Agent 配置更简单：用户只选择一组工具集，不再区分主 Skill / 辅助 Skill。
- 内置专家边界更清晰：身份、职责和长期规则沉淀到 Agent 模板本身。
- 本机 Skill 的来源更可信：`GET /api/skills` 返回的都是用户本机可检查、可维护的条目。
- 头像成为 Agent Profile 的一部分，好友列表不再被底层 Engine 图标主导。

### Costs

- 需要维护 `toolset/avatar` 新字段和旧字段兼容层。
- 旧文档、测试和调度面板里的 Skill 语言需要逐步收敛。
- Orchestrator 的内部匹配仍会短期引用旧角色键，后续可单独迁移到显式 `role_key`。

## Non-Goals

当前不做：

- Web UI 内创建/编辑本机 Skill。
- Skill 市场、版本、权限系统。
- 自动 Skill 检索/RAG。
- 完全删除数据库旧字段。
- Orchestrator 自动执行完整 DAG 状态机的重新设计。

## 状态说明

本 ADR 是对 ADR-0009 的补充，而不是否定。ADR-0009 解决“Agent 如何作为 CLI 进程运行”；ADR-0011 解决“用户可见 Agent 如何由 System Prompt、Rules、Toolset、Context Policy、Runtime Config、Avatar 和 Engine 构成”。
