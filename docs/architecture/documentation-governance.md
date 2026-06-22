# 文档治理

> 本文档说明 AgentHub 文档之间的职责边界，避免 ADR、PRD、架构事实和历史归档互相混用。

## 文档层级

```text
README.md
  -> 项目入口、运行方式、交付入口

CONTEXT.md
  -> 全局术语、当前状态、权威导航

docs/PRD/
  -> 产品需求、范围、验收口径

docs/adr/
  -> 架构决策原因和约束

docs/architecture/
  -> 当前系统事实

docs/archive/phases/
  -> 历史 Phase 规格、交付快照、开发日志

docs/user-guides/
  -> 面向用户的配置和使用说明

docs/submission/
  -> 课程/挑战赛交付材料
```

## 权威边界

| 问题 | 权威文档 |
| --- | --- |
| 项目当前是什么、读文档从哪里开始 | `README.md`, `CONTEXT.md` |
| 产品为什么要做这个能力 | `docs/PRD/` |
| 架构为什么做这个选择 | `docs/adr/` |
| 当前代码架构、数据模型、事件契约是什么 | `docs/architecture/` |
| 已完成阶段当时怎么验收 | `docs/archive/phases/` |
| 用户怎么配置和使用 | `docs/user-guides/` |
| 答辩怎么讲 | `docs/submission/` |

## ADR 规则

ADR 只回答“为什么做了这个架构决策”。它不应该长期保存完整当前实现细节。

新增 ADR 的条件：

- 改变核心领域模型。
- 改变技术栈或运行环境。
- 改变数据持久化、租户隔离、安全、部署、runtime 策略。
- 推翻已有 ADR。
- 一个选择未来会被反复争论。

不需要 ADR：

- 普通 bug 修复。
- 局部 UI 调整。
- 不改变接口和领域语义的小重构。

## Architecture 文档规则

`docs/architecture/` 保存当前事实，应随实现变化更新。

当前规划：

| 文档 | 作用 |
| --- | --- |
| `overview.md` | 当前架构总览和主链路 |
| `data-model.md` | 当前表结构、表组和数据关系 |
| `runtime-model.md` | 本机/云端 runtime、Run/Task/Process 状态 |
| `event-contracts.md` | SSE、WebSocket、EventBus 事件导航 |
| `documentation-governance.md` | 文档边界和更新规则 |

## 归档规则

`docs/archive/` 表示历史位置，不自动表示失效。

如果归档文档仍是权威需求源，必须在 `CONTEXT.md` 或 `docs/README.md` 中说明。例如：

- `docs/archive/AgentHub-多Agent协作平台设计.md` 仍是核心启动需求源。
- `docs/archive/phases/` 用于追溯已完成 Phase。

## 更新规则

1. 改领域术语：更新 `CONTEXT.md`。
2. 改产品范围：更新对应 PRD。
3. 改架构决策：新增或修订 ADR。
4. 改当前数据模型、运行链路、事件契约：更新 `docs/architecture/`。
5. 改用户操作方式：更新 `docs/user-guides/`。
6. 改答辩材料：更新 `docs/submission/`。

## 陈旧文档处理

遇到陈旧内容时按优先级处理：

1. 如果只是历史背景：在文档顶部加修订说明，标注当前口径链接。
2. 如果决策已被替代：将状态改为 `Superseded`，并链接新 ADR。
3. 如果当前事实散落在多个文档：收敛到 `docs/architecture/`，其他地方只保留链接。
4. 如果内容已无任何参考价值：移入归档或删除，但必须确保索引不再指向它。

## 一个事实一个权威源

同一事实不要复制到多个文件长期维护。

推荐写法：

```text
ADR 说明为什么选择 Project-first。
architecture/data-model.md 说明当前 Project 相关表结构。
CONTEXT.md 只给术语定义和链接。
README.md 只给入口和摘要。
```

