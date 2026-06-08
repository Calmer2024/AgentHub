# AgentHub 项目规则 (Trae 特化)

> 本文件是 CLAUDE.md 的补充，仅包含 Trae IDE 中需要强调的约定。
> 全局规则（技术栈、架构约束、代码规范、禁止事项）以 CLAUDE.md 为唯一权威来源。

## AI 协作铁律

> 全局规则以 [CLAUDE.md](../../CLAUDE.md) 为唯一权威来源。以下仅列出 Trae IDE 中需特别强调的要点。

1. **无 Spec 不开发**：没有对应 Spec 文档的模块，AI 应拒绝开始写代码（见 CLAUDE.md Forbidden 节）
2. **契约优先**：先定义接口（抽象类/类型），再写实现（见 ADR-0005）
3. **按需引入架构层**：只在触发条件满足时才引入新架构层（见 ADR-0004），禁止提前建"可能以后用"的抽象
4. **每个增量可演示**：一个增量结束时，必须是前端可操作、效果可见的完整状态

## Vibe Coding 核心约定

1. **架构打底优先**：正式写功能代码前，先完成顶层架构设计（Phase 0）
2. **模块逐个突破**：完成一个模块后，立即写该模块的单元测试
3. **小步提交原则**：每完成一个能跑的小功能就立刻 commit（见 docs/GIT_PROTOCOL.md）
4. **避免臃肿文件**：行数只是代码气味提示，不是硬性上限；按职责、可测试性和可理解性判断是否拆分（见 CLAUDE.md Code Rules）
5. **每日快照**：每天工作结束前 commit 标注当日进展

## 当前开发阶段

**Phase 10: Sandbox Runner 与云端 Agent Runtime** — Phase 9 云端 workspace 基座完成后的下一阶段 (2026-06-08)

范围：在 Phase 9 的 `workspaceId`、Team/RBAC 和 audit log 基座上接入云端 sandbox runner 与真实 CLI Agent Runtime，同时保持 P1 本地 `workspace_path`、本机 CLI、build/preview/export 主路径零回归。

Phase 1-8 P1 核心闭环已验收通过；Phase 9 已完成用户/团队/RBAC、CloudWorkspaceProvider、workspace 导入/快照/恢复、审计日志与 P1/P2 真实服务验收。Phase 10 不得把 cloud Agent 降级为裸 HTTP LLM API，也不得让本地版必须依赖云端登录或云端 workspace。
