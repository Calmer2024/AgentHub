# Spec: Phase 7D — MVP 演示与 UX 加固

**版本**: v1.0
**创建日期**: 2026-06-06
**状态**: Draft
**关联 ADR/PRD**: [ADR-0008](../../adr/0008-revised-development-strategy.md)、[ADR-0010](../../adr/0010-message-level-artifact-experience.md)、[PRD-03](../../PRD/03-User_Experience.md)、[PRD-05](../../PRD/05-End_to_End_Product_Flow.md)、[PRD-06](../../PRD/06-MVP_Local_Workspace_Delivery.md)
**依赖模块**: Phase 7A/7B/7C、Phase 6F Artifact Bridge deliverables、真实 Claude Code 服务验收

---

## 1. 目标

本模块负责把 Phase 7A-7C 和 Phase 6F 已实现能力打成一个稳定演示闭环，并清理会影响答辩观感的 P0/P1 UX 问题。它不是新增大功能，而是把“真实服务能跑、UI 不乱、文档和验收脚本说得清”作为 Phase 7 的完工门槛。

目标用户是项目答辩/验收时的演示者和后续接手开发的 Agent。演示脚本必须覆盖真实 Claude Code 对话、workspace 写文件、消息级 Artifact 卡片、文件编辑器、代码引用、版本管理、审批、环境体检和中枢总结。

**成功标准**（可证伪）：

- [ ] 提供一份可执行的真实 cc 对话验收脚本，覆盖本轮实现的所有用户可见能力。
- [ ] 自动化 E2E/真实服务测试至少覆盖 Project→Claude Code→Artifact→编辑/引用→审批→总结主链路。
- [ ] 前端状态拆分后，Chat、Runtime、Approval、SystemHealth 的状态互不污染，刷新/切会话不会丢 pending 状态。
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
  → [本模块] demo script + state hardening + regression matrix
  → Phase 7 完成验收
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | Phase 6F Artifact 卡片/编辑/版本管理 | 作为演示主链路能力 |
| **上游输入** | Phase 7A/B/C API 与 Store | 做端到端状态整合 |
| **下游产出** | E2E 脚本、真实服务验收日志、开发日志、deliverables | Phase 7 wrap-up 交付 |
| **本模块不通** | 新产品能力 | 本模块只做加固与验收 |

---

## 3. 跨模块契约

### 3.1 API 端点

本模块不新增业务 API。它要求以下 API 在演示脚本中全部可用：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/projects` | POST/GET | 创建/选择 Project |
| `/api/sessions` | POST/GET | 创建 Claude Code 单聊 |
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

本模块不新增表。它要求 Phase 7A/7B 的 run 与 approval 表已完成迁移，并在验收脚本中可查询。

### 3.4 跨组件 TypeScript 类型

建议拆分 Store：

```typescript
stores/
  chatStore.ts       // messages, artifacts, reply/code references
  sessionStore.ts    // projects, sessions, agents, current selection
  runtimeStore.ts    // active runs, tasks, process snapshots
  approvalStore.ts   // checkpoints, pending decisions
  systemStore.ts     // health payload, last check, blocking reasons
  searchStore.ts     // search query/results/current highlight
```

约束：

- `chatStore` 不再承载 active run、approval、health 的长期状态。
- `runtimeStore` 和 `approvalStore` 以 `sessionId` 为 key，切会话时保留未完成状态。
- `systemStore` 不保存敏感详情，只保存 health payload。

---

## 4. 行为规格

### 4.1 MVP 演示脚本

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

### 4.2 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** | 新 Project/新 Session 无卡片时界面干净，无空白工作台 | 初始状态 |
| **加载态** | run、artifact scan、health、approval 都有局部 loading | 请求中 |
| **正常态** | 消息、产物、运行状态、审批、体检同时存在时不拥挤 | 主演示链路 |
| **完成态** | 任务完成后状态收起，保留产物卡片和总结 | done |
| **错误态** | 错误局部显示，不白屏，不吞输入 | CLI/health/approval 错误 |
| **边界态** | 窄屏、长文件名、长 diff、快速切会话、刷新恢复 | E2E 覆盖 |

### 4.3 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| Vite optimize dep 过期 | 前端 504 | 页面提示刷新/自动重载 | 清缓存或重启 dev server |
| 真实 cc 未登录 | CLI error | “Claude Code 未登录或不可用” | 体检跳 AgentPanel/安装登录说明 |
| Artifact 未生成 | `createdCount=0` | “未检测到产物，可重新分析” | 手动 scan 或重发任务 |
| 审批未触发 | 无 checkpoint | 演示脚本标记失败 | 检查 task metadata |

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

---

## 6. 前端交互序列

```text
用户: 切换 session
  → 前端: 加载 messages/artifacts/runs/approvals/health
  → UI: 恢复 pending run/approval 状态

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
- [ ] AC-7D-02: Store 拆分完成，runtime/approval/system/search 不再塞在 chatStore 的长期状态里。
- [ ] AC-7D-03: 真实 cc 演示脚本可生成 `web_preview/file_tree/code_diff` 并完成编辑、引用、版本管理。
- [ ] AC-7D-04: E2E 截图验证桌面和移动宽度下无文字溢出、卡片重叠、弹窗被裁剪。
- [ ] AC-7D-05: 取消 run、审批确认、审批驳回、健康阻断四个新增主流程都有自动化测试。
- [ ] AC-7D-06: Phase 7 deliverables 包含 implementation snapshot、acceptance log、manual validation script。
- [ ] AC-7D-07: `pytest`、`tsc --noEmit`、`vitest run`、`npm run build` 均通过；Vite chunk warning 可记录但不阻断。

---

## 8. 测试策略

### 8.1 单元测试（2 条）

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| Store selectors | 2 | 切会话隔离 runtime/approval/system 状态 |

### 8.2 集成测试

- 后端 API 集成：run cancel + approval + health。
- 前端组件集成：ChatWindow 同时渲染 RuntimeControlStrip、MessageArtifactStrip、ApprovalCard。

### 8.3 E2E 测试

- `e2e/phase7_mvp_demo.py`: 启动真实服务或连接已有服务，执行主演示脚本。
- `e2e/phase7_ui_audit.py`: 桌面/移动截图检查无遮挡、不裁剪、不重叠。
- `backend/test_real_api_claude_phase7.py`: 真实 Claude Code 服务路径，断言 Artifact + run + approval。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| 演示必须走真实 CLI 服务路径 | PRD-01 CLI Wrapper；Phase 6F 验收标准 |
| 不恢复 Drawer，文档统一到消息级 Artifact | ADR-0010 |
| Store 按领域拆分 | ADR-0008 功能板块制；SPEC_TEMPLATE 跨组件契约 |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 7A | runs/cancel | 待实现 |
| Phase 7B | approvals | 待实现 |
| Phase 7C | system health | 待实现 |
| Phase 6F | ArtifactCard/FileEditor/VersionManager | 已验收 |
| E2E harness | 浏览器测试脚本 | 已有 e2e 目录，可扩展 |

---

## 11. Non-Goals

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 不新增业务功能 | 本模块只做演示和加固 | 其它 Phase |
| 不把演示脚本写成用户教程 | deliverables 可另写使用指南 | Phase wrap-up |
| 不要求所有 CLI 都真实跑完整演示 | MVP 以 Claude Code 为真实服务验收主路径 | 后续补 Codex/OpenCode |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| Phase 7 文档 | Drawer/工作台为主线 | run/approval/health/demo 为主线 | 更新索引与 ADR |
| Store | chatStore 承载过多状态 | 按 runtime/approval/system/search 拆分 | 保持现有组件 props，逐步迁移 |
| 验收 | 分散人工描述 | 自动化 + 真实 cc 脚本 + deliverables | Phase 7 wrap-up |

> **版本历史**
> - v1.0 (2026-06-06): 初始版本。
