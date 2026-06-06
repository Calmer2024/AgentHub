# AgentHub Specs — 功能规格文档索引

**最后更新**: 2026-06-06
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
├── phase5/                      ← Phase 5: 产物工作台能力 ✅
├── phase6/                      ← Phase 6: Workspace Runtime + CLI 适配器 + 产物入口桥接 ✅
├── phase7/                      ← Phase 7: 任务可控性 + 审批 + 环境体检 + 演示闭环 📋
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
| [Phase 5](phase5/) | 产物工作台能力 | ✅ | 对已有 Artifact 提供版本链 + Diff、在线编辑；不宣称上游产物生成入口已完整打通 |
| [Phase 6](phase6/) | Workspace Runtime + CLI 适配器 + 产物入口桥接 | ✅ | 本机 workspace 创建/绑定、真实 CLI Agent、执行轨迹、消息级 Artifact Card、文件编辑器、代码引用、版本管理 |
| [Phase 7](phase7/) | 任务可控性 + 审批 + 环境体检 + 演示闭环 | 📋 | run/task 取消与恢复、审批卡片、环境体检、真实 cc 演示与 UX 加固 |

---

## 北极星链路

所有 Phase 必须说明自己位于以下链路的哪一段：

```text
创建或绑定 workspace
  -> 用户输入
  -> Orchestrator/Agent 执行
  -> Agent 以 workspace_path 作为 cwd 读写文件
  -> 文件变更 / Agent 输出检测
  -> Artifact 创建
  -> 聊天流消息级 Artifact Card
  -> 页面级预览/编辑/版本化
  -> 审批继续调度
  -> 最终中枢总结
```

MVP 本机 workspace 链路见 [PRD-06](../PRD/06-MVP_Local_Workspace_Delivery.md)，SaaS 云端 workspace 链路见 [PRD-07](../PRD/07-SaaS_Cloud_Workspace_Delivery.md)。后续 Workspace 相关 Spec 必须说明自己服务于本机版、SaaS 版，还是二者共用的抽象契约。

Completed Phase 保留完成记录，但也要写清“已解锁任务”和“未覆盖边界”。Planned Phase 不能只列模块，要定义端到端验收场景。

---

## 阅读指南

- **新成员**：从 [SPEC_TEMPLATE.md](SPEC_TEMPLATE.md) 了解 Spec 格式，然后按 Phase 顺序阅读
- **开发者**：进入当前 Phase 目录，阅读 README.md 了解验收标准，然后按子模块编号阅读 Spec
- **架构师**：从 [ADR-0008](../adr/0008-revised-development-strategy.md) 了解策略，从各 Phase README 了解完成度
