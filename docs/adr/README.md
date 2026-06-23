# ADR 索引与治理规则

> ADR = Architecture Decision Record，记录项目已经确立的关键架构决策、核心设计和后续开发必须遵守的架构约束。
> 背景、取舍和触发因素只作为辅助上下文；本目录不承担“当前系统完整说明书”的职责。

## 目录职责

`docs/adr/` 保存当前仍作为活跃阅读入口的架构决策和核心设计约束。已经归档但仍可追溯的历史 ADR 放在 [../archive/adr/](../archive/adr/)。

当前系统事实、表结构、事件契约和运行链路应优先放在 `docs/architecture/`。文档分类、索引和归档规则见 [../documentation-governance.md](../documentation-governance.md)。

## 状态含义

| 状态 | 含义 | 后续开发如何使用 |
| --- | --- | --- |
| `Accepted` | 当前仍生效的架构决策 | 默认遵守；如需改变，应新增 ADR 或修订状态。 |
| `Accepted / Historical Notes` | 主决策仍有参考价值，但部分内容是历史语境 | 只采纳未被后续文档覆盖的部分。 |
| `Archived` | 已移入归档目录 | 用于追溯，不作为当前优先阅读入口。 |
| `Superseded` | 已被后续 ADR 或当前架构替代 | 不再作为约束，只作历史追溯。 |
| `Proposed` | 尚未接受 | 不作为开发约束。 |
| `Deprecated` | 决策已不推荐，但尚未完全移除 | 新开发避免继续扩大。 |

## 当前 ADR 清单

| 编号 | 文件 | 当前状态 | 决策主题 | 当前阅读建议 |
| --- | --- | --- | --- | --- |
| ADR-0001 | [0001-技术栈选型.md](0001-技术栈选型.md) | Accepted | 技术栈选型：React / FastAPI / SQLite | 仍生效；细节结合 [architecture/overview](../architecture/overview.md)。 |
| ADR-0002 | [0002-目录结构规范.md](0002-目录结构规范.md) | Accepted | 项目目录结构规范 | 仍生效；目录继续扩展时同步本索引和 [../README.md](../README.md)。 |
| ADR-0005 | [0005-目标架构.md](0005-目标架构.md) | Accepted | 整体目标架构：六层架构 | 当前整体架构约束；实现事实见 [../architecture/overview.md](../architecture/overview.md)。 |
| ADR-0007 | [0007-Orchestrator 架构设计.md](0007-Orchestrator%20架构设计.md) | Accepted / Historical Notes | Orchestrator Pipeline、DAG、Plan-first 演进 | Pipeline / DAG 决策仍有效；早期 HTTP Agent 语境已被 CLI Wrapper 决策覆盖。 |

## 归档 ADR 清单

以下 ADR 已移入 [../archive/adr/](../archive/adr/)。归档不等于彻底失效；它表示这些文件默认作为历史追溯入口，而不是当前文档主线。

| 编号 | 文件 | 当前用途 |
| --- | --- | --- |
| ADR-0003 | [../archive/adr/0003-vibe-coding-philosophy.md](../archive/adr/0003-vibe-coding-philosophy.md) | Vibe Coding 方法论历史背景 |
| ADR-0004 | [../archive/adr/0004-development-methodology.md](../archive/adr/0004-development-methodology.md) | 架构跑道、Walking Skeleton、增量交付方法论 |
| ADR-0006 | [../archive/adr/0006-ai-collaboration-system.md](../archive/adr/0006-ai-collaboration-system.md) | AI 协作规范体系；早期开发阶段 Skill 已退役 |
| ADR-0008 | [../archive/adr/0008-revised-development-strategy.md](../archive/adr/0008-revised-development-strategy.md) | 功能板块制和 Phase 4-7 路线历史 |
| ADR-0009 | [../archive/adr/0009-project-workspace-model.md](../archive/adr/0009-project-workspace-model.md) | Project-first workspace 模型历史决策 |
| ADR-0010 | [../archive/adr/0010-message-level-artifact-experience.md](../archive/adr/0010-message-level-artifact-experience.md) | 消息级 Artifact 体验决策 |
| ADR-0011 | [../archive/adr/0011-agent-engine-skill-model.md](../archive/adr/0011-agent-engine-skill-model.md) | Agent Profile / Engine / Toolset 建模决策 |
| ADR-0012 | [../archive/adr/0012-data-persistence-model.md](../archive/adr/0012-data-persistence-model.md) | SQLite + SQLAlchemy + Project-first 持久化模型 |

## 何时新增 ADR

新增 ADR 的触发条件：

- 改变核心技术栈、运行模式、数据模型或跨端能力边界。
- 改变 Project / Session / Agent / Artifact / Runtime 等领域模型的含义。
- 引入新的长期约束，例如多租户、部署 provider、安全隔离策略。
- 推翻或显著修订已有 Accepted ADR。
- 一个核心设计会成为后续开发约束，或未来容易被反复争论。

不需要新增 ADR 的情况：

- 普通 bug 修复。
- 局部 UI 文案或样式调整。
- 不改变领域模型和接口契约的小型重构。
- 已在 PRD / Spec 中明确，且没有架构取舍的新功能实现细节。

## ADR 与其他文档的边界

| 文档位置 | 回答的问题 |
| --- | --- |
| `CONTEXT.md` | 项目全局术语、当前状态、权威导航。 |
| `docs/PRD/` | 产品需求、范围、用户链路和验收口径。 |
| `docs/adr/` | 已确立的关键架构决策、核心设计和开发约束。 |
| `docs/archive/adr/` | 已归档 ADR 的历史追溯。 |
| `docs/architecture/` | 当前系统事实：架构图、数据模型、运行模型、事件契约。 |
| `docs/archive/phases/` | 已完成 Phase 的历史规格和开发日志。 |
| `docs/user-guides/` | 面向用户的配置和使用说明。 |

## 治理规则

1. ADR 编号递增，不复用编号。
2. 标题必须包含 `ADR-NNNN`。
3. ADR 正文以中文为主；英文只保留在必要的技术名词、代码标识符、文件路径、协议名和既有专有名词中。
4. 新增或重写 ADR 时，元信息和一级标题使用中文，例如“日期 / 更新 / 状态 / 背景 / 决策 / 影响 / 取代与保留”。
5. 架构关系图、依赖图、流程图优先使用 Mermaid 代码块；只有目录树、命令输出、短接口草图等不适合 Mermaid 的内容才使用纯文本代码块。
6. 每篇 ADR 必须有日期和状态。
7. 后续决策覆盖旧 ADR 时，优先新增 ADR，并在旧 ADR 顶部加修订说明或状态说明。
8. 当前实现事实不要长期塞进 ADR；应沉淀到 `docs/architecture/`。
9. 一个事实只保留一个权威源，其他文档用链接引用。
10. 文档治理通用规则以 [../documentation-governance.md](../documentation-governance.md) 为准。
