# AgentHub Specs — 功能规格文档索引

**最后更新**: 2026-06-02
**关联**: [ADR-0008](../adr/0008-revised-development-strategy.md) (开发策略)

---

## 目录结构

```
specs/
├── README.md                    ← 本文件
├── SPEC_TEMPLATE.md             ← 模块规格模板
├── phase1/                      ← Phase 1: Walking Skeleton ✅
├── phase2/                      ← Phase 2: Core Features ✅
├── phase3/                      ← Phase 3: Orchestrator + Infrastructure ✅
├── phase4/                      ← Phase 4: 消息交互闭环 ✅
├── phase5/                      ← Phase 5: 产物深度管理 📋
├── phase6/                      ← Phase 6: CLI 适配器 📋
├── phase7/                      ← Phase 7: UX 体验闭环 📋
└── planning/                    ← 历史规划文档（参考）
```

**状态标记**: ✅ = 已完成 | 🔜 = 当前开发 | 📋 = 计划中

---

## Phase 总览

| Phase | 名称 | 状态 | 核心交付 |
|-------|------|------|---------|
| [Phase 1](phase1/) | Walking Skeleton | ✅ | 单聊全链路：前端→API→Agent→SQLite，流式对话 |
| [Phase 2](phase2/) | Core Features | ✅ | 多 Agent、群聊、Orchestrator v1、WebSocket、产物基础 |
| [Phase 3](phase3/) | Orchestrator + Infrastructure | ✅ | EventBus、Orchestrator v2 (Pipeline + DAG)、CollaborationPanel |
| [Phase 4](phase4/) | 消息交互闭环 | ✅ | Reply/Regenerate/Pin、全文搜索 FTS5 |
| [Phase 5](phase5/) | 产物深度管理 | 📋 | 版本链 + Diff、在线编辑 (Tool Calling) |
| [Phase 6](phase6/) | CLI 适配器 | 📋 | PTY 进程管理、ANSI 清洗、交互拦截 |
| [Phase 7](phase7/) | UX 体验闭环 | 📋 | 三栏布局、产物抽屉、审批卡片、全局打磨 |

---

## 阅读指南

- **新成员**：从 [SPEC_TEMPLATE.md](SPEC_TEMPLATE.md) 了解 Spec 格式，然后按 Phase 顺序阅读
- **开发者**：进入当前 Phase 目录，阅读 README.md 了解验收标准，然后按子模块编号阅读 Spec
- **架构师**：从 [ADR-0008](../adr/0008-revised-development-strategy.md) 了解策略，从各 Phase README 了解完成度
