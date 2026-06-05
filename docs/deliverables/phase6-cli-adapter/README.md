# Phase 6 CLI Adapter 交付文档

**日期**: 2026-06-05
**范围**: Phase 6B-6E，本机 CLI Agent 适配器
**状态**: 实现基线已同步

本目录记录当前 CLI Adapter 阶段的交付快照，面向交接、验收和后续开发。

## 文档清单

| 文档 | 作用 |
|------|------|
| [architecture-and-implementation.md](architecture-and-implementation.md) | 说明 CLI Adapter 当前架构、运行流程、事件模型、各 CLI 解析策略、Codex 官方/中转配置处理，以及仍需关注的技术风险。 |
| [usage-guide.md](usage-guide.md) | 面向用户和开发者，说明如何在 AgentHub 中配置和使用 Claude Code、Codex、OpenCode。 |
| [../../dev-logs/phase6-cli-adapter-dev-log.md](../../dev-logs/phase6-cli-adapter-dev-log.md) | 阶段开发日志：已完成事项、验证情况、关键决策与下一步。 |
| [../phase6-artifact-bridge/README.md](../phase6-artifact-bridge/README.md) | 6F Artifact Bridge 验收快照：消息级产物卡片、文件编辑器、代码引用与版本管理。 |

## 权威来源

长期维护的产品与规格文档仍然是：

- [Phase 6 Spec README](../../specs/phase6/README.md)
- [CLI Adapter Spec](../../specs/phase6/01-cli-adapter.md)
- [Phase 6 Dev Log](../../dev-logs/phase6-dev-log.md)
- [PRD-01 Architecture Adapter](../../PRD/01-Architecture_Adapter.md)
- [ADR-0009 Project Workspace Model](../../adr/0009-project-workspace-model.md)

本目录是当前实现阶段的实用快照。如果这里与 PRD 或 ADR 冲突，应先更新长期文档，再同步本交付目录。
