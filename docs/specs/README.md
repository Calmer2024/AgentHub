# AgentHub Specs — 功能规格文档索引

**最后更新**: 2026-06-08
**关联**: [ADR-0008](../adr/0008-revised-development-strategy.md) (开发策略)、[AgentHub-多Agent协作平台设计](../archive/AgentHub-多Agent协作平台设计.md) (核心启动需求源)、[PRD 总览](../PRD/00-Master_Hub.md) (阶段化产品需求)

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
├── phase6/                      ← Phase 6: Workspace Runtime + CLI Engine + Agent Profile + 产物入口桥接 ✅
├── phase7/                      ← Phase 7: 任务可控性 + 审批 + 环境体检 + IM 体验 + 演示闭环 + 上下文缓存策略 + 单聊/群聊常驻进程 🚧
├── phase8/                      ← Phase 8: P1 发布候选收口 📋
├── phase9/                      ← Phase 9: Cloud Workspace Foundation 📋
├── phase10/                     ← Phase 10: Sandbox Runner 与云端 Agent Runtime 📋
├── phase11/                     ← Phase 11: Cloud Preview 与 Deployment 📋
├── phase12/                     ← Phase 12: 协作、多端与高级 Artifact 📋
└── planning/                    ← 历史规划文档（参考）
```

**状态标记**: ✅ = 已完成 | 🔜 = 当前开发 | 🚧 = 收尾中 | 📋 = 计划中

---

## Phase 总览

| Phase | 名称 | 状态 | 核心交付 |
|-------|------|------|---------|
| [Phase 1](phase1/) | Walking Skeleton | ✅ | 单聊全链路：前端→API→Agent→SQLite，流式对话 |
| [Phase 2](phase2/) | Core Features | ✅ | 多 Agent、群聊、Orchestrator v1、WebSocket、产物基础 |
| [Phase 3](phase3/) | Orchestrator + Infrastructure | ✅ | EventBus、Orchestrator v2 (Pipeline + DAG)、CollaborationPanel |
| [Phase 4](phase4/) | 消息交互闭环 | ✅ | Reply/Regenerate/Pin、全文搜索 FTS5 |
| [Phase 5](phase5/) | 产物工作台能力 | ✅ | 对已有 Artifact 提供版本链 + Diff、在线编辑；不宣称上游产物生成入口已完整打通 |
| [Phase 6](phase6/) | Workspace Runtime + CLI Engine + Agent Profile + 产物入口桥接 | ✅ | 本机 workspace 创建/绑定、真实 CLI Agent、Agent = Engine + Toolset 建模、执行轨迹、消息级 Artifact Card、文件编辑器、代码引用、版本管理 |
| [Phase 7](phase7/) | 任务可控性 + 审批 + 环境体检 + IM 体验 + 演示闭环 | 🚧 | v1.0 本机 MVP 基线已覆盖运行控制、审批、体检、IM 会话基线和 UI 加固；7E Engine Session / 上下文包策略与 7F Claude Code stdin JSONL、Codex/OpenCode 常驻 RPC 已记录并实现基线；群聊已同步单聊 runtime 与 workspace Artifact 链路；真实 CLI 完整自动化演示脚本待补 |
| [Phase 8](phase8/) | P1 发布候选收口 | 📋 | 收敛真实 CLI E2E、本地 Build/Export/Preview、Context Pack、Orchestrator 审批续跑、Store 拆分和截图审计 |
| [Phase 9](phase9/) | Cloud Workspace Foundation | 📋 | 建立 P2 用户/团队/RBAC、CloudWorkspaceProvider、workspace 快照/导入/审计日志基础 |
| [Phase 10](phase10/) | Sandbox Runner 与云端 Agent Runtime | 📋 | 在云端隔离 sandbox 中运行真实 CLI Agent，保持 P1 CLI 事件契约兼容，并补齐配额、secret、日志脱敏 |
| [Phase 11](phase11/) | Cloud Preview 与 Deployment | 📋 | 为云端 Artifact 提供 preview URL、Deployment pipeline、部署日志、发布 URL、重试和回滚 |
| [Phase 12](phase12/) | 协作、多端与高级 Artifact | 📋 | 补齐团队评论/通知、移动端审批预览、附件/图片输入、PPT/文档 Artifact、Git sync、对话式 Agent 创建 |

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

早期核心设计文档定义完整产品骨架，MVP 本机 workspace 链路见 [PRD-06](../PRD/06-MVP_Local_Workspace_Delivery.md)，SaaS 云端 workspace 链路见 [PRD-07](../PRD/07-SaaS_Cloud_Workspace_Delivery.md)。后续 Workspace 相关 Spec 必须说明自己服务于本机版、SaaS 版，还是二者共用的抽象契约。

Completed Phase 保留完成记录，但也要写清“已解锁任务”和“未覆盖边界”。Planned Phase 不能只列模块，要定义端到端验收场景。

---

## P2 双运行时兼容门禁

Phase 9 起进入 SaaS 云端化阶段，但 P2 开发不得破坏 P1 本机版。每个 Phase 必须同时满足以下两条硬性门禁：

1. **P1 本机版零回归**：本机 Project 创建、私聊/群聊、真实 CLI runtime、Artifact Card、本地 build/preview/export、审批续跑和 IM 基线必须继续通过真实服务验收。任何云端抽象不得让 P1 用户必须登录、必须选择团队、必须拥有云端 workspace，或暴露 cloud-only 字段才能完成本机流程。
2. **P2 可运行切片递增**：每个 SaaS Phase 都必须交付一个真实可运行的 cloud slice，而不是只沉淀 schema 或静态 UI。Phase 9 至少可创建 cloud Project 和 workspace 元数据闭环；Phase 10 至少可在 cloud runtime 路径启动并回传标准事件；Phase 11 至少可创建 cloud preview/deployment 状态闭环；Phase 12 至少可完成 Web/Mobile 协作、通知、审批和预览查看闭环。

### 强制验证矩阵

| 验证维度 | Phase 9-11 最低要求 | Phase 12 起最低要求 |
|---------|-------------------|-------------------|
| P1 local runtime | local Project + local session + Artifact/build/preview/export 回归 | 同左，且 IM 通知/未读不被 SaaS 通知中心覆盖 |
| P2 cloud runtime | 当前 Phase 的 cloud slice 真实服务可运行 | cloud workspace + runtime + preview/deploy + collaboration/mobile 真实服务可运行 |
| Web 桌面端 | 真实 Vite 页面 + `/api` 代理 + 桌面宽度截图无 P0/P1 UX 缺陷 | 同左 |
| Web 移动宽度 | Playwright mobile viewport 覆盖新增入口的轻量展示或禁用态 | MobileShell 主链路覆盖 IM、审批、状态、预览 |
| 桌面壳 | 不引入 cloud-only 依赖导致 Tauri/local 后端无法启动 | Tauri/local 后端 smoke 继续通过 |
| 移动壳 | 不要求移动端具备本机 CLI 或文件系统特权 | Capacitor/MobileShell smoke 覆盖移动入口 |

若任一门禁失败，本 Phase 不得标记为 Completed，也不得进入下一 Phase。

---

## 阅读指南

- **新成员**：从 [SPEC_TEMPLATE.md](SPEC_TEMPLATE.md) 了解 Spec 格式，然后按 Phase 顺序阅读
- **开发者**：进入当前 Phase 目录，阅读 README.md 了解验收标准，然后按子模块编号阅读 Spec
- **架构师**：从 [ADR-0008](../adr/0008-revised-development-strategy.md) 了解策略，从各 Phase README 了解完成度
