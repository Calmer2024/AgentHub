# Phase 6: Workspace Runtime + CLI 适配器 + 产物入口桥接 📋 PLANNED

**关联 ADR**: [ADR-0008](../../adr/0008-revised-development-strategy.md) §6, [ADR-0009 Project-Workspace 模型](../../adr/0009-project-workspace-model.md)  
**关联 PRD**: [PRD-01: Architecture Adapter](../../PRD/01-Architecture_Adapter.md), [PRD-05: End-to-End Flow](../../PRD/05-End_to_End_Product_Flow.md), [PRD-06: MVP Local Workspace](../../PRD/06-MVP_Local_Workspace_Delivery.md)  
**依赖**: Phase 3 (BaseAgentAdapter / EventBus), Phase 5 (ArtifactService)  
**状态**: 计划中

---

## 1. 全局定位

Phase 5 已完成”已有 Artifact 的工作台能力”。Phase 6 的任务是补上它的上游执行底座，并引入 **Project** 作为顶层组织实体（详见 [ADR-0009](../../adr/0009-project-workspace-model.md)）：

```text
创建 Project + 绑定 workspace 目录
  -> 在 Project 下创建私聊/群聊 Session
  -> 用户输入 / Orchestrator 子任务
  -> CLI Agent 以 Project.workspace_path 为 cwd 执行
  -> stdout/stderr 语义解析 → 分层渲染（文本/进度/产物/交互）
  -> artifact.detected / artifact.created
  -> 聊天流出现 Artifact Card
```

Phase 6 完成后，AgentHub 不再只是“聊天里生成一段文本”。它必须能明确回答：

- 代码被创建在哪里。
- CLI Agent 的 `cwd` 是什么。
- 文件变更如何被捕获。
- Agent 输出如何变成可预览、可编辑、可版本化的 Artifact。

---

## 2. 板块目标

Phase 6 作为 Phase 5 之后的合理下一阶段，分三层补齐端到端执行链路：

1. **Project + Workspace Runtime**：引入 Project 实体，绑定 workspace 目录；Project 下所有 Session 共享此目录。提供文件树、Diff、预览、snapshot 等基础能力。
2. **CLI Agent Adapter**：每个 CLI 工具单独适配（`ClaudeCodeAdapter`、`CodexAdapter`、`OpenCodeAdapter`），通过 PTY/subprocess 管理进程，对 stdout 做语义分层解析（文本→消息、进度→状态条、Diff/代码块→Artifact Card、交互提示→确认卡片）。
3. **Artifact Output Bridge**：将 CLI Agent 输出和 workspace 文件变更转换为标准 Artifact 事件。

**关键原则**：

- Project 是顶层组织实体，所有聊天必须属于某个 Project。不存在"无 Project 的聊天"。
- CLI 工具由用户在外部安装（`npm install -g` 等），AgentHub 只管理配置（executable、init_args、env vars）。
- CLI Wrapper 是 AgentHub 唯一的 Agent 执行模式。所有 Agent 必须通过 PTY/subprocess 管理，以 Project.workspace_path 为 cwd 执行。
- Orchestrator 不直接读写文件；它只派发任务并引用 workspace / artifact 上下文。
- Adapter 不直接写业务表，只输出标准事件；WorkspaceService 和 ArtifactService 负责落库。

---

## 3. 子模块

### Module 6A: Workspace Runtime

| 维度 | 内容 |
|------|------|
| **Spec** | [00-workspace-runtime.md](00-workspace-runtime.md) |
| **后端** | `backend/app/models/workspace.py`, `backend/app/services/workspace_service.py`, `backend/app/infrastructure/local_workspace_provider.py`, `backend/app/api/workspaces.py` |
| **数据库** | `projects` 表（新增）+ `sessions.project_id`；`artifacts.project_id/file_path/preview_id` |
| **职责** | 创建/绑定本机 workspace、路径安全、文件树、Diff、snapshot、静态预览、为 CLI 提供可信 `cwd` |

### Module 6B: CLI Process Manager

| 维度 | 内容 |
|------|------|
| **Spec** | [01-cli-adapter.md](01-cli-adapter.md) §4 |
| **后端** | `backend/app/infrastructure/cli_process_manager.py` |
| **职责** | PTY/subprocess 进程孵化、使用 `workspace_path` 作为 CWD、环境变量隔离、心跳超时、SIGTERM/SIGKILL |

### Module 6C: Stream Sanitizer (ANSI 清洗)

| 维度 | 内容 |
|------|------|
| **Spec** | [01-cli-adapter.md](01-cli-adapter.md) §5 |
| **后端** | `backend/app/infrastructure/stream_sanitizer.py` |
| **职责** | ANSI 转义码过滤、分块 SSE 推送、TUI 组件降级渲染 |

### Module 6D: Interactive Prompt Interception

| 维度 | 内容 |
|------|------|
| **Spec** | [01-cli-adapter.md](01-cli-adapter.md) §6 |
| **后端** | `backend/app/infrastructure/prompt_interceptor.py` |
| **前端** | `InteractivePromptCard.tsx` |
| **职责** | 阻塞特征匹配 → 暂停推流 → 前端确认卡片 → stdin 回写 |

### Module 6E: CLI Agent Adapter

| 维度 | 内容 |
|------|------|
| **Spec** | [01-cli-adapter.md](01-cli-adapter.md) §7（基类）+ §8（Per-CLI 接入方案） |
| **后端** | `backend/app/agents/cli_adapter.py`（基类）、`claude_code_adapter.py`、`codex_adapter.py`、`opencode_adapter.py`（子类） |
| **职责** | 基类整合 Process/Sanitizer/Interceptor；三个子类各自实现 CLI 专属的输出解析、交互匹配、产物检测；在 AgentPanel 中选择 CLI 工具类型并配置 executable/init_args/env vars |

### Module 6F: Artifact Output Bridge

| 维度 | 内容 |
|------|------|
| **Spec** | [02-artifact-output-bridge.md](02-artifact-output-bridge.md) |
| **后端** | `backend/app/services/artifact_detection_service.py` 或 ArtifactService 扩展 |
| **职责** | 将 CLI/API Agent 输出中的代码块、patch、workspace 文件变更摘要转换为 `artifact.detected`，再由 ArtifactService 创建 Artifact 与 Artifact Card |

---

## 4. 验收标准

### Workspace Runtime

- [ ] **6A-1**: 新建 Project 时绑定 workspace 目录，记录 `projects.workspace_path`。Project 下创建 Session 时自动继承 workspace。
- [ ] **6A-2**: `GET /api/projects/{id}/tree` 返回 workspace 内相对文件树。
- [ ] **6A-3**: 任何 `../` 越界读取、写入、预览请求都会被拒绝（基于 Project.workspace_path 边界校验）。
- [ ] **6A-4**: Agent 执行前后 hash diff 能识别 created/modified/deleted 文件。
- [ ] **6A-5**: 静态 HTML workspace 能生成 `previewId`，并通过后端 preview URL 打开。
- [ ] **6A-6**: Artifact 可绑定 `project_id/file_path/preview_id`。

### CLI Adapter

- [ ] **6B-1**: AgentConfig 中 `agent_type='cli_wrapper'`，配置 `executable` + `init_args` → 启动对应 CLI 进程。
- [ ] **6B-2**: CLI 进程启动时的 `cwd` 必须等于当前 Session 所属 Project 的 `workspace_path`。
- [ ] **6B-3**: 进程 stdout → 语义分层解析（文本/进度/产物/交互）→ 实时推流到前端（延迟 < 100ms）。
- [ ] **6B-4**: 用户关闭网页 → 3 分钟后进程收到 SIGTERM → 进程正常退出。
- [ ] **6B-5**: stdout 静默超过 5 分钟 → 判定死锁 → SIGKILL → 前端显示”进程已超时”。
- [ ] **6C-1**: ANSI 颜色码 `\x1b[31mError\x1b[0m` → 前端收到 `Error`。
- [ ] **6D-1**: CLI 输出 `Do you want to run this? (y/n)` → 前端弹出交互卡片。
- [ ] **6D-2**: 用户点击同意/拒绝 → stdin 写入 `y\n` / `n\n` → 进程继续。
- [ ] **6E-1**: 每个 CLI 工具单独适配：`ClaudeCodeAdapter`、`CodexAdapter`、`OpenCodeAdapter`，各自理解该 CLI 的特定输出格式。
- [ ] **6E-2**: AgentPanel 可配置 executable 路径、init_args、env vars（CLI 工具由用户在外部安装）。
- [ ] **6E-3**: 分层渲染：spinner/进度 → 状态条；文本 → 消息气泡；Diff/代码块 → Artifact Card；交互提示 → 确认卡片。

### Artifact Bridge

- [ ] **6F-1**: CLI/API Agent 输出 HTML/TSX/patch 代码块 → 触发 `artifact.detected`。
- [ ] **6F-2**: workspace 文件变更摘要 → 能创建 `file_tree` 或 `code_diff` Artifact。
- [ ] **6F-3**: Artifact 创建后聊天流追加 Artifact Card，绑定 `artifact_id/message_id/task_id/version/workspace_id`。
- [ ] **6F-4**: Orchestrator 子任务带 `expected_outputs` 时，任务完成前能关联至少一个 Artifact 或明确失败原因。
- [ ] **6F-5**: 创建出的 Artifact 可直接进入 Phase 5 versions/diff/edit API。

---

## 5. 上下游契约

| 方向 | 契约 |
|------|------|
| 上游输入 | 用户创建 Project（绑定 workspace_path）、Project 下创建 Session、用户聊天消息、Orchestrator 子任务、AgentConfig(cli_wrapper) |
| 本阶段输出 | `project.created`、`workspace.diff_ready`、`agent.output`、`interactive_prompt`、`artifact.detected`、`artifact.created` |
| 下游消费 | Phase 5 Artifact 版本/Diff/编辑；Phase 7 Artifact Drawer、Preview、Approval Card |
| 未覆盖边界 | SaaS 云端 sandbox、公网部署、完整 Web IDE、多人实时协同编辑 |

---

## 6. 接口契约

### Project + Workspace API

```text
# Projects
POST /api/projects                   创建 Project（命名 + 选择/创建 workspace 目录）
GET  /api/projects                   列出用户的所有 Project
GET  /api/projects/{project_id}      获取 Project 详情（含 workspace_path）

# Workspace（从属于 Project）
GET  /api/projects/{project_id}/tree        文件树
GET  /api/projects/{project_id}/files?path= 文件内容
GET  /api/projects/{project_id}/diff        文件变更 Diff
POST /api/workspaces/{workspace_id}/snapshot
POST /api/workspaces/{workspace_id}/preview
POST /api/sessions/{session_id}/workspace
```

### CLI Interactive API

```text
POST /api/sessions/{id}/interactive_reply
Body: { "process_id": "...", "reply": "y" }
-> 200 { "status": "acknowledged" }
```

### 新增 SSE / WebSocket 事件

```json
{"type": "workspace.created", "workspaceId": "...", "sessionId": "..."}
{"type": "workspace.diff_ready", "workspaceId": "...", "changedFiles": 3}
{"type": "interactive_prompt", "content": "Do you want to run this? (y/n)", "processId": "..."}
{"type": "artifact.created", "artifactId": "...", "messageId": "...", "taskId": "...", "version": 1}
```

---

## 7. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Workspace 概念引入后影响普通聊天 | 普通聊天 session 可不绑定 workspace；只有项目型 session 强制绑定 |
| 本机路径越界 | 所有路径使用 `resolve()` 校验，前端不直接持有本机路径 |
| Windows 文件监听不稳定 | MVP 使用执行前后 hash diff，不依赖常驻 watcher |
| CLI 工具版本差异导致解析失败 | 阻塞特征和 Artifact 检测用正则 + expected_outputs 辅助 |
| CLI 长时间占用资源 | 心跳超时、静默超时、总执行时间上限 |
| Artifact 与 workspace 双版本源冲突 | Artifact 记录 `workspace_id/file_path/preview_id`，workspace snapshot 作为文件系统版本边界 |

