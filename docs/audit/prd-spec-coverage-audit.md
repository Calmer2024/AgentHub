# AgentHub PRD / Spec 覆盖审计

**日期**: 2026-06-03  
**审计对象**:
- 启动文档: [docs/archive/AgentHub-多Agent协作平台设计.md](../archive/AgentHub-多Agent协作平台设计.md)
- PRD: [docs/PRD/](../PRD/)
- Specs: [docs/specs/](../specs/)

---

## 1. 结论

当前 PRD **没有完全覆盖**启动文档。它已经覆盖了 AgentHub 的高级方向：CLI Adapter、Orchestrator、三栏工作区、Artifact Drawer、数据契约；但缺少启动文档中 IM 产品基本面的完整需求映射，也缺少一条明确的“用户输入 -> Agent 执行 -> 产物生成 -> 预览/编辑 -> 版本化 -> 部署/交付”的端到端链路。

当前 Specs **没有完全覆盖** PRD。Phase 1-5 已经实现了许多重要能力，但阶段文档过于按模块拆分，缺少每个 Phase 在全局产品链路中的定位。典型问题是 Phase 5 完成了 Artifact 工作台能力（版本、Diff、在线编辑），但文档没有提前定义“Artifact 从哪里来、如何由 Agent 输出链路创建、如何被聊天流引用、如何进入右侧抽屉”的上游入口和下游体验。

因此需要修订：
- PRD 增加启动文档需求追踪矩阵、端到端产品闭环、阶段路线图。
- Spec 增加全局链路图、阶段使命、可完成任务、未打通边界、跨 Phase 接口契约。
- Phase 5-7 重新定位为连续链路：`Artifact 工作台能力` -> `Workspace Runtime + 真实 Agent 执行入口` -> `用户体验闭环`。

---

## 2. 启动文档需求追踪矩阵

| 启动文档要求 | PRD 覆盖情况 | Spec 覆盖情况 | 结论 |
|---|---|---|---|
| IM 聊天式交互：会话列表、新建、置顶、归档、搜索、最近活跃排序 | 部分覆盖。PRD-03 有三栏布局，但未完整定义会话列表操作 | Phase 1 有新建/列表；Phase 4 有搜索；置顶/归档/排序未形成完整验收 | 需补入 PRD 与后续 UX 验收 |
| 单聊模式 | 覆盖 | Phase 1 覆盖 | 已覆盖 |
| 群聊模式：@ 多 Agent、Orchestrator 自动分派、多个 Agent 依次回复 | 覆盖 | Phase 2/3 覆盖 | 已覆盖 |
| 上下文连续：历史消息、长期 pin | PRD 有上下文管理方向，但未细化 IM 语义 | Phase 1 历史、Phase 4 pin/reply 覆盖 | 基本覆盖 |
| 消息类型：文本、代码块、图片、文件附件、网页预览、Diff、部署状态 | 部分覆盖 Artifact/Diff，图片/文件/部署状态缺范围定义 | Phase 2/5 覆盖代码/网页/Diff；图片/文件/部署未覆盖 | 需明确 P0/P1/P2 范围 |
| 消息操作：回复、引用、重新生成、复制代码、一键应用 Diff、展开预览 | PRD-03 部分覆盖 | Phase 4 覆盖 reply/regenerate/pin；Phase 5 覆盖 Diff 确认；展开预览在 Phase 7 | 基本覆盖，但需打通入口 |
| 多 Agent 接入：至少 2 个主流 Agent 平台 | 覆盖 | Phase 2 HTTP adapter 覆盖；Phase 6 Workspace Runtime + CLI wrapper 计划 | 已覆盖，但需说明 HTTP/CLI 关系 |
| 用户自建 Agent：对话式创建，设定 prompt + 工具集 | 部分覆盖 AgentConfig，但缺“对话式创建”产品细节 | Phase 2 AgentPanel 覆盖配置式创建；对话式创建未覆盖 | 需补为 P1/P2 |
| Agent 联系人：头像、名称、能力标签 | 部分覆盖 | Phase 2 Agent 管理部分覆盖 | 需补 UX 验收 |
| 产物内联：代码 Diff、网页预览卡片、附件 | PRD-03 覆盖资产卡片/抽屉 | Phase 2 基础 Artifact；Phase 5 深度管理；Phase 7 抽屉计划 | 入口链路缺失 |
| 产物预览与编辑：全屏预览、代码编辑器、版本历史、局部修改 | 覆盖 | Phase 5/7 覆盖 | 需要 Phase 7 接 UI 闭环 |
| 部署发布：聊天指令部署、状态卡片、预览 URL/源码下载 | 仅在启动文档 P2，PRD 未系统化 | Specs 未覆盖 | 需列入 P2 Roadmap |
| 多端支持：Web/桌面/移动 | 启动文档 P2，PRD 未系统化 | Specs 未覆盖 | 需列入非 MVP/P2 |
| AI 协作交付物：Spec、skill、rules、开发记录 | 部分覆盖 | docs/specs、CLAUDE、dev-logs 已覆盖 | 需在 PRD 成功标准中显式化 |

---

## 3. 全局端到端链路缺口

### 3.1 当前已具备的局部能力

1. 用户可以创建会话并与 Agent 流式聊天。
2. 用户可以在群聊中让 Orchestrator 做意图分析、Agent 选择、DAG/链式协作。
3. 用户可以 reply/regenerate/pin/search。
4. 系统有 Artifact 模型，已支持版本链、Diff、在线编辑和确认/拒绝。

### 3.2 缺失的闭环契约

| 链路节点 | 当前问题 | 应补设计 |
|---|---|---|
| 产物生成入口 | 文档没有定义“Agent 输出什么事件时创建 Artifact” | 定义 `artifact.detected` / `artifact.created` 事件、消息卡片写入规则、会话产物列表刷新规则 |
| Agent 输出到 Artifact | CLI Agent 输出与 ArtifactService 的边界不清 | Orchestrator/Adapter 只发事件；ArtifactService 统一解析、落库、版本化 |
| Artifact 到聊天流 | Phase 5 有工作台能力，但未定义卡片何时出现 | 定义 `content_type='artifact_card'` 消息，绑定 `message_id`、`task_id`、`artifact_id` |
| Artifact 到右侧抽屉 | Phase 7 只写抽屉 UI，缺数据加载与状态同步 | 定义 Drawer 从卡片、会话产物库、审批卡片三个入口打开 |
| 编辑指令回到 Agent | Phase 5 支持 edit API，但缺“在聊天中描述修改”的入口 | 定义引用当前 Artifact 后发送自然语言，自动转换为 edit intent |
| 审批继续调度 | PRD 有审批，Phase 7 有卡片，但与 Artifact 审阅未绑定 | 定义 `requires_human_approval` 任务必须产出可审阅 Artifact 或摘要 |
| 部署交付 | PRD/spec 未覆盖启动文档 P2 | 建立 P2 Deployment Phase：部署指令、状态卡片、preview URL/source bundle |

---

## 4. 修订原则

1. **不篡改已完成事实**：Phase 1-5 已完成的实现与验收记录保留。
2. **补全阶段边界**：Completed Phase 需要说明“完成了什么”和“还没打通什么”，避免后续误读。
3. **后续 Phase 必须端到端**：Phase 6 不只是 CLI 进程管理，还必须让真实 Agent 输出进入 Artifact 链路；Phase 7 不只是视觉打磨，还必须把 IM、Artifact、审批、环境体检打成演示闭环。
4. **P2 显式延期**：部署发布、多端、图片/文件附件、对话式自建 Agent 可以不进 MVP，但必须在 PRD 中有位置。
