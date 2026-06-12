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

**产品优化结尾状态（Phase 15-16: SaaS 生产化收口后半段）** — Phase 14 生产 Auth 与租户隔离已完成人工验收，当前重点是围绕真实云 Sandbox Runtime、真实一键部署 Provider、线上真实 CLI Runtime 和用户可感知缺陷做实测、修复、打磨与稳定化。

范围：在 Phase 9-14 的 cloud workspace、开发态 sandbox runtime、cloud preview/deployment、协作通知、多端壳、生产 Auth、TenantScope 和 RBAC 基线上，继续把云端 runtime 与部署 provider 从占位/本机模拟推进为真实生产能力。大型 Phase 验收和发布候选需要保持 P1 本地 `workspace_path`、本机 CLI、build/preview/export 主路径零回归；小修按影响面选择相关测试。

Phase 1-14 当前代码已完成阶段实现与自动化/真实服务验收。后续开发不得让本地版必须依赖云端登录或云端 workspace，不得让 SaaS 版暴露本机特权能力，也不得让移动端承载本机 CLI 或完整桌面工作区设置。

`agenthub-module-dev`、`agenthub-code-review`、`agenthub-phase-wrapup`、`agenthub-qa-audit` 四个早期开发阶段 Skill 已退役，只保留历史文件供追溯；产品优化结尾状态下不得再调用这些 Skill 作为开发、审查、收尾或 QA 流程入口。
