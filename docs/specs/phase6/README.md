# Phase 6: Workspace Runtime + CLI Engine + Agent Profile + 产物入口桥接

**状态**: ✅ 本轮验收通过（6A Workspace Runtime、6B-6E CLI Adapter、6F Artifact Bridge 均已落地；Phase 7 已补齐群聊 runtime 与 Artifact 链路同步）
**版本**: v3.9
**更新日期**: 2026-06-08
**关联 ADR**: [ADR-0005](../../adr/0005-target-architecture.md)、[ADR-0009](../../adr/0009-project-workspace-model.md)
**关联 PRD**: [PRD-01](../../PRD/01-Architecture_Adapter.md)、[PRD-05](../../PRD/05-End_to_End_Product_Flow.md)、[PRD-06](../../PRD/06-MVP_Local_Workspace_Delivery.md)
**依赖**: Phase 3（BaseAgentAdapter / EventBus / SessionService）、Phase 5（ArtifactService）

---

## 1. 全局定位

Phase 5 完成了"已有 Artifact 的工作台能力"（版本链、Diff、在线编辑），但产物是哪里来的？Agent 在哪个目录执行的？如何从 CLI 输出变成聊天里的产物卡片？

Phase 6 回答这三个问题。它引入 **Project** 作为顶层组织实体，实现三个 CLI 工具的专属适配器，并把产品概念从“裸 CLI 好友”升级为 **Agent Profile = Engine + Skills + Context Policy**，最终打通从 Agent 输出到 Artifact Card 的完整链路。

当前进度：**6A Workspace Runtime、6B-6E CLI Adapter 与 6F Artifact Bridge 核心闭环均已落地**。已落地 Project-first 三栏 UI、Project CRUD、系统目录选择器、Session→Project workspace 查询、文件树、文件读取安全校验、snapshot/diff、静态 preview；同时已接入真实本机 Claude Code / Codex / OpenCode CLI 进程、CLI-only Agent 配置、Codex 官方/中转配置托管、执行轨迹块与 Agent 设置弹窗。6F 已在 CLI 消息完成后扫描回复、执行轨迹和 workspace diff，创建 `web_preview` / `file_tree` / `code_diff` / `document` Artifact，并接入消息下方的 MessageArtifactStrip/ArtifactCard 卡片流；同时补齐文件编辑器、代码片段引用、Artifact 版本管理、会话文件入口和三类 CLI Agent logo 头像。Phase 7F 已把群聊同步到同一产物链路：每个 Agent 子消息拥有独立 workspace snapshot，产物按 messageId/sourceId 绑定，不再只依赖文本扫描。

```text
创建 Project + 绑定 workspace 目录
  → 在 Project 下创建私聊/群聊 Session
  → 用户输入 / Orchestrator 子任务
  → 路由到 Agent Profile
  → 解析 Engine + Skill bindings + Context Policy
  → Engine Adapter: ClaudeCodeAdapter | CodexAdapter | OpenCodeAdapter
  → CLI Engine 以 Project.workspace_path 为 cwd 执行
  → stdout/stderr 语义解析 → 分层渲染（文本/进度/产物/交互）
  → 标准化事件 → Artifact Bridge 检测产物
  → artifact.created → 消息下方产物卡片
  → Phase 5 版本/Diff/编辑 → Phase 7 审批体验闭环
```

Phase 6 完成后，AgentHub 能明确回答：

- 代码被创建在哪里 → `Project.workspace_path` 下
- CLI Agent 的 cwd 是什么 → `Session → Project.workspace_path`
- 文件变更如何被捕获 → 执行前后 hash diff
- Agent 输出如何变成 Artifact → 消息完成后扫描回复/执行轨迹/workspace diff → artifact.detected → artifact.created → MessageArtifactStrip + ArtifactCard
- 群聊产物如何归属 → 每个 Agent 调用前创建 snapshot，finalizer 按 Agent 子消息触发 Artifact Bridge，产物绑定对应 messageId/sourceId

---

## 2. 子模块索引

| 模块 | Spec 文档 | 核心交付 |
|------|----------|---------|
| **6A: Workspace Runtime** | [00-workspace-runtime.md](00-workspace-runtime.md) | ✅ Project 实体 + workspace 目录管理 + 文件树/Diff/静态预览 + 路径安全 + 项目创建菜单 |
| **6B-6E: CLI Adapter** | [01-cli-adapter.md](01-cli-adapter.md) | ✅ ClaudeCodeAdapter / CodexAdapter / OpenCodeAdapter + subprocess 进程管理 + ANSI 清洗 + Codex 官方/中转配置 + 执行轨迹分层渲染 |
| **6F: Artifact Bridge** | [02-artifact-output-bridge.md](02-artifact-output-bridge.md) | ✅ CLI 消息完成后自动扫描回复、执行轨迹和 workspace diff，创建 Artifact，并接入消息下方产物卡片流 |
| **6G: Agent Profile** | [03-agent-engine-skill-profile.md](03-agent-engine-skill-profile.md) | ✅ Agent = Engine + Skills 建模、内置 Skill Registry、Prompt Assembly、Skill-based AgentSelector |
| **CLI Adapter 交付快照** | [../../deliverables/phase6-cli-adapter/README.md](../../deliverables/phase6-cli-adapter/README.md) | CLI Adapter 架构原理、使用指南、阶段开发日志 |
| **Artifact Bridge 交付快照** | [../../deliverables/phase6-artifact-bridge/README.md](../../deliverables/phase6-artifact-bridge/README.md) | 消息级 Artifact 卡片、文件编辑器、代码引用、版本管理与验收日志 |

---

## 3. 关键原则

| 原则 | 依据 |
|------|------|
| Project 是顶层组织实体，所有聊天必须归属 Project | ADR-0009 §核心规则 1 |
| 一个 Project 绑定一个 workspace 目录，Project 内所有 Session 共享 | ADR-0009 §核心规则 2-3 |
| CLI Wrapper 是 AgentHub 唯一的 Engine 执行模式；用户可见 Agent = Engine + Skills | ADR-0011 |
| 每个 CLI 工具单独适配（子类化 CliAgentAdapter） | ADR-0009 §配套决策 B |
| CLI 工具由用户在外部安装，AgentHub 只管理配置 | ADR-0009 §配套决策 A |
| stdout 语义分层解析：文本→消息、进度→状态条、产物→Card、交互→卡片 | ADR-0009 §配套决策 C |
| Adapter 不直接写业务表，只输出标准事件 | PRD-01 §3.4 |
| Orchestrator 不直接读写文件，只派发任务 | PRD-02 |

---

## 4. 跨模块事件流

```
用户发送消息
  → ChatService 路由到 Agent Profile
  → Prompt Assembly 注入 primary/auxiliary skills
  → Engine Adapter 启动 CLI 进程（cwd = Project.workspace_path）
  → stdout → StreamSanitizer → PromptInterceptor → 分层解析
  → SSE: agent.output (text) → 前端消息气泡
  → SSE: agent.output (progress) → 前端状态条
  → SSE: interactive_prompt → 前端确认卡片 → POST /interactive_reply → stdin 回写
  → agent.process.completed
  → ArtifactOutputBridge 扫描消息内容 + executionTrace + workspace diff
  → artifact.detected → ArtifactService → artifact.created
  → SSE: artifact.created → MessageArtifactStrip + ArtifactCard
```

---

## 5. 核心 API 总览

| 端点 | 方法 | 所属模块 | 说明 |
|------|------|---------|------|
| `/api/projects/pick-folder` | POST | 6A | 调起本机系统目录选择器，返回一次性 folderToken |
| `/api/projects` | POST/GET | 6A | 创建/列出 Project |
| `/api/projects/{id}` | GET/DELETE | 6A | Project 详情/归档 |
| `/api/projects/{id}/tree` | GET | 6A | 文件树 |
| `/api/projects/{id}/files?path=` | GET | 6A | 读取文件 |
| `/api/projects/{id}/diff` | GET | 6A | 文件变更 Diff |
| `/api/projects/{id}/preview` | POST | 6A | 启动预览 |
| `/api/projects/{id}/build` | POST | 6A | 启动构建 |
| `/api/sessions/{id}/workspace` | GET | 6A | 查询 Session 继承的 Project workspacePath |
| `/api/sessions/{id}/chat` | POST (SSE) | 6B-6E | 与 CLI Agent 对话 |
| `/api/sessions/{id}/interactive_reply` | POST | 6D | 确认/拒绝 CLI 交互提示 |
| `/api/sessions/{id}/artifacts` | GET | 6F | 会话产物列表（Phase 5 已有） |

---

## 6. 全量验收标准汇总

### Workspace Runtime（详见 [00-workspace-runtime.md](00-workspace-runtime.md) §6）

- ✅ AC-WS-01: 创建 Project → 目录被创建 + `.agenthub/project.json` 存在
- ✅ AC-WS-02: Session 继承 Project workspace，`/api/sessions/{id}/workspace` 返回同一路径
- ✅ AC-WS-03: 文件树返回相对路径，`../` 越界返回 403
- ✅ AC-WS-04: 静态 HTML 项目 → preview URL 可访问
- ✅ AC-WS-05: snapshot/diff 正确识别文件变更
- ✅ AC-WS-06: 创建按钮弹出 `新建空白文件夹` / `选择现有文件夹`，后者通过系统目录选择器授权，不要求用户手输路径
- ✅ AC-WS-07: 项目不再暴露 `静态网页 / Vite React / 已有项目` 这类用户可选属性；`project_type` 仅保留为兼容字段

### CLI Adapter（详见 [01-cli-adapter.md](01-cli-adapter.md) §6）

- AC-CLI-01: 好友列表预置三个 Agent，各自显示名称 + 头像 + 版本 + 状态
- AC-CLI-02: [+] 按钮 → 添加 Agent 弹窗 → 检测 executable → 绿色指示灯
- AC-CLI-03: Agent ⋮ → [发起对话] → 选 Project → 创建 Session → 进入聊天
- AC-CLI-04: 消息发送 → CLI 进程以 workspace_path 为 cwd 启动
- AC-CLI-05: stdout → 分层渲染（文本/进度/产物/交互）
- AC-CLI-06: ANSI 码完全清洗，前端无乱码
- AC-CLI-07: `(y/n)` → 确认卡片 → 用户响应 → stdin 回写
- AC-CLI-08: 三个 CLI 各自正确识别 diff 格式并发送 artifact_signal
- AC-CLI-09: 同一 Project 下两个私聊 → 两个独立 CLI 进程 → 互不影响
- AC-CLI-10: 超时/断连 → 进程自动终止 + 前端明确提示

### Agent Profile（详见 [03-agent-engine-skill-profile.md](03-agent-engine-skill-profile.md) §10）

- AC-PROFILE-01: `GET /api/agents` 返回 `primarySkill / auxiliarySkills / contextPolicy`
- AC-PROFILE-02: Agent 设置面板能配置 Engine、Primary Skill、Auxiliary Skills、Context Policy
- AC-PROFILE-03: Prompt Assembly 注入 primary skill 和 auxiliary skill prompt
- AC-PROFILE-04: AgentSelector 优先按 Skill 匹配，再 fallback 到 name/description/systemPrompt
- AC-PROFILE-05: 调度器被建模为 `orchestrator_planner` Skill 的特殊 Agent Profile，不再作为孤立概念

### Artifact Bridge（详见 [02-artifact-output-bridge.md](02-artifact-output-bridge.md) §6）

- ✅ AC-BR-01: CLI 写入 `index.html` → `web_preview` Artifact 在最终 `done` 前创建
- ✅ AC-BR-02: 完整 fenced `diff` 代码块 → `code_diff` Artifact
- ✅ AC-BR-03: workspace 多文件变更 → `file_tree` Artifact
- ✅ AC-BR-04: 代码块未闭合 → 不创建 Artifact，也不写候选
- ✅ AC-BR-05: 低置信度（0.50-0.79）→ 写入 message metadata 候选，不落库
- ✅ AC-BR-06: 同一 message 重复扫描 → 幂等，不重复创建 Artifact
- ✅ AC-BR-07: MessageArtifactStrip 只展示与当前 messageId 绑定的 Artifact，并在消息下方直接渲染完整卡片
- ✅ AC-BR-08: ArtifactCard/FileEditorModal 支持编辑文件、保存、选区添加到对话和 ChatInput 代码引用块
- ✅ AC-BR-09: ArtifactVersionManager 支持撤销本次修改与跳转历史版本
- ✅ AC-BR-10: Chat Header 文件按钮打开当前会话的文件、资产与变更管理界面
- ✅ AC-BR-11: 群聊 Agent 子消息可基于各自 workspace snapshot 生成 `workspace_diff` Artifact，并按 messageId/sourceId 归属

---

## 7. 测试策略总览

| 层级 | 条数 | 覆盖 |
|------|------|------|
| 单元测试 | ~90 条 | Workspace(已覆盖核心 API/组件) + CLI Adapter(50) + Artifact Bridge(18) |
| 集成测试 | 5 场景 | Project→Session→cwd、测试 CLI fixture→SSE、Diff→Artifact 全链路 |
| E2E | 4 场景 | 创建 Project→CLI Agent 执行→消息下方产物卡片→预览 |

6A 已有测试入口：

- `backend/test_api/test_projects_phase6.py`
- `frontend/src/components/ProjectSidebar.test.tsx`

---

## 8. 上下游总契约

| 方向 | 输入/输出 |
|------|----------|
| **上游输入** | Phase 3: SessionService、EventBus、BaseAgentAdapter；Phase 5: ArtifactService |
| **本阶段输出** | Project CRUD API、CLI Agent 执行引擎、Artifact 桥接服务、分层渲染事件流 |
| **下游消费** | Phase 5: Artifact 版本/Diff/编辑 API；Phase 7: 运行可控性、Approval Card、HealthCheck、MVP 演示脚本 |
| **未覆盖边界** | SaaS 云端 sandbox（→ P2）；公网部署（→ P2）；完整 Web IDE（不做）；多人实时协同编辑（不做） |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| CLI 工具版本差异导致解析失败 | Per-CLI 专属 Adapter 各自理解该 CLI 格式；Artifact Bridge 同时参考 executionTrace 与 workspace diff，避免只依赖单一 stdout 文本模式 |
| Windows 文件监听不稳定 | 使用执行前后 hash diff，不依赖常驻文件 watcher |
| CLI 进程长时间占用资源 | 三重超时：静默 5min → SIGKILL；断连 3min → SIGTERM；总时长 30min → SIGKILL |
| Workspace 概念影响普通聊天体验 | 所有聊天必须归属 Project；Project 创建流程在首次使用时引导，降低认知负担 |
| Artifact 与 workspace 双版本源冲突 | Artifact 记录 project_id/file_path/preview_id；workspace snapshot 作为文件系统版本边界 |

---

## 10. Phase 完成后全局影响

Phase 6 完成后：

- `sessions.workspace_id` 废弃，改用 `sessions.project_id`（→ Project.workspace_path）
- `agent_configs` 表新增 executable / init_args / env_vars 字段
- `artifacts` 表新增 project_id / file_path / source / confidence / task_id 字段
- AgentPanel 新增 CLI 包装器配置模式
- 前端新增 ProjectList 页面和 Project 工作区布局

6A 当前已完成 Project / workspace runtime / Project 工作区布局部分；6B-6E 已完成 CLI 进程管理、三类本机 CLI Agent 接入、Codex 配置托管与执行轨迹 UI；6F 已完成 Artifact 自动入口、幂等创建、低置信候选、手动重扫、消息下方产物卡片流、文件编辑器、代码片段引用、版本管理和会话文件入口。真实 Claude Code 服务路径已通过 `backend/test_real_api_claude_artifact_bridge.py` 验收：Claude Code 在临时 workspace 写入 `index.html`、`package.json`、`src/App.tsx`，最终 `done` 前创建 `web_preview`、`file_tree`、`code_diff` 三类 Artifact。2026-06-08 群聊真实服务验收已确认：临时群聊中两个 custom CLI Agent 各自写入 HTML 文件后，分别在各自 Agent 消息下生成 `workspace_diff` `web_preview/code_diff` Artifact。

> **版本历史**
> - v1.0 (2026-06-02): 初始版本
> - v2.0 (2026-06-04): 引入 Project 模型 + Per-CLI 适配 + 分层渲染
> - v3.0 (2026-06-04): 按新 Spec 模板全面重构，去 MVP 最小实现限制，全量覆盖
> - v3.1 (2026-06-04): 记录 Phase 6A 人工验收通过；同步项目创建菜单、系统目录选择器、去除用户可选 project type 的实现口径
> - v3.2 (2026-06-05): 同步 CLI Adapter 实现基线、Codex 官方/中转配置托管、执行轨迹 UI 与交付文档入口
> - v3.3 (2026-06-05): 同步 6F Artifact Bridge 新设计：消息完成后扫描回复/轨迹/workspace diff，接入 MessageArtifactStrip 与产物工作台；后续 P1 Artifact 体验已由 ADR-0010 收敛为消息级卡片
> - v3.4 (2026-06-05): 记录 6F 核心闭环完成与真实 Claude Code 验收：workspace diff/code block/manual rescan → ArtifactService → MessageArtifactStrip/ArtifactCard
> - v3.5 (2026-06-05): 同步 UI 决策：移除独立产物工作台，ArtifactCard 直接跟随消息展示；diff UI 收敛为 VS Code/GitHub 风格统一视图
> - v3.6 (2026-06-06): 同步文件编辑器、代码片段引用、Artifact 版本管理、会话文件入口、Agent 状态位置和三类 CLI Agent logo 头像
> - v3.7 (2026-06-06): 记录本轮验收通过，并新增 Phase 6F Artifact Bridge deliverables 快照
> - v3.8 (2026-06-06): 同步 ADR-0010 与新版 Phase 7：不再把 Drawer 作为 P1 后续，Phase 7 聚焦运行可控性、审批、环境体检与演示加固
> - v3.9 (2026-06-08): 同步群聊重构后的 Artifact 归属：每个 Agent 子消息基于独立 snapshot 扫描 workspace diff 并绑定产物
