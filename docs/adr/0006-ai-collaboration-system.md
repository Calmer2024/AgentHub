# ADR-0006: AI 协作规范体系 —— Rules / Spec / Skill 三层沉淀

**Date**: 2026-05-26
**Status**: Accepted

## Context

考察要点中"沉淀出和 AI 协作的 Spec、Skill、Rules 等协作规范"权重 30%，是最高权重项。这要求我们不是"用了 AI 写代码"，而是**建立了一套成体系的、可演示的、持续沉淀的人机协作方法**。答辩时需要展示这些协作产物的完整性和演进过程。

## Decision

建立三层 AI 协作体系：

```
┌──────────────────────────────────────────────┐
│              Skill 层（能力复用）              │
│  可重复调用的 AI 工作流，一键执行常见任务       │
│  文件位置: .claude/skills/*.md                │
│  触发方式: /skill-name 或自然语言匹配           │
├──────────────────────────────────────────────┤
│              Spec 层（规格定义）               │
│  每个功能模块的"完工标准"，AI 和人共同遵守      │
│  文件位置: docs/specs/{module}-spec.md         │
│  触发方式: 开发前要求 AI 阅读对应 Spec          │
├──────────────────────────────────────────────┤
│              Rules 层（全局约束）              │
│  AI 在整个项目中必须遵守的底线规则             │
│  文件位置: CLAUDE.md + .trae/rules/            │
│  触发方式: 自动加载，每次对话生效              │
└──────────────────────────────────────────────┘
```

### 三层详细定义

#### Rules 层（全局约束，始终生效）

| 文件 | 作用 | 加载时机 |
|------|------|---------|
| `CLAUDE.md` | 项目级 AI 行为指南：架构约束、技术栈、禁止事项、代码风格 | Claude Code 每次对话自动加载 |
| `.trae/rules/project_rules.md` | 开发铁律：避免臃肿文件、提交规范、注释语言 | Trae IDE 每次对话自动加载 |

Rules 的内容类型：
- **技术栈锁定**：只能用 React+Vite / FastAPI+SQLAlchemy / SQLite
- **架构约束**：只能向下依赖、模块间通过接口通信
- **代码铁律**：避免单文件承担过多职责、禁止 any 类型（前端）、API 路由必须做参数校验。行数只是代码气味提示，不作为硬性拆分门槛。
- **禁止事项**：禁止提前建"以后用"的抽象、禁止跳过接口定义直接写实现

#### Spec 层（功能规格，按需加载）

| 文件 | 作用 | 何时创建 |
|------|------|---------|
| `docs/specs/SPEC_TEMPLATE.md` | 功能规格模板：统一格式，所有模块 Spec 照此填写 | Phase 0 创建 |
| `docs/specs/{module}-spec.md` | 每个功能模块的详细规格 | 每个增量开始前 |

Spec 必须包含的章节：
1. **目标**：这个模块要解决什么问题（1-2 句话）
2. **输入输出**：接口签名、数据格式
3. **行为规格**：正常流程、异常流程、边界条件
4. **验收标准**：可手动验证的具体 checklist
5. **依赖**：需要哪些已有模块
6. **不在范围内**：明确不做什么（防止范围蔓延）

#### Skill 层（能力复用，按需触发）

| Skill | 作用 | 适用场景 |
|-------|------|---------|
| `agenthub-module-dev` | 标准模块开发流程：读 Spec → 写接口 → 写实现 → 写测试 → 提交 | 每个新模块开发时 |
| `agenthub-code-review` | 代码审查：检查接口契约、类型安全、规则遵循 | 模块完成后 |
| `agenthub-spec-write` | 辅助编写功能 Spec：根据用户描述生成标准化 Spec | 新功能规划时 |

Skill 的本质是**把重复的 AI 协作模式封装成可复用的 Prompt 模板**。每次开发不用重新描述流程，一句 `/agenthub-module-dev` 就能启动标准化开发流水线。

### 沉淀的演示逻辑（答辩时）

```
1. Rules 层 → 展示 CLAUDE.md + project_rules.md，说明"这是 AI 在项目里的宪法"
2. Spec 层 → 展示 SPEC_TEMPLATE + 至少 2 个已完成的模块 Spec，
   说明"每个功能开发前，人和 AI 先就这份 Spec 达成一致"
3. Skill 层 → 展示自定义 Skill 文件 + 使用记录，
   说明"重复流程封装成 Skill，一行命令启动标准化开发"
4. 演进过程 → 展示 Git 历史中 Rules/Spec/Skill 的迭代修改，
   说明"这些规范不是一次写完的，是在开发中持续打磨的"
```

### 沉淀节奏

| 阶段 | Rules 沉淀 | Spec 沉淀 | Skill 沉淀 |
|------|-----------|-----------|------------|
| Phase 0 | 初始 CLAUDE.md + project_rules.md | SPEC_TEMPLATE + Phase 1 Skeleton Spec | agenthub-module-dev (v1) |
| Phase 2.1 | 补充新发现的禁止事项 | Agent Adapter Spec | 更新 Skill 到 v2 |
| Phase 2.2 | 补充 Service 层规则 | Message Service Spec | agenthub-code-review |
| Phase 2.3 | 补充 Event/Orchestrator 规则 | Orchestrator Spec | - |
| Phase 2.4 | 补充 Artifact/Context 规则 | Artifact Service Spec | agenthub-spec-write |
| Phase 3-4 | 规则趋于稳定 | 补齐剩余 Spec | 根据实际痛点新增 Skill |

## Consequences

- 每个增量开始前，必须完成对应模块的 Spec 文档
- CLAUDE.md 在开发过程中持续更新（发现新规则立即写入）
- Skill 不需要一次写完美——v1 能用就行，后续迭代优化
- 答辩时可以展示 Git diff 展示 Rules/Spec/Skill 的演进历史，证明"持续沉淀"而非"一次性写完"
