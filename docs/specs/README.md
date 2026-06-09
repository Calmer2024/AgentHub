# AgentHub Specs — 功能规格文档索引

**最后更新**: 2026-06-09
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
├── phase7/                      ← Phase 7: 任务可控性 + 审批 + 环境体检 + IM 体验 + 演示闭环 + 上下文缓存策略 + 单聊/群聊常驻进程 ✅
├── phase8/                      ← Phase 8: P1 发布候选收口 ✅
├── phase9/                      ← Phase 9: Cloud Workspace Foundation ✅
├── phase10/                     ← Phase 10: Sandbox Runner 与云端 Agent Runtime ✅
├── phase11/                     ← Phase 11: Cloud Preview 与 Deployment ✅
├── phase12/                     ← Phase 12: 协作、多端与高级 Artifact ✅
├── phase13/                     ← Phase 13: 多端产品壳拆分 ✅
├── phase14/                     ← Phase 14: 生产 Auth 与租户隔离收口 📋
├── phase15/                     ← Phase 15: 真实云 Sandbox Runtime 📋
├── phase16/                     ← Phase 16: 真实一键部署 Provider 📋
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
| [Phase 7](phase7/) | 任务可控性 + 审批 + 环境体检 + IM 体验 + 演示闭环 | ✅ | v1.0 本机 MVP 基线已覆盖运行控制、审批、体检、IM 会话基线和 UI 加固；7E Engine Session / 上下文包策略与 7F Claude Code stdin JSONL、Codex/OpenCode 常驻 RPC 已记录并实现基线；群聊已同步单聊 runtime 与 workspace Artifact 链路 |
| [Phase 8](phase8/) | P1 发布候选收口 | ✅ | 真实 CLI E2E、本地 Build/Export/Preview、Context Pack、Orchestrator 审批续跑、Store 拆分和截图审计门禁已完成 |
| [Phase 9](phase9/) | Cloud Workspace Foundation | ✅ | 已建立 P2 用户/团队/RBAC、CloudWorkspaceProvider、workspace 导入/快照/恢复、审计日志基础，并完成 P1 local 回归 |
| [Phase 10](phase10/) | Sandbox Runner 与云端 Agent Runtime | ✅ | 已打通 cloud Project → sandbox ready → 真实 CLI 输出 → Artifact/logs/run 终态切片；配额、Secret 脱敏、P1/P2 双运行时兼容已完成 |
| [Phase 11](phase11/) | Cloud Preview 与 Deployment | ✅ | 云端 Artifact preview URL、Deployment pipeline、部署日志、发布 URL、重试和回滚已完成 |
| [Phase 12](phase12/) | 协作、多端与高级 Artifact | ✅ | 团队评论/通知、移动端审批预览、附件/图片输入、Artifact 引用、Git sync、对话式 Agent 创建已完成 |
| [Phase 13](phase13/) | 多端产品壳拆分 | ✅ | Local Desktop、SaaS Web、Mobile 三端 shell、构建命令、能力矩阵、native skeleton 和验收闭环已完成 |
| [Phase 14](phase14/) | 生产 Auth 与租户隔离收口 | 📋 | 将开发态请求头 auth 收口为生产登录、跨端用户、TenantScope、RBAC 和所有 cloud 资源租户过滤 |
| [Phase 15](phase15/) | 真实云 Sandbox Runtime | 📋 | 将 Phase 10 的本机模拟 cloud runtime 替换为真实容器/K8s/microVM runner、隔离卷、资源限制和运行清理 |
| [Phase 16](phase16/) | 真实一键部署 Provider | 📋 | 将 Phase 11 的 preview/deployment 占位链路替换为真实 HTTPS 发布、provider、release、回滚和移动端审批 |

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
2. **P2 可运行切片递增**：每个 SaaS Phase 都必须交付一个真实可运行的 cloud slice，而不是只沉淀 schema 或静态 UI。Phase 9 至少可创建 cloud Project 和 workspace 元数据闭环；Phase 10 至少可在 cloud runtime 路径启动并回传标准事件；Phase 11 至少可创建 cloud preview/deployment 状态闭环；Phase 12 至少可完成 Web/Mobile 协作、通知、审批和预览查看闭环；Phase 13 至少可证明本地版、SaaS 版、移动端具有独立 shell、独立构建和独立验收路径；Phase 14-16 必须把开发态 SaaS 切片收口为生产可上线的身份、运行时和部署 provider。

### 强制验证矩阵

| 验证维度 | Phase 9-11 最低要求 | Phase 12-13 最低要求 | Phase 14-16 生产化最低要求 |
|---------|-------------------|-------------------|-------------------|
| P1 local runtime | local Project + local session + Artifact/build/preview/export 回归 | LocalDesktopShell 独立启动，local-only UI 和本机 runtime 回归 | 本地项目不强制登录、不依赖云 runner、不被云部署 provider 替换 |
| P2 cloud runtime | 当前 Phase 的 cloud slice 真实服务可运行 | SaasWebShell 独立启动，cloud workspace + runtime + preview/deploy + collaboration/mobile 真实服务可运行 | 生产 auth、租户隔离、真实 runner、真实 provider 均在云环境验收 |
| Web 桌面端 | 真实 Vite 页面 + `/api` 代理 + 桌面宽度截图无 P0/P1 UX 缺陷 | local/saas 两个桌面 shell 分别截图，无跨端入口污染 | SaaS Web 登录、团队、运行、部署、权限失败态完整覆盖 |
| Web 移动宽度 | Playwright mobile viewport 覆盖新增入口的轻量展示或禁用态 | MobileShell 独立路由和构建，覆盖 IM、审批、状态、预览 | Mobile 与 SaaS Web 共享用户和云 workspace，只暴露移动端可执行动作 |
| 桌面壳 | 不引入 cloud-only 依赖导致 Tauri/local 后端无法启动 | Tauri skeleton 包装 local build 并 smoke 本地后端 | Tauri 桌面可离线使用本机项目，并可选登录云账号访问云项目 |
| 移动壳 | 不要求移动端具备本机 CLI 或文件系统特权 | Capacitor skeleton 包装 mobile build，移动端不导入本机特权能力 | Capacitor/MobileShell smoke 覆盖生产登录、审批、部署状态和无权限状态 |
| 安全隔离 | cloud slice 不泄漏本机物理路径 | 三端能力矩阵不暴露跨端入口 | 跨租户 API、事件、日志、workspace、secret、deployment 均有越权测试 |

若任一门禁失败，本 Phase 不得标记为 Completed，也不得进入下一 Phase。

---

## 阅读指南

- **新成员**：从 [SPEC_TEMPLATE.md](SPEC_TEMPLATE.md) 了解 Spec 格式，然后按 Phase 顺序阅读
- **开发者**：进入当前 Phase 目录，阅读 README.md 了解验收标准，然后按子模块编号阅读 Spec
- **架构师**：从 [ADR-0008](../adr/0008-revised-development-strategy.md) 了解策略，从各 Phase README 了解完成度
