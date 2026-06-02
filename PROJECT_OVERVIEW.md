# AgentHub 项目全景

> 这是一份给人看的文档。不是给 AI 看的 Spec，不是 ADR，就是一个普通开发者接手项目时需要知道的一切。

---

## 这个项目要做什么？

一句话：**做一个 AI 版的 Slack**。

用户打开网页，像用微信/飞书一样，创建对话、发消息。对话的对象不是人，是 AI Agent（比如 DeepSeek、Claude、Gemini 等）。核心玩法：

- **单聊**：选一个 Agent，1v1 对话
- **群聊**：拉多个 Agent 进同一个群，用 @ 指定谁来回，或者让 Orchestrator（协调器）自动分配任务
- **产物预览**：Agent 回复不只是文字，还能生成代码、网页等富媒体内容，直接在聊天里预览

这是一个**毕业设计/课题项目**，考察重点：AI 协作能力(30%) > 功能完整度(25%) > 生成效果(20%) > 代码理解(15%) > 创新(10%)。

---

## 技术栈

```
前端：React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui + Zustand
后端：Python FastAPI + SQLAlchemy 2.0 (async) + SQLite
通信：SSE（流式推送） + WebSocket（实时双向）
AI  ：6 家适配器（DeepSeek / Claude / Gemini / OpenAI / GLM / MiniMax）
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
│       ├── agents/             ← AI 适配器（每家厂商一个）
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
└── .claude/skills/             ← AI 工作流 Skill
```

---

## 已经做完了什么？

项目分 5 个阶段，目前 Phase 1、Phase 2 已全部完成，Phase 3 完成了一部分。

### Phase 1：单聊全链路 ✅

最薄的可运行版本：用户发消息 → 后端调 Claude API → 流式返回 → 前端逐字显示 → 存到 SQLite。

- 前端：会话列表 + 聊天窗口 + 输入框 + SSE 流式渲染
- 后端：Session CRUD + Chat SSE 端点 + Claude/DeepSeek 适配器
- 数据库：Session + Message 两张表
- 测试：28 条

### Phase 2：多 Agent + 群聊 + Orchestrator ✅

从"单人单 AI"升级到"多人多 AI 协作"。

- 多 Agent 支持：6 家厂商适配器，统一接口
- Agent 管理：CRUD API + 前端 AgentPanel 配置界面
- 群聊模式：Session 支持 single/group 两种模式，SessionMember 多对多关联
- Orchestrator V1：消息路由 + 多 Agent 并发协调
- WebSocket：实时双向通信（心跳 + 重连 + 广播）
- 产物预览：Artifact 模型 + 前端渲染
- 前端重构：三 Tab 布局（聊天/Agent/设置）+ Markdown 渲染 + @提及补全
- 测试：72 条后端 + 7 条前端

### Phase 3 部分完成（3/8 模块）

Phase 3 是"智能增强"，拆成 8 个模块：

| 模块 | 内容 | 状态 |
|------|------|------|
| M1 | 基础设施（EventBus + DB 迁移 + Service ABC） | ✅ 完成 |
| M2 | 消息操作（引用/重新生成/Pin） | ⏳ 待开发 |
| M3 | 消息搜索（FTS5 全文检索） | ⏳ 待开发 |
| M4 | Orchestrator 核心（意图分析 + Agent 选择 + 任务拆解 + 执行引擎） | ✅ 完成 |
| M5 | 链式协作（A 产出 → B Review） | ✅ 合并进 M4 |
| M6 | 产物版本 + Diff | ⏳ 待开发 |
| M7 | 产物在线编辑 | ⏳ 待开发 |
| M8 | Store 拆分 + 体验收尾 | ⏳ 待开发 |

---

## 接下来要做什么？（Phase 3 剩余）

### M2：消息操作（引用/重新生成/Pin）

用户在聊天里能做的事：

- **引用回复**：hover 消息 → 点"引用" → 输入框上方出现引用卡片 → 发送后气泡显示引用预览
- **重新生成**：hover AI 消息 → 点"重新生成" → 后端用相同上下文重新调用 Agent → 原地替换旧内容
- **Pin 消息**：hover 消息 → 点"Pin" → 图钉图标 → 后续对话中 Pin 的消息始终包含在上下文里

涉及 4 个新 API 端点、2 个新前端组件、修改 MessageBubble。

### M3：消息搜索

- FTS5 全文搜索（SQLite 内置，不需要外部服务）
- 快捷键 Ctrl+K 打开搜索面板
- 搜索结果高亮、点击跳转到对应消息
- FTS5 不可用时降级为 LIKE 查询

### M6：产物版本 + Diff

- 每次重新生成产物 → 版本号 +1，形成版本链
- 任意两个版本之间做 Diff 对比
- 前端用 `react-diff-viewer-continued` 展示

### M7：产物在线编辑（最复杂）

- 用户在产物代码中选中片段 → 描述修改意图 → Agent 返回修改结果 → Diff 确认 → 应用
- 支持 tool calling 的 Agent 走工具调用，不支持的降级为上下文注入

### M8：收尾

- Zustand Store 拆分（chat / session / search）
- 全局 UX 润色

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

- **Agent 适配器模式**：6 家 AI 厂商通过统一的 `BaseAgentAdapter` 接口屏蔽差异，新增厂商只需写一个适配器
- **EventBus 解耦**：Agent 流式输出 → EventBus 广播 → WebSocket 推送 / 持久化 / 产物检测，各模块不直接依赖
- **Orchestrator 四阶段流水线**：意图分析 → Agent 选择 → 任务拆解 → 执行调度，每个阶段独立可测试
- **SQLite + FTS5**：零配置数据库，内置全文搜索，课题项目够用

---

## 数据库有哪些表？

| 表 | 用途 |
|----|------|
| `sessions` | 会话（single/group 模式） |
| `messages` | 消息（支持 parent_message_id 引用、is_pinned 标记） |
| `session_members` | 群聊成员关联表 |
| `agent_configs` | Agent 配置（名称、描述、system_prompt、厂商、模型） |
| `artifacts` | 产物（代码、网页预览等，支持版本链） |
| `messages_fts` | FTS5 全文搜索虚拟表（M3 待用） |

---

## 有哪些 API？

### 已有

```
# 会话
POST   /api/sessions              创建会话
GET    /api/sessions              会话列表
GET    /api/sessions/{id}         会话详情
DELETE /api/sessions/{id}         删除会话

# 聊天
POST   /api/sessions/{id}/chat    发消息（SSE 流式返回）

# Agent 配置
GET    /api/agents                Agent 列表
POST   /api/agents                创建 Agent
PUT    /api/agents/{id}           更新 Agent
DELETE /api/agents/{id}           删除 Agent

# 产物
GET    /api/sessions/{id}/artifacts   会话产物列表

# WebSocket
WS     /ws/sessions/{id}          实时通信
```

### M2 新增

```
POST   /api/messages/{id}/reply       引用回复
POST   /api/messages/{id}/regenerate  重新生成（SSE）
POST   /api/messages/{id}/pin         Pin
DELETE /api/messages/{id}/pin         取消 Pin
```

### M3 新增

```
GET    /api/messages/search?session_id=&q=&limit=   消息搜索
```

---

## 前端有哪些页面？

单页应用，一个主页面，三个 Tab：

1. **聊天 Tab**（默认）：左侧会话列表 + 右侧聊天窗口 + 底部输入框
2. **Agent Tab**：Agent 配置管理（创建/编辑/删除 Agent）
3. **设置 Tab**：API Key 配置

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

需要在 `backend/.env` 里配置至少一个 API Key（推荐 DeepSeek，便宜）。

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
| **Phase 3.2 Spec** | `docs/specs/phase3.2-message-actions-spec.md` | 你要做的功能规格 |
| **Phase 3.3 Spec** | `docs/specs/phase3.3-message-search-spec.md` | 你要做的功能规格 |
| **Phase 3 模块总览** | `docs/specs/phase3-modules.md` | 了解所有模块的依赖关系 |

### 按需查阅

| 文档 | 位置 | 什么时候看 |
|------|------|-----------|
| MessageService 接口定义 | `backend/app/services/message_service.py` | 写 M2/M3 后端时 |
| ChatService 接口定义 | `backend/app/services/chat_service.py` | 参考已有实现模式 |
| SessionService 实现 | `backend/app/services/session_service.py` | 参考 Service 层写法 |
| ContextManager | `backend/app/domain/context_manager.py` | M2 Pin 消息需要联动 |
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
| Orchestrator 设计 | `docs/specs/orchestrator/` | 9 篇文档，M4 的完整设计 |
| 新成员上手 | `docs/ONBOARDING.md` | 更详细的项目介绍 |
| Phase 1 Spec | `docs/specs/phase1-skeleton-spec.md` | Phase 1 功能规格 |
| Phase 2 Spec | `docs/specs/phase2-core-features-spec.md` | Phase 2 功能规格 |
