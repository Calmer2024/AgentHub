# Spec: Phase 7D — IM 体验、MVP 演示与 UX 加固

**版本**: v1.2
**创建日期**: 2026-06-06
**状态**: v1.0 Baseline — IM 能力与 v1.0 UI 加固已实现，真实 cc 完整自动化演示脚本待沉淀
**关联 ADR/PRD**: [ADR-0008](../../../../adr/0008-revised-development-strategy.md)、[ADR-0010](../../../../adr/0010-message-level-artifact-experience.md)、[PRD-03](../../../../PRD/03-User_Experience.md)、[PRD-05](../../../../PRD/05-End_to_End_Product_Flow.md)、[PRD-06](../../../../PRD/06-MVP_Local_Workspace_Delivery.md)
**依赖模块**: Phase 7A/7B/7C、Phase 6F Artifact Bridge deliverables、真实 Claude Code 服务验收

---

## 1. 目标

本模块负责把 Phase 7A-7C 和 Phase 6F 已实现能力打成一个稳定演示闭环，并把聊天界面补齐为一个更接近真实 IM 软件的 v1.0 基线。它不再只是“演示脚本收尾”，还包括会话列表、消息右键菜单、未读/免打扰、转发/多选、明亮主题和卡片化布局等会影响产品第一印象的 P0/P1 体验。

目标用户是项目答辩/验收时的演示者、后续接手开发的 Agent，以及使用 AgentHub 进行日常多会话协作的用户。演示脚本必须覆盖真实 Claude Code 对话、workspace 写文件、消息级 Artifact 卡片、文件编辑器、代码引用、版本管理、审批、环境体检和中枢总结；IM 基线必须覆盖会话管理、消息操作和清晰的时间/状态反馈。

**成功标准**（可证伪）：

- [x] 会话列表具备新建、搜索、置顶、归档箱、最近活跃排序、未读数、免打扰。
- [x] 消息气泡右键菜单支持引用、重新生成、Pin、复制、转发、多选，并带出现动画。
- [x] 转发、多选、已读、免打扰、置顶、归档走真实 API/持久化状态，不只是前端静态状态。
- [x] 每个气泡下方显示完整时间戳，Agent 名称标签取消绿点/下边框并形成独立样式。
- [x] 执行过程支持全屏弹窗查看。
- [x] 明亮主题辅色收敛为纯白，输入框外层透明，项目/聊天栏形成圆角卡片层级。
- [ ] 提供一份可执行的真实 cc 对话验收脚本，覆盖 v1.0 主链路的所有用户可见能力。
- [ ] 自动化 E2E/真实服务测试至少覆盖 Project→Claude Code→Artifact→编辑/引用→审批→总结主链路。
- [ ] 前端状态继续拆分后，Chat、Runtime、Approval、SystemHealth、Session IM 状态互不污染，刷新/切会话不会丢 pending 状态。
- [ ] P0/P1 UX 缺陷清零：无弹窗挤压、无按钮文字溢出、无输入框遮挡、无卡片互相重叠。
- [ ] 不通过标准：只有人工口头脚本，没有自动化或真实服务验证；或文档仍提右侧 Drawer 为主路线。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
Phase 7A run control
  + Phase 7B approval
  + Phase 7C health
  + Phase 6F message-level artifacts
  → [本模块] IM baseline + demo script + state hardening + regression matrix
  → Phase 7 完成验收
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | Phase 6F Artifact 卡片/编辑/版本管理 | 作为演示主链路能力 |
| **上游输入** | Phase 7A/B/C API 与 Store | 做端到端状态整合 |
| **下游产出** | IM 状态 API、E2E 脚本、真实服务验收日志、开发日志、deliverables | Phase 7 wrap-up 与 v1.0 发布交付 |
| **本模块不通** | 多端推送、企业权限、附件级联转发 | 后续增强 |

---

## 3. 跨模块契约

### 3.1 API 端点

本模块新增会话 IM 增强 API，同时要求 Phase 6/7 主链路 API 在演示脚本中全部可用：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/projects` | POST/GET | 创建/选择 Project |
| `/api/sessions` | POST/GET | 创建 Claude Code 单聊；列表支持 `includeArchived` |
| `/api/sessions/{id}` | PATCH | 置顶、归档/取消归档、免打扰、重命名 |
| `/api/sessions/{id}/read` | POST | 当前会话标记已读 |
| `/api/sessions/forward` | POST | 将一条或多条消息转发到其它会话 |
| `/api/sessions/{id}/chat` | POST SSE | 真实对话与流式执行 |
| `/api/sessions/{id}/artifacts` | GET | 拉取消息级 Artifact |
| `/api/artifacts/{id}/save` | POST | 保存编辑后的新版本 |
| `/api/artifacts/{id}/restore` | POST | 版本回滚/跳转 |
| `/api/runs/{id}/cancel` | POST | 运行取消验收 |
| `/api/approvals/{id}/approve` | POST | 审批确认 |
| `/api/approvals/{id}/reject` | POST | 审批驳回 |
| `/api/system/health` | GET/POST | 体检与发送前 guard |

### 3.2 事件

演示脚本必须至少能观察或断言：

| 事件类型 | 用途 |
|---------|------|
| `agent.process.started` | 真实 CLI 进程启动 |
| `agent.output` | 文本流式输出 |
| `artifact.scan.started/completed` | 产物扫描 |
| `artifact.created` | 产物落库与卡片出现 |
| `run.status_changed` | 运行状态 |
| `approval.created/status_changed` | 审批 |
| `orchestrator.summary.*` | 中枢总结 |

### 3.3 数据库 Schema 变更

本模块不新增表，但扩展 `sessions` 表：

| 字段 | 用途 |
|------|------|
| `is_pinned` | 会话置顶 |
| `archived_at` | 归档时间；未归档为 `NULL` |
| `unread_count` | 未读数 |
| `last_read_at` | 最后已读时间 |
| `is_muted` | 免打扰 |

迁移文件：

- `backend/migrations/018_session_pin_archive.sql`
- `backend/migrations/019_session_im_state.sql`

### 3.4 跨组件 TypeScript 类型

建议继续拆分 Store。本轮已在现有状态结构上补齐功能，后续整理时按以下方向收敛：

```typescript
stores/
  chatStore.ts       // messages, artifacts, reply/code references
  sessionStore.ts    // projects, sessions, agents, current selection
  runtimeStore.ts    // active runs, tasks, process snapshots
  approvalStore.ts   // checkpoints, pending decisions
  systemStore.ts     // health payload, last check, blocking reasons
  searchStore.ts     // search query/results/current highlight
  imStore.ts         // unread/mute/pin/archive/forward selection
```

约束：

- `chatStore` 不再承载 active run、approval、health 的长期状态。
- `runtimeStore` 和 `approvalStore` 以 `sessionId` 为 key，切会话时保留未完成状态。
- `systemStore` 不保存敏感详情，只保存 health payload。
- `imStore` 或 `sessionStore` 承担会话置顶、归档、未读、免打扰、转发选择，不让消息流状态和会话管理状态互相污染。

---

## 4. 行为规格

### 4.1 IM 基线行为

```text
1. 用户打开某个 Project
2. 会话列表默认展示未归档会话，置顶会话在第一组，普通会话按最近活跃排序
3. 若存在归档会话，列表顶部出现归档入口
4. 用户搜索关键词，列表按标题/Agent 名称过滤
5. 用户在会话菜单中选择置顶/取消置顶、免打扰、归档/取消归档
6. 后端持久化状态，刷新后仍保持
7. 有新 Agent 消息进入非当前会话时，未读数增加；进入会话或标记已读后清零
8. 用户右键消息，菜单动画出现；选择引用/Pin/转发/多选后进入对应真实流程
```

### 4.2 MVP 演示脚本

```text
1. 启动前后端真实服务
2. 创建或选择 Project，workspace 指向临时演示目录
3. 打开环境体检，确认 Claude Code、workspace、Node/Python、DeepSeek 状态
4. 创建 Claude Code 单聊
5. 发送任务：
   “请在当前 workspace 创建一个极简登录页，包含 index.html、package.json、src/App.tsx。页面要有邮箱、密码和提交按钮。”
6. 观察 run 状态和执行轨迹
7. 等待消息下方出现 web_preview、file_tree、code_diff ArtifactCard
8. 打开 file_tree，hover 文件行看 diff，点击完整预览
9. 点击编辑文件，修改按钮文案或样式并保存
10. 在编辑器中选中一段代码，添加到对话
11. 发送“基于这段代码，把按钮改为红色并增加 hover 状态”
12. 观察新 Artifact/version 产生，打开版本管理并撤销/跳转历史版本
13. 触发审批 checkpoint，点击确认继续
14. Orchestrator 输出中枢总结，说明产物、版本和后续建议
15. 保存验收日志和截图/trace
```

### 4.3 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** | 新 Project/新 Session 无卡片时界面干净，无空白工作台 | 初始状态 |
| **加载态** | run、artifact scan、health、approval 都有局部 loading | 请求中 |
| **正常态** | 会话列表、消息、产物、运行状态、审批、体检同时存在时不拥挤 | 主演示链路 |
| **完成态** | 任务完成后状态收起，保留产物卡片和总结 | done |
| **错误态** | 错误局部显示，不白屏，不吞输入 | CLI/health/approval 错误 |
| **边界态** | 窄屏、长文件名、长 diff、快速切会话、归档箱、多选转发、刷新恢复 | E2E 覆盖 |

### 4.4 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| Vite optimize dep 过期 | 前端 504 | 页面提示刷新/自动重载 | 清缓存或重启 dev server |
| 真实 cc 未登录 | CLI error | “Claude Code 未登录或不可用” | 体检跳 AgentPanel/安装登录说明 |
| Artifact 未生成 | `createdCount=0` | “未检测到产物，可重新分析” | 手动 scan 或重发任务 |
| 审批未触发 | 无 checkpoint | 演示脚本标记失败 | 检查 task metadata |
| 转发目标不存在 | 404 | “转发失败，请稍后重试” | 重新选择目标对话 |
| 转发源消息不存在 | 400 | “转发失败，请稍后重试” | 刷新消息列表 |

---

## 5. 前端页面设计

### 5.1 页面布局

保持当前三栏 Project-first 布局，不新增右侧 Drawer：

```text
ProjectSidebar | SessionSidebar | ChatWorkspace
                                ├── ChatHeader(Search, Files, Health)
                                ├── MessageList
                                │   ├── RuntimeControlStrip
                                │   ├── MessageArtifactStrip
                                │   └── ApprovalCard
                                └── ChatInput
```

### 5.2 组件树

```text
App
├── ProjectSidebar
├── SessionList
└── ChatWindow
    ├── ChatHeader
    ├── MessageBubble[]
    ├── SessionArtifactManager
    ├── FileEditorModal
    ├── ArtifactVersionManager
    ├── ApprovalCard[]
    └── ChatInput
```

### 5.3 关键视觉元素

| 元素 | 位置 | 视觉规格 |
|------|------|---------|
| ChatHeader 文件按钮 | 搜索按钮旁 | lucide `Files`，28px icon button |
| Health 按钮 | ChatHeader 或左栏 | lucide `Activity`，状态色点 |
| Runtime strip | 消息下方 | 32-40px，紧凑状态与取消 |
| Approval card | 消息下方 | 8px 圆角，琥珀边框，操作按钮清晰 |
| 代码引用条 | ChatInput 上方 | 路径/行号/删除按钮，文本不溢出 |
| 归档入口 | 会话列表顶部 | 文件夹式入口，显示归档数量 |
| 置顶会话 | 会话列表第一组 | 独立“置顶”分组和徽标 |
| 未读徽标 | 会话列表右侧 | 非免打扰高对比，免打扰弱化 |
| 消息右键菜单 | 气泡右键位置 | portal 浮层 + 出现动画 + 不被滚动容器裁剪 |

---

## 6. 前端交互序列

```text
用户: 切换 session
  → 前端: 加载 messages/artifacts/runs/approvals/health
  → UI: 恢复 pending run/approval 状态

用户: 置顶会话
  → 前端: PATCH /api/sessions/{id} { isPinned: true }
  → UI: 会话移动到置顶区第一组

用户: 归档会话
  → 前端: PATCH /api/sessions/{id} { archived: true }
  → UI: 会话移出常规列表，归档入口数量增加

用户: 右键消息并转发
  → 前端: POST /api/sessions/forward
  → 后端: 目标会话创建真实 user 消息和 forwardSource 快照
  → UI: 目标会话最近活跃时间更新

用户: 打开会话文件按钮
  → 前端: SessionArtifactManager 展示当前会话 assets
  → 用户: 预览/编辑/版本管理

用户: 运行真实 cc 脚本
  → 前端: RuntimeControlStrip + ArtifactCard + ApprovalCard 同步更新
  → E2E: 截图和断言 UI 不重叠
```

---

## 7. 验收标准

- [ ] AC-7D-01: docs 中所有 Phase 7 入口不再把右侧 Drawer 写为 P1 必做路线。
- [x] AC-7D-02: 会话列表支持搜索、置顶、归档箱、最近活跃排序。
- [x] AC-7D-03: 会话未读数、免打扰、已读清零已持久化并有测试覆盖。
- [x] AC-7D-04: 消息右键菜单支持引用、重新生成、Pin、复制、转发、多选，并带出现动画。
- [x] AC-7D-05: 转发走真实 API 并创建目标会话消息。
- [x] AC-7D-06: 执行过程可全屏弹窗查看。
- [x] AC-7D-07: Phase 7 deliverables 包含 IM hardening implementation snapshot 与 acceptance log。
- [ ] AC-7D-08: Store 拆分完成，runtime/approval/system/search/session IM 状态不再集中在 chatStore/App runtime。
- [ ] AC-7D-09: 真实 cc 演示脚本可生成 `web_preview/file_tree/code_diff` 并完成编辑、引用、版本管理。
- [ ] AC-7D-10: E2E 截图验证桌面和移动宽度下无文字溢出、卡片重叠、弹窗被裁剪。
- [ ] AC-7D-11: 取消 run、审批确认、审批驳回、健康阻断、会话归档/转发五个主流程都有自动化测试。
- [ ] AC-7D-12: `pytest`、`tsc --noEmit`、`vitest run`、`npm run build` 均通过；Vite chunk warning 可记录但不阻断。

---

## 8. 测试策略

### 8.1 单元测试（2 条）

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| Store selectors | 2 | 切会话隔离 runtime/approval/system/session IM 状态 |
| SessionService | 6 | 置顶、归档、未读、免打扰、转发 |

### 8.2 集成测试

- 后端 API 集成：run cancel + approval + health + session IM state。
- 前端组件集成：ChatWindow 同时渲染 RuntimeControlStrip、MessageArtifactStrip、ApprovalCard、右键菜单、多选转发。

### 8.3 E2E 测试

- `e2e/phase7_mvp_demo.py`: 启动真实服务或连接已有服务，执行主演示脚本。
- `e2e/phase7_ui_audit.py`: 桌面/移动截图检查无遮挡、不裁剪、不重叠。
- `backend/test_real_api_claude_phase7.py`: 真实 Claude Code 服务路径，断言 Artifact + run + approval。
- `e2e/phase7_im_audit.py`: 会话置顶、归档箱、未读、右键菜单、转发和执行过程全屏。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| 演示必须走真实 CLI 服务路径 | PRD-01 CLI Wrapper；Phase 6F 验收标准 |
| 不恢复 Drawer，文档统一到消息级 Artifact | ADR-0010 |
| Store 按领域拆分 | ADR-0008 功能板块制；SPEC_TEMPLATE 跨组件契约 |
| IM 能力必须持久化，不做静态装饰 | PRD-03 会话列表；PRD-05 IM 核心体验 |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 7A | runs/cancel | 已验收 |
| Phase 7B | approvals | 已验收 |
| Phase 7C | system health | 已验收 |
| Phase 6F | ArtifactCard/FileEditor/VersionManager | 已验收 |
| E2E harness | 浏览器测试脚本 | 已有 e2e 目录，可扩展 |

---

## 11. Non-Goals

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 不做多端推送/企业通知策略 | 当前只补本机 v1.0 IM 基线 | 后续增强 |
| 不做附件/Artifact 级联转发 | 本轮转发文本消息快照 | 后续增强 |
| 不把演示脚本写成用户教程 | deliverables 可另写使用指南 | Phase wrap-up |
| 不要求所有 CLI 都真实跑完整演示 | MVP 以 Claude Code 为真实服务验收主路径 | 后续补 Codex/OpenCode |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| Phase 7 文档 | Drawer/工作台为主线 | run/approval/health/demo 为主线 | 更新索引与 ADR |
| Session 列表 | 仅列表/重命名/删除 | 置顶、归档、未读、免打扰、转发 | 新增 sessions 字段与迁移 |
| 消息操作 | hover 操作条为主 | 右键菜单为主 | 保留真实 Reply/Pin 上下文链路 |
| Store | chatStore/App 承载过多状态 | 按 runtime/approval/system/search/session IM 拆分 | 保持现有组件 props，逐步迁移 |
| 验收 | 分散人工描述 | 自动化 + 真实 cc 脚本 + deliverables | Phase 7 wrap-up |

---

## Phase 7D 文档审计记录 (2026-06-07)

- 已同步当时入口文档：`README.md`、`CONTEXT.md`、`PROJECT_OVERVIEW.md`、`docs/README.md`、`docs/specs/README.md`、`docs/specs/phase7/README.md`。后续当前入口已收敛为 `README.md`、`CONTEXT.md`、`CLAUDE.md`。
- 已新增发布摘要：`docs/deliverables/v1.0-release/README.md`，用于记录 v1.0.0 发布范围、本轮开发总结、验证记录和未纳入项。
- 已保持未完成项透明：真实 Claude Code 完整自动化 E2E、UI 截图审计、Store 领域拆分、多端通知策略、Artifact 级联转发均未标记为完成。
- 未发现需要恢复右侧 Drawer 或独立产物工作台的引用；P1 Artifact 体验仍以 ADR-0010 的消息级 Artifact Card + 页面级弹窗为准。

> **版本历史**
> - v1.0 (2026-06-06): 初始版本。
> - v1.1 (2026-06-07): 补入 IM 基线增强、会话状态迁移、消息右键菜单、转发/多选、执行过程全屏和 v1.0 UI 加固验收项。
> - v1.2 (2026-06-07): 补入 Phase 7D 文档审计记录与 v1.0.0 发布摘要入口。
