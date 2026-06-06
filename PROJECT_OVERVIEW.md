# AgentHub 项目全景

> 这是一份给人看的文档。不是给 AI 看的 Spec，不是 ADR，就是一个普通开发者接手项目时需要知道的一切。

---

## 这个项目要做什么？

一句话：**做一个 AI 版的 Slack**。

用户打开网页，像用微信/飞书一样，创建对话、发消息。对话的对象不是人，是 AI Agent。Agent 是后端封装的真实 CLI 工具实例，例如 Anthropic 官方 `claude` CLI、开源 `opencode` 等。AgentHub 不做简单的 HTTP LLM API 调用——那已经被 PRD-00/01 明确否决。核心玩法：

- **单聊**：选一个 Agent，1v1 对话
- **群聊**：拉多个 Agent 进同一个群，用 @ 指定谁来回，或者让 Orchestrator（协调器）自动分配任务
- **产物预览**：Agent 回复不只是文字，还能生成代码、网页等富媒体内容，直接在聊天里预览

这是一个**毕业设计/课题项目**，考察重点：AI 协作能力(30%) > 功能完整度(25%) > 生成效果(20%) > 代码理解(15%) > 创新(10%)。

### 产品交付阶段

项目分两步走：

| 阶段 | 产品形态 | 架构 | 一键部署 |
|------|---------|------|---------|
| **P1（当前）** | **桌面版**：桌面端（Tauri/Node.js）= 本地无头服务器 + 本地特权执行引擎；Web 端（浏览器）= 主力 UI | 浏览器 → localhost 后端 → 本机文件系统 + 本机 CLI Agent | ❌ |
| **P2（远期）** | **SaaS 云版**：Web 浏览器 + 云端后端 + 云端容器沙箱 | 浏览器 → 云端后端 → 云端沙箱 + 云端 CLI Agent → 部署到云端 URL | ✅ |

**P1 为什么不能一键部署？** CLI Agent 进程直接在用户本机运行，读写本地文件系统。没有远程服务器可"部署"到。一键部署是 P2 云版（有沙箱环境）才具备的能力。

---

## 技术栈

```
前端：React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui + Zustand
后端：Python FastAPI + SQLAlchemy 2.0 (async) + SQLite
通信：SSE（流式推送） + WebSocket（实时双向）
AI  ：CLI Wrapper 模式（PTY/subprocess 管理 claude / codex / opencode 等真实 CLI 工具）+ DeepSeek 后端内部系统模型能力
```

前后端分离，后端是 API 服务器，前端是 SPA。SQLite 是文件数据库，不需要装额外的数据库服务。

---

## 项目结构速览

```
AgentHub/
├── backend/                    ← Python 后端
│   └── app/
│       ├── main.py             ← 入口
│       ├── api/                ← 路由层（HTTP 接口）
│       ├── services/           ← 业务逻辑层
│       ├── domain/             ← 纯逻辑层（Orchestrator、ContextManager）
│       ├── agents/             ← CLI 适配器
│       ├── system_models/      ← DeepSeek 内部系统模型适配器
│       ├── event_bus/          ← 事件总线（解耦消息通知）
│       ├── models/             ← 数据库表定义
│       └── migrations/         ← 数据库迁移脚本
│
├── frontend/                   ← React 前端
│   └── src/
│       ├── App.tsx             ← 主页面
│       ├── components/         ← UI 组件
│       ├── stores/             ← 状态管理（Zustand）
│       ├── api/                ← 后端通信（REST + SSE + WebSocket）
│       └── types/              ← TypeScript 类型
│
├── docs/                       ← 文档（后面细说）
├── e2e/                        ← 端到端测试
└── .agents/skills/             ← AI 工作流 Skill（.claude/skills 保留镜像）
```

---

## 已经做完了什么？

项目按 Phase 1-7 推进，目前 Phase 1-6 核心闭环已完成并通过验收；Phase 7A-7C 的运行任务可控性、审批卡片和环境体检也已通过验收；Phase 7D 的 IM 会话基线、明亮主题和 v1.0 UI 加固已实现，继续补真实 Claude Code E2E 演示脚本与完整回归矩阵。

### Phase 1：单聊全链路 ✅

最薄的可运行版本：用户发消息 → 后端调 Claude API → 流式返回 → 前端逐字显示 → 存到 SQLite。

- 前端：会话列表 + 聊天窗口 + 输入框 + SSE 流式渲染
- 后端：Session CRUD + Chat SSE 端点 + Claude/DeepSeek 适配器
- 数据库：Session + Message 两张表
- 测试：28 条

### Phase 2：多 Agent + 群聊 + Orchestrator ✅

从"单人单 AI"升级到"多人多 AI 协作"。

- 多 Agent 支持：历史版本曾用 6 家 HTTP 厂商适配器；当前已迁移为 CLI Agent 好友模型
- Agent 管理：CRUD API + 前端 AgentPanel 配置界面
- 群聊模式：Session 支持 single/group 两种模式，SessionMember 多对多关联
- Orchestrator V1：消息路由 + 多 Agent 并发协调
- WebSocket：实时双向通信（心跳 + 重连 + 广播）
- 产物预览：Artifact 模型 + 前端渲染
- 前端重构：三 Tab 布局（聊天/Agent/设置）+ Markdown 渲染 + @提及补全
- 测试：72 条后端 + 7 条前端

### Phase 3：Orchestrator + 基础设施 ✅

Phase 3 聚焦多 Agent 协作基础设施与 Orchestrator 深化。

| 模块 | 内容 | 状态 |
|------|------|------|
| M1 | 基础设施（EventBus + DB 迁移 + Service ABC） | ✅ 完成 |
| M4 | Orchestrator 核心（意图分析 + Agent 选择 + 任务拆解 + 执行引擎） | ✅ 完成 |
| M5 | 链式协作（A 产出 → B Review） | ✅ 合并进 M4 |

### Phase 4：消息交互闭环 ✅

用户在聊天里能做的事：

- **引用回复**：hover 消息 → 点"引用" → 输入框上方出现引用卡片 → 发送后气泡显示引用预览；真实 `/chat` 请求携带 `parentMessageId`，后端保存引用快照并注入 Agent Prompt
- **重新生成**：hover AI 消息 → 点"重新生成" → 后端用相同上下文重新调用 Agent → 原地流式替换旧内容，并可查看原版
- **Pin 消息**：hover 消息 → 点"Pin" → Pin 标记 → 后续单聊/群聊上下文中优先注入
- **消息搜索**：`Ctrl+K` 打开搜索 → 中文关键词高亮 → 点击结果跳转原消息

人工验收已通过：真实 UI 中引用 4 天 3 夜攻略并要求改成一周，Agent 最终回复能复述只存在于被引用消息里的唯一代号，证明引用内容已进入 Agent 输入链路。

---

### Phase 5：产物工作台能力 ✅

- **版本链**：确认编辑或重新生成产物时创建新 Artifact 版本，`version += 1`，`parent_artifact_id` 指向前版。
- **Diff 对比**：任意两个版本可生成 Diff，前端支持 split（左右）和 unified（上下）两种视图。
- **在线编辑**：用户在代码产物中选中片段，输入修改意图，先生成 Diff 预览；确认后创建新版本，拒绝则保持原版不变。
- **工具调用/降级**：OpenAI/DeepSeek 走真实 `edit_artifact` tool calling；不支持工具调用的 Agent 自动降级为上下文注入。
- **架构收拢**：新增 `ArtifactEditor` Domain 纯逻辑 + `ArtifactService` 业务层，接入 EventBus，不把业务堆在 API handler。

真实 HTTP 验收已通过：临时启动后端，创建真实会话/消息/产物，完成编辑预览、确认创建 v2、版本链追溯、Diff 校验和会话产物链头刷新。

需要注意：Phase 5 完成的是“已有 Artifact 的工作台能力”，不是完整产物链路。Phase 6 已补齐 Project-first workspace runtime、真实 CLI Agent 执行和 Artifact Bridge：Project 绑定本机目录，Session 继承 `Project.workspace_path`，Agent 文件变更会自动生成消息下方 Artifact Card，并可继续进入文件编辑器、代码引用和版本管理。当前 P1 产品路线不再做右侧 Drawer，消息级 Artifact 体验以 ADR-0010 为准；审批卡片绑定产物、运行可控性和环境体检留给 Phase 7。

---

## 接下来要做什么？（v1.0 收尾）

### Phase 6：Workspace Runtime + CLI Agent 适配器 + 产物入口桥接 ✅

- Project 实体、创建项目菜单、系统目录选择器授权、workspace 文件树/Diff/静态预览、Session→workspace 查询已完成。
- Claude Code、Codex、OpenCode 真实 CLI Agent 以 `Project.workspace_path` 为 cwd 执行，并通过 SSE 展示文本和执行轨迹。
- CLI 输出、消息代码块和 workspace diff 已由 ArtifactOutputBridge 转为真实 Artifact，并在对应消息下方以 ArtifactCard 展示。
- 文件编辑器、代码片段引用、Artifact 版本管理和会话文件入口已通过本轮验收。

### Phase 7：任务可控性 + 审批 + 环境体检 + IM 体验 + 演示闭环 🚧

- ✅ 运行任务可控性：run/task/process 状态持久化、取消真实 CLI 进程、停止后明确提示并解锁输入框。
- ✅ Human-in-the-loop 审批卡片：确认继续、驳回并携带 Artifact/代码引用回到 ChatInput。
- ✅ 统一环境体检：CLI、Node/Python、workspace、DeepSeek 系统模型、活跃进程状态，发送前可阻断不可执行环境。
- ✅ IM 基线与 UI 加固：会话搜索、置顶、归档箱、未读数、免打扰、转发、多选、消息右键菜单、明亮主题纯白辅色、执行过程全屏。
- 🚧 v1.0 收尾：跑通 workspace 绑定 → 输入任务 → Agent 输出消息级 Artifact → 编辑/引用/版本管理 → 审批继续 → 中枢总结的真实 cc 演示脚本，并补截图审计。

---

## 架构是怎样的？

分层依赖（只能向下，不能向上）：

```
前端 (React)
  ↓
API 路由层 (FastAPI)
  ↓
业务逻辑层 (Service)
  ↓
纯逻辑层 (Domain)        ← Orchestrator、ContextManager 在这里
  ↓
基础设施层 (EventBus、Agent 适配器)
  ↓
数据层 (SQLAlchemy ORM + SQLite)
```

关键设计决策：

- **Agent 适配器模式**：CLI Wrapper 通过统一 CLI 事件契约封装真实 CLI 工具（Claude Code、Codex、OpenCode 等），通过 PTY/subprocess 管理进程、ANSI 清洗、交互拦截。新增工具只需实现一个适配器
- **EventBus 解耦**：Agent 流式输出 → EventBus 广播 → WebSocket 推送 / 持久化 / 产物检测，各模块不直接依赖
- **Orchestrator 四阶段流水线**：意图分析 → Agent 选择 → 任务拆解 → 执行调度，每个阶段独立可测试
- **SQLite + FTS5**：零配置数据库，内置全文搜索，课题项目够用

---

## 数据库有哪些表？

| 表 | 用途 |
|----|------|
| `projects` | 项目（顶层组织实体，绑定 workspace_path） |
| `sessions` | 会话（single/group 模式，归属某个 Project） |
| `messages` | 消息（支持 parent_message_id 引用、is_pinned 标记） |
| `session_members` | 群聊成员关联表 |
| `agent_configs` | CLI Agent 配置（名称、备注、executable、init_args、非敏感 env vars） |
| `artifacts` | 产物（代码、网页预览等，支持版本链） |
| `runs` | Phase 7 运行记录（单聊/群聊一次执行的状态） |
| `run_tasks` | Phase 7 run 下的 Agent/task 状态 |
| `run_processes` | Phase 7 CLI 进程与 run/task 的绑定 |
| `approval_checkpoints` | Phase 7 人工审批断点 |
| `messages_fts` | FTS5 全文搜索虚拟表 |

`sessions` 当前还承担 IM 状态：`is_pinned`、`archived_at`、`unread_count`、`last_read_at`、`is_muted`。

---

## 有哪些 API？

### 已有

```
# 会话
POST   /api/sessions              创建会话
GET    /api/sessions              会话列表（默认隐藏归档，支持 includeArchived）
GET    /api/sessions/{id}         会话详情
PATCH  /api/sessions/{id}         重命名、置顶、归档/取消归档、免打扰
POST   /api/sessions/{id}/read    标记会话已读
POST   /api/sessions/forward      转发消息到其它会话
DELETE /api/sessions/{id}         删除会话

# 聊天
POST   /api/sessions/{id}/chat    发消息（SSE 流式返回）

# Agent 配置
GET    /api/agents                Agent 列表
POST   /api/agents                创建 Agent
PATCH  /api/agents/{id}           更新 Agent
DELETE /api/agents/{id}           删除 Agent

# 产物
GET    /api/sessions/{id}/artifacts   会话产物列表

# WebSocket
WS     /ws/sessions/{id}          实时通信
```

### Phase 4 新增

```
POST   /api/messages/{id}/reply       引用回复
POST   /api/messages/{id}/regenerate  重新生成（SSE）
POST   /api/messages/{id}/pin         Pin
DELETE /api/messages/{id}/pin         取消 Pin
```

### Phase 4 搜索

```
GET    /api/messages/search?session_id=&q=&limit=   消息搜索
```

---

## 前端有哪些页面？

单页应用，一个主页面，三个 Tab：

1. **聊天 Tab**（默认）：左侧会话列表 + 右侧聊天窗口 + 底部输入框
2. **Agent Tab**：Agent 配置管理（创建/编辑/删除 Agent）
3. **CLI Agent 配置视图**：接入和检测本机 Claude Code / Codex / OpenCode。DeepSeek 属于后端内部系统配置，不进入用户界面。

群聊创建通过 GroupChatCreator 弹窗完成。Orchestrator 协作状态通过 CollaborationView 内联展示。

---

## 怎么跑？

```bash
# 后端
cd backend
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 前端（另一个终端）
cd frontend
npx vite --host 127.0.0.1 --port 5173

# 浏览器打开 http://127.0.0.1:5173
```

用户聊天 Agent 走本机 CLI 认证：请先在系统终端完成 `claude` / `codex` / `opencode` 的安装和登录。`DEEPSEEK_API_KEY` 仅由后端内部读取，用于标题生成、中枢总结、产物编辑辅助等系统能力，不向用户暴露。

---

## 怎么测试？

```bash
# 后端单元 + API 测试
cd backend && python -m pytest test_unit/ test_api/ -v

# 前端类型检查 + 测试
cd frontend && npx tsc --noEmit && npx vitest run

# E2E 浏览器测试（需先启动前后端）
python e2e/full_ui_audit.py
```

---

## 文档清单

项目文档确实多，按用途分类：

### 你必须读的

| 文档 | 位置 | 为什么 |
|------|------|--------|
| **本文档** | `PROJECT_OVERVIEW.md` | 你正在看的 |
| **端到端 PRD** | `docs/PRD/05-End_to_End_Product_Flow.md` | 启动文档需求追踪与 MVP 产品闭环 |
| **Phase 4 Spec** | `docs/specs/phase4/README.md` | 消息交互闭环的权威规格与验收记录 |
| **Phase 5 Spec** | `docs/specs/phase5/README.md` | 产物工作台能力完成记录与未打通边界 |
| **Phase 6 Spec** | `docs/specs/phase6/README.md` | Workspace Runtime、CLI Adapter、Artifact Bridge 核心闭环验收记录 |
| **Phase 7 运行控制交付快照** | `docs/deliverables/phase7-runtime-control/README.md` | 运行控制、审批卡片、环境体检实现与验收记录 |
| **Phase 7 IM 加固交付快照** | `docs/deliverables/phase7-im-hardening/README.md` | 会话 IM 基线、右键菜单、明亮主题、执行过程全屏与 v1.0 UI 加固 |
| **Docs Index** | `docs/README.md` | 查看所有文档入口 |

### 按需查阅

| 文档 | 位置 | 什么时候看 |
|------|------|-----------|
| MessageService 接口定义 | `backend/app/services/message_service.py` | 理解 Phase 4 消息操作契约 |
| ChatService 接口定义 | `backend/app/services/chat_service.py` | 参考已有实现模式 |
| SessionService 实现 | `backend/app/services/session_service.py` | 参考 Service 层写法 |
| ContextManager | `backend/app/domain/context_manager.py` | 理解 Reply/Pin 上下文注入 |
| EventBus | `backend/app/event_bus/event_bus.py` | 理解事件解耦机制 |
| 测试协议 | `docs/TEST_PROTOCOL.md` | 写测试时看规范 |
| Git 规范 | `docs/GIT_PROTOCOL.md` | 提交代码时看格式 |

### 设计参考（有空再看）

| 文档 | 位置 | 内容 |
|------|------|------|
| 项目背景设计 | `AgentHub-多Agent协作平台设计.md` | 课题要求、核心功能、考察要点 |
| 全局上下文 | `CONTEXT.md` | 领域术语、架构总览、完整文档索引 |
| AI 协作规则 | `CLAUDE.md` | 代码规范、禁止事项 |
| 架构决策记录 | `docs/adr/` | 8 篇 ADR，解释"为什么这样设计" |
| Orchestrator 设计 | `docs/specs/phase3/02-orchestrator/` | 9 篇文档，Phase 3 Orchestrator 的完整设计 |
| Phase 1 Spec | `docs/specs/phase1/01-skeleton-spec.md` | Phase 1 功能规格 |
| Phase 2 Spec | `docs/specs/phase2/01-core-features-spec.md` | Phase 2 功能规格 |
