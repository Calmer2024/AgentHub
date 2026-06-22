# ADR 索引与治理规则

> ADR = Architecture Decision Record，记录架构决策的背景、选择、取舍和后续约束。  
> 本目录回答“为什么当时这样决定”，不承担“当前系统完整说明书”的职责。

## 目录职责

`docs/adr/` 保存已经发生或明确接受的架构决策。每篇 ADR 都应说明：

- 当时面对的问题和约束。
- 被考虑过的替代方案。
- 最终选择的方案。
- 选择带来的正面收益、成本和后续约束。
- 该决策是否仍然有效，或是否已被后续 ADR / PRD / 当前实现覆盖。

当前系统事实、表结构、事件契约和运行链路应优先放在 `docs/architecture/`。ADR 可以链接这些事实文档，但不应复制完整实现细节。

## 状态含义

| 状态 | 含义 | 后续开发如何使用 |
| --- | --- | --- |
| `Accepted` | 当前仍生效的架构决策 | 默认遵守；如需改变，应新增 ADR 或修订状态。 |
| `Accepted / Historical Notes` | 主决策仍有参考价值，但部分内容是历史语境 | 只采纳未被后续文档覆盖的部分。 |
| `Superseded` | 已被后续 ADR 或当前架构替代 | 不再作为约束，只作历史追溯。 |
| `Proposed` | 尚未接受 | 不作为开发约束。 |
| `Deprecated` | 决策已不推荐，但尚未完全移除 | 新开发避免继续扩大。 |

## 当前 ADR 清单

| 编号 | 文件 | 当前状态 | 决策主题 | 当前阅读建议 |
| --- | --- | --- | --- | --- |
| ADR-0001 | [0001-tech-stack-selection.md](0001-tech-stack-selection.md) | Accepted | 技术栈选型：React / FastAPI / SQLite | 仍生效；细节可结合 [architecture/overview](../architecture/overview.md)。 |
| ADR-0002 | [0002-directory-structure.md](0002-directory-structure.md) | Accepted | 项目目录结构规范 | 仍生效；如目录继续扩展，应同步本索引和 `docs/README.md`。 |
| ADR-0003 | [0003-vibe-coding-philosophy.md](0003-vibe-coding-philosophy.md) | Accepted / Historical Notes | 结构化 Vibe Coding 模式 | 方法论仍有价值；具体 Skill 流程需结合 ADR-0006 和 `CONTEXT.md` 的退役说明。 |
| ADR-0004 | [0004-development-methodology.md](0004-development-methodology.md) | Accepted | 架构跑道、Walking Skeleton、增量交付 | 仍生效；用于解释为什么按 Phase 演进。 |
| ADR-0005 | [0005-target-architecture.md](0005-target-architecture.md) | Accepted | 整体目标架构：六层架构 | 当前唯一整体架构约束；旧整体架构图和横切平面图已被取代。 |
| ADR-0006 | [0006-ai-collaboration-system.md](0006-ai-collaboration-system.md) | Accepted / Historical Notes | AI 协作规范体系：Rules / Spec / Skill | Rules / PRD / ADR / Dev Log 仍生效；早期开发阶段 Skill 已退役。 |
| ADR-0007 | [0007-orchestrator-architecture.md](0007-orchestrator-architecture.md) | Accepted / Historical Notes | Orchestrator Pipeline、DAG、Plan-first 演进 | Orchestrator 的 Pipeline / DAG 决策仍有效；早期 HTTP Agent 语境已被 CLI Wrapper 决策覆盖。 |
| ADR-0008 | [0008-revised-development-strategy.md](0008-revised-development-strategy.md) | Accepted / Historical Notes | 功能板块制、Phase 4-7 路线和文档治理 | 功能板块制仍有效；Phase 路线已归档，当前状态以 `CONTEXT.md` 为准。 |
| ADR-0009 | [0009-project-workspace-model.md](0009-project-workspace-model.md) | Accepted | Project-Workspace 绑定模型、CLI 适配策略、分层渲染 | 仍是 Project-first 和 workspace runtime 的核心决策。 |
| ADR-0010 | [0010-message-level-artifact-experience.md](0010-message-level-artifact-experience.md) | Accepted | 消息级 Artifact 体验 | 仍生效；解释为什么不恢复独立 Artifact 工作台或右侧 Drawer。 |
| ADR-0011 | [0011-agent-engine-skill-model.md](0011-agent-engine-skill-model.md) | Accepted | Agent Profile = System Prompt + Rules + Toolset + Engine | 仍生效；解释 Agent 与 Engine 的区别。 |
| ADR-0012 | [0012-data-persistence-model.md](0012-data-persistence-model.md) | Accepted | 数据持久化模型：SQLite + SQLAlchemy + Project-first 数据结构 | 仍生效；解释 SQLite、核心表组和未来迁移条件。 |

## 何时新增 ADR

新增 ADR 的触发条件：

- 改变核心技术栈、运行模式、数据模型或跨端能力边界。
- 改变 Project / Session / Agent / Artifact / Runtime 等领域模型的含义。
- 引入新的长期约束，例如多租户、部署 provider、安全隔离策略。
- 推翻或显著修订已有 Accepted ADR。
- 一个设计选择未来容易被反复争论，需要留下判断依据。

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
| `docs/adr/` | 为什么做某个架构决策，以及它带来的约束。 |
| `docs/architecture/` | 当前系统事实：架构图、数据模型、运行模型、事件契约。 |
| `docs/archive/phases/` | 已完成 Phase 的历史规格、交付快照和开发日志。 |
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
