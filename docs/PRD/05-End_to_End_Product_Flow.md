# 需求规格说明书 (PRD)：05 - 端到端产品闭环与需求追踪

**创建日期**: 2026-06-03  
**状态**: Active  
**来源**: 启动文档覆盖审计与 Phase 5 后复盘

## 1. 文档定位

本文档补齐 AgentHub 的全局产品链路。它回答三个问题：

1. 启动文档中的要求是否在 PRD 中有明确位置。
2. 用户从发起任务到拿到产物，中间经过哪些产品状态。
3. 每个 Phase 在全局链路中解锁什么能力、不能宣称完成什么能力。
4. Session、Workspace、Agent 执行目录、Artifact、预览和部署之间的关系是什么。

本文是 [00-Master_Hub.md](./00-Master_Hub.md) 的闭环补充，优先级高于各 Phase 的局部实现描述。Workspace 形态的权威落地说明见 [PRD-06 MVP 本机 Workspace](./06-MVP_Local_Workspace_Delivery.md) 与 [PRD-07 SaaS 云端 Workspace](./07-SaaS_Cloud_Workspace_Delivery.md)。

---

## 2. 启动文档需求追踪矩阵

| 启动文档要求 | MVP 定位 | 权威 PRD | Spec / Phase |
|---|---:|---|---|
| IM 会话列表：新建、最近活跃、搜索、置顶、归档箱、未读数、免打扰 | P0/P1 | PRD-03, PRD-04 | Phase 1, Phase 4, Phase 7D |
| 单聊模式 | P0 | PRD-03, PRD-04 | Phase 1 |
| 群聊模式、@ Agent、Orchestrator 自动分派 | P0 | PRD-02, PRD-03, PRD-04 | Phase 2, Phase 3 |
| 上下文连续、历史消息、Pin 长期上下文 | P0 | PRD-02, PRD-04 | Phase 1, Phase 4 |
| 消息类型：文本、代码块、网页预览、Diff 卡片 | P0 | PRD-03, PRD-04 | Phase 1, Phase 2, Phase 5, Phase 7 |
| 图片、文件附件 | P2 | 本文 §8 | 暂不进入 MVP |
| 消息操作：回复、引用、重新生成、复制、转发、多选、展开预览 | P0/P1 | PRD-03, PRD-04 | Phase 4, Phase 7D |
| 一键应用 Diff、版本历史、局部修改 | P0 | PRD-03, PRD-04 | Phase 5 |
| 本机 Project/workspace 创建绑定、Agent cwd、文件变更入 Artifact | P0 | PRD-06 | Phase 6A 已完成 workspace runtime；Phase 6B-6F/Phase 7 补齐执行与 UI |
| 主 Agent 协调器：拆解、并行、失败降级、冲突处理 | P0/P1 | PRD-02 | Phase 3, Phase 7 |
| 多 Agent 接入：至少 2 个主流平台 | P0 | PRD-01, PRD-04 | Phase 2, Phase 6 |
| 用户自建 Agent：名称、头像、能力标签、prompt、工具集 | P1 | PRD-03, PRD-04 | Phase 2 已有配置式创建；对话式创建为后续增强 |
| Agent 产物内联：代码、网页、文档、PPT | P0/P2 | PRD-03, PRD-04 | Phase 2, Phase 5, Phase 7；PPT 为 P2 |
| 实时预览、代码二次编辑 | P0 | PRD-03, PRD-04 | Phase 5, Phase 7 |
| 本机预览、源码下载、构建产物导出 | P0/P1 | PRD-06 | Phase 6 Workspace Runtime + Phase 7 UX |
| 一键公网部署发布 | P1/P2 | PRD-06, PRD-07, 本文 §8 | MVP 可通过 DeployAdapter 扩展；SaaS 版作为核心能力 |
| SaaS 云端 workspace、多租户 sandbox、云端 preview URL | P2 | PRD-07 | MVP 后商业化路线 |
| Web 端完整体验 | P0 | PRD-03 | Phase 1-7 |
| 桌面端、移动端 | P2 | 本文 §8 | 暂不进入 MVP |
| AI 协作交付物：Spec、Skill、Rules、开发记录 | P0 | PRD-00, 本文 | docs/specs, CLAUDE.md, dev-logs |

---

## 3. 北极星演示闭环

MVP 的最终演示必须跑通以下完整链路：

```text
用户创建 Project（选择/新建 workspace 目录）
  -> Project 记录 workspace_path
  -> 在 Project 下创建私聊/群聊 Session
  -> 输入自然语言任务
  -> Orchestrator 判断单聊/群聊/复杂 DAG
  -> 选择 CLI Agent 执行
  -> Agent 以 Project.workspace_path 作为 cwd 读写文件
  -> Agent 流式输出文字、任务状态、Artifact 事件
  -> Adapter 分层解析 + File Change / Output Bridge 检测文件变更、HTML、Diff、构建产物
  -> ArtifactService 统一创建产物版本
  -> 聊天流出现 Artifact Card
  -> 用户打开页面级 Artifact 预览/编辑弹窗查看网页或 Diff
  -> 用户引用产物或选中代码片段发起修改
  -> Agent 基于同一个 workspace 生成编辑 Diff 或直接修改文件
  -> 用户确认后创建新版本
  -> 如任务需要审批，Approval Card 暂停流水线
  -> 用户确认后 Orchestrator 继续下游任务
  -> 中枢总结输出最终交付说明
```

MVP 本机版的运行位置是：

```text
本机浏览器
  -> 本机后端
  -> 本机 CLI Agent
  -> 本机 workspace_path
  -> 本机预览 / 构建 / 导出 / 可选上传部署
```

SaaS 版的运行位置是：

```text
用户浏览器
  -> 云端后端
  -> 云端 sandbox / runner
  -> 云端 workspace
  -> 云端预览 / 云端部署
```

任何 Phase 的验收都必须说明自己打通了这条链路中的哪一段，未打通哪一段。

---

## 4. Artifact 生成与回流规则

Artifact 不是独立工作台，它必须是聊天与 Agent 输出链路的一等公民。

### 4.1 产物来源

系统允许三类产物来源：

| 来源 | 说明 | MVP 要求 |
|---|---|---|
| Agent 输出检测 | API/CLI Agent 输出包含代码块、HTML、patch、文件清单等结构 | 必须支持 |
| Orchestrator 任务结果 | 子任务完成后提交 `artifact.created` 事件 | 必须支持 |
| 用户手动创建/编辑 | 用户在现有 Artifact 上局部编辑并确认 | Phase 5 已支持 |

### 4.2 产物创建边界

Agent Adapter 不直接写数据库。它只输出标准事件：

```json
{
  "type": "artifact.detected",
  "session_id": "session-id",
  "message_id": "message-id",
  "task_id": "task-id-or-null",
  "artifact_type": "code_diff|web_preview|document|file_tree",
  "title": "LoginPage_v1",
  "content": "...",
  "source": "api_agent|cli_agent|orchestrator"
}
```

`ArtifactService` 负责：
- 解析事件并创建 Artifact。
- 建立 `message_id`、`task_id`、`parent_artifact_id`、`version` 关系。
- 发布 `artifact.created` / `artifact.version_created` 事件。
- 让聊天流追加 `content_type='artifact_card'` 的系统消息或 Agent 消息附件。

### 4.3 产物回流到聊天

用户在页面级 Artifact 预览/编辑弹窗中看到产物后，有两种回流方式：

| 用户动作 | 系统行为 |
|---|---|
| 点击“引用此版本”后发送自然语言 | 当前消息携带 `referenced_artifact_id` 与 `version`，ContextManager 注入产物摘要 |
| 选中代码片段并描述修改 | 调用 Phase 5 `POST /api/artifacts/{id}/edit`，生成 Diff 预览；确认后创建新版本 |

---

## 5. Phase 定位与可完成任务

| Phase | 全局定位 | 完成后能做什么 | 不能宣称完成什么 |
|---|---|---|---|
| Phase 1 | IM 单聊骨架 | 单 Agent 流式聊天、历史持久化 | 多 Agent、产物、搜索 |
| Phase 2 | 多 Agent 与产物基础 | 创建群聊、@ Agent、基础 Artifact 卡片 | 深度调度、版本、真实 CLI |
| Phase 3 | Orchestrator 与协作基础设施 | 自动选 Agent、任务拆解、DAG/chain 协作、协作面板 | Artifact 完整工作台、真实 CLI |
| Phase 4 | 消息交互闭环 | Reply、Regenerate、Pin、全文搜索，并让引用/Pin 进入 Agent 上下文 | Artifact 预览抽屉、部署 |
| Phase 5 | Artifact 工作台能力 | 对已有 Artifact 做版本链、Diff、局部编辑、确认/拒绝 | 不代表 Agent 输出入口已经完整打通 |
| Phase 6 | Workspace Runtime + CLI Agent 适配器 | 6A 已引入 Project 实体 + 绑定 workspace，并通过系统目录选择器支持已有目录；6B-6E 实现 Claude Code / Codex / OpenCode 三个 CLI 的专属适配器（PTY 管理 + 分层渲染 + 交互拦截）；6F 让 CLI 输出和文件变更进入标准事件 → Artifact Card | 6A 不代表 CLI/Artifact Bridge 已完成；Phase 6 不负责最终 UI 打磨（审批卡片、运行控制、环境体检、IM 基线→Phase 7）；不做 SaaS sandbox（→P2） |
| Phase 7 | 用户体验与演示闭环 | 运行控制、审批卡片、环境体检、IM 会话基线、消息级 Artifact 页面级预览/编辑、端到端演示 | 不新增部署、多端等 P2 能力；真实 cc 自动化脚本仍需单独验收 |

---

## 6. MVP 完成定义

MVP 完成不是“所有模块都写完”，而是必须通过以下验收：

- 每个可执行会话都必须归属一个 Project，并通过 `sessions.project_id` 继承 `Project.workspace_path`。
- CLI Agent 执行时必须以 `Project.workspace_path` 作为 `cwd`；API Agent 生成的文件也必须写入同一 workspace。
- Agent 输出、文件变更、构建产物必须能回流为标准 Artifact 事件。
- 单聊与群聊均可从用户消息进入 Agent 执行链路。
- Orchestrator 对复杂任务能展示拆解、状态变化和中枢总结。
- 至少一个 Agent 输出能自动生成 Artifact Card。
- Artifact Card 能打开页面级预览/编辑弹窗，展示代码 Diff 或网页预览。
- 用户能基于该 Artifact 发起局部修改，并确认创建新版本。
- 用户能在本机预览 workspace 产物，并导出源码或构建产物。
- 需要人工审批的任务能暂停、展示 Approval Card、确认后继续。
- 环境体检能提示关键运行条件，如 API Key、CLI 工具、Node/Python。
- docs/specs/dev-logs 能解释每个 Phase 的设计、实现、验收与剩余边界。

---

## 7. 文档覆盖规则

后续任何 PRD 或 Spec 修改必须满足：

1. 每个需求都能从启动文档或后续明确决策追溯到 PRD。
2. 每个 PRD 需求都必须有 Spec 阶段归属，哪怕归属为 P2 / Non-MVP。
3. 每个 Phase README 必须包含“全局定位、已解锁任务、上下游契约、未覆盖边界”。
4. 每个 Artifact 相关 Spec 必须说明产物入口、存储、聊天卡片、页面级预览、编辑回流的关系。

---

## 8. P2 Roadmap

以下能力来自启动文档，但不进入当前 MVP：

| 能力 | 价值 | 放入 P2 的原因 | 最小设计方向 |
|---|---|---|---|
| 公网部署发布 | 让网页/代码产物变成可访问交付物 | 需要构建、Token、第三方平台与部署安全边界 | MVP 可用 DeployAdapter 上传本机 `dist/`；SaaS 版见 PRD-07 |
| SaaS 云端 workspace | 让用户无需本机安装后端/CLI 也能使用 AgentHub | 需要多租户隔离、sandbox、配额、Secret 管理 | Project + Cloud Workspace + Sandbox Runner + Preview/Deploy Service |
| 文件附件与图片输入 | 支持更真实的 IM 协作 | 需要存储、上传安全、上下文压缩 | AttachmentService + message attachment metadata |
| PPT 浏览 | 覆盖更多产物类型 | 当前课题主要演示代码/网页 | Artifact type 增加 `presentation` |
| 对话式自建 Agent | 降低 Agent 创建门槛 | 现有 AgentPanel 已能覆盖配置式创建 | Orchestrator 引导收集 name/prompt/tools |
| 桌面端 | 本地文件和进程管理更自然 | 需要 Tauri/Electron 安全策略 | 复用 Web UI + 本地 Agent runtime |
| 移动端 | 轻量审批和查看 | 需响应式与权限简化 | 只保留会话查看、审批、产物预览 |
