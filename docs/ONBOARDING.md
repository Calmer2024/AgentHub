# AgentHub 新成员上手指南

**最后更新**: 2026-06-01
**当前分支**: `phase/phase3-smart-collab`

---

## 1. 项目概览

AgentHub 是一个 **多 Agent 协作平台**，采用 IM 聊天作为核心交互范式。用户像用微信一样创建群聊、@Agent、发消息，多个 AI Agent 在后台自动协作完成任务。

**核心理念**: 自动化优先。复杂决策由后端自动完成，不暴露过多配置给用户。

### 1.1 一句话定位

> "AI 版的 Slack — 你把多个 AI Agent 拉到群聊里，它们自动分工协作，像真人团队一样讨论和产出。"

### 1.2 当前阶段

**Phase 3 (增强)** 进行中。Phase 1 (单聊) 和 Phase 2 (基础群聊+Orchestrator) 已交付。

---

## 2. 项目结构

```
AgentHub/
├── backend/                        # Python FastAPI 后端
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口 + lifespan
│   │   ├── config.py               # Pydantic Settings (API keys, CORS)
│   │   ├── database.py             # AsyncEngine + Session + Base
│   │   ├── api/                    # API 路由层
│   │   │   ├── chat.py             # POST /sessions/{id}/chat (SSE)
│   │   │   ├── sessions.py         # 会话 CRUD
│   │   │   ├── agents.py           # Agent 配置 CRUD
│   │   │   ├── ws.py               # WebSocket 端点
│   │   │   └── ws_manager.py       # ConnectionManager
│   │   ├── services/               # 业务逻辑层
│   │   │   ├── chat_service_impl.py # 聊天核心 (thin coordinator)
│   │   │   ├── agent_executor.py   # Agent 执行引擎
│   │   │   ├── schemas.py          # Pydantic 共享模型
│   │   │   ├── session_service.py  # 会话管理
│   │   │   └── message_service.py  # 消息操作 (ABC)
│   │   ├── domain/                 # 纯逻辑 (零 FastAPI 依赖)
│   │   │   ├── orchestrator_v2.py  # Pipeline thin coordinator
│   │   │   ├── intent_analyzer.py  # 意图分析
│   │   │   ├── agent_selector.py   # Agent 选择
│   │   │   ├── task_decomposer.py  # 任务拆解 + 6 角色
│   │   │   ├── execution_planner.py # 执行计划 + 优先级链
│   │   │   └── context_manager.py  # Token 预算 + 截断
│   │   ├── agents/                 # AI 模型适配器
│   │   │   ├── base.py             # BaseAgentAdapter (契约)
│   │   │   ├── registry.py         # AgentRegistry
│   │   │   ├── deepseek_adapter.py
│   │   │   ├── gemini_adapter.py
│   │   │   ├── glm_adapter.py
│   │   │   └── minimax_adapter.py
│   │   ├── event_bus/              # 发布/订阅
│   │   │   ├── event_types.py      # EventType 枚举
│   │   │   └── event_bus.py        # InMemoryEventBus
│   │   ├── infrastructure/         # 跨领域工具
│   │   │   └── stream_merger.py    # 异步流交错合并
│   │   ├── models/                 # SQLAlchemy 模型
│   │   │   ├── agent_config.py     # Agent 配置表
│   │   │   ├── session.py          # 会话表
│   │   │   ├── message.py          # 消息表
│   │   │   ├── session_member.py   # 群成员关联表
│   │   │   └── artifact.py         # 产物表
│   │   └── migrations/             # DB 迁移 (幂等 SQL)
│   ├── test_unit/                  # 单元测试
│   └── test_api/                   # API 集成测试
│
├── frontend/                       # React + TypeScript + Vite
│   └── src/
│       ├── App.tsx                 # 主应用 + 协作状态管理
│       ├── types/index.ts          # TypeScript 类型定义
│       ├── api/
│       │   ├── client.ts           # REST + SSE 客户端
│       │   └── wsClient.ts         # WebSocket 客户端
│       ├── stores/
│       │   ├── chatStore.ts        # 聊天状态 + 协作持久化
│       │   └── sessionStore.ts     # 会话/Agent/Provider 状态
│       └── components/
│           ├── ChatWindow.tsx      # 主聊天区 (Orchestrator 横幅 + 气泡)
│           ├── ChatInput.tsx       # @mention 输入框
│           ├── MessageBubble.tsx   # 消息气泡 (Markdown 渲染)
│           ├── CollaborationView.tsx # 协作面板
│           ├── GroupChatCreator.tsx  # 群聊创建 (无链式开关)
│           ├── SessionList.tsx     # 会话列表
│           ├── AgentPanel.tsx      # Agent 管理
│           └── SettingsPanel.tsx   # API Key 配置
│
├── docs/
│   ├── CONTEXT.md                  # 领域术语 + 架构总览 + 文档索引
│   ├── CLAUDE.md                   # AI 行为规则
│   ├── ONBOARDING.md               # 本文件
│   ├── adr/                        # 架构决策记录 (0001-0008)
│   ├── specs/                      # 功能规格
│   │   ├── orchestrator/           # Orchestrator 完整设计文档
│   │   ├── phase3-modules.md       # Phase 3 模块拆解
│   │   └── phase3-parallel-guide.md
│   ├── testing/                    # 测试规范
│   └── TEST_PROTOCOL.md
│
├── e2e/                            # Playwright E2E 测试
│   └── full_ui_audit.py
│
└── .claude/
    ├── skills/                     # AI Skill 定义
    │   ├── agenthub-module-dev/
    │   ├── agenthub-code-review/
    │   ├── agenthub-qa-audit/
    │   └── agenthub-phase-wrapup/
    └── settings.local.json
```

---

## 3. 技术栈 (锁定)

| 层 | 技术 |
|----|------|
| Frontend | React + TypeScript + Vite + shadcn/ui + Tailwind CSS v3 |
| State | Zustand |
| Backend | Python 3.12 + FastAPI |
| Database | SQLite + SQLAlchemy 2.0 (async aiosqlite) |
| AI | 4 家厂商: DeepSeek, Gemini, GLM (智谱), MiniMax |
| Desktop | Tauri v2 |
| Mobile | Capacitor |
| Testing | pytest + pytest-asyncio + vitest + Playwright |

---

## 4. 核心概念速查

> 完整术语表见 [CONTEXT.md](CONTEXT.md)

| 概念 | 说明 |
|------|------|
| **Agent** | 用户创建的 AI 角色 (名称 + 描述 + system_prompt)，底层调用 4 家模型厂商之一。**Agent ≠ Provider。** |
| **Provider** | 模型厂商 (DeepSeek/Gemini/GLM/MiniMax) |
| **Orchestrator** | 群聊智能调度核心 — 意图分析 → Agent 选择 → 任务拆解 → 执行调度 |
| **Pipeline** | Orchestrator 四阶段: ContextAssembly → AgentSelection → ExecutionPlanning → Lifecycle |
| **协作 DAG** | 有向无环图，描述一次协作中 Phase 间的依赖关系。Phase 间串行，Phase 内可并行 |
| **协作角色** | 6 种: planner(规划)/executor(执行)/reviewer(审查)/researcher(研究)/synthesizer(综合)/critic(批判) |
| **SharedContext** | 所有 Agent 共享的对话历史，Agent 完成后产出自动追加 |
| **CollaborationPanel** | 前端 DAG 可视化面板，展示协作流程和实时状态 |
| **SSE** | Server-Sent Events — 后端推送 Agent token 流到前端的协议 |
| **自动化优先** | 复杂决策由后端自动完成，不暴露给用户配置 |

---

## 5. 核心数据流

```
用户在群聊中发送消息
  │
  ▼
POST /sessions/{id}/chat { content, mentions? }
  │
  ▼
ChatServiceImpl._group_chat()
  ├── 查询 SessionMembers → member_agents
  ├── 构建 PipelineRequest
  │
  ▼
OrchestratorV2.run(req)
  ├── IntentAnalyzer.analyze()     → intent + required_tags
  ├── ContextManager.assemble()     → 截断控制
  ├── AgentSelector.select()        → Agent 元数据标签匹配
  └── ExecutionPlanner.plan()       → 执行模式 + 角色分配
  │
  ▼
AgentExecutor.execute(calls, mode)
  ├── mode=single   → 单 Agent + 60s 超时
  ├── mode=parallel → N 并发 + StreamMerger
  └── mode=chain    → 串行 + 产出注入 + 中断检测
  │
  ▼
SSE 事件流 → 前端 CollaborationView + MessageBubble
```

---

## 6. 开发规则

> 完整规则见 [CLAUDE.md](CLAUDE.md)

| 规则 | 说明 |
|------|------|
| 分层依赖 | Frontend → API → Service → Domain → Infrastructure → Data (只能向下依赖) |
| Domain 纯逻辑 | 零 FastAPI/SQLAlchemy 导入 |
| 单文件 300 行 | 超过必须拆分 |
| 自动化优先 | 复杂决策后端自动完成，前端不暴露配置开关 |
| 中文注释 | 所有代码注释用中文 |
| Git 确认 | 任何 Git 操作前必须获得人工验收确认 |
| Comment in Chinese | All code comments in Chinese |

---

## 7. 关键文档索引

| 我想了解... | 看这个 |
|------------|--------|
| 项目整体设计 + 术语 | [CONTEXT.md](CONTEXT.md) |
| AI 行为规则 | [CLAUDE.md](CLAUDE.md) |
| 架构决策 | [docs/adr/](adr/) (尤其是 0005 和 0008) |
| Orchestrator 全部设计 | [docs/specs/orchestrator/README.md](specs/orchestrator/README.md) |
| Phase 3 整体计划 | [docs/specs/phase3-modules.md](specs/phase3-modules.md) |
| 测试协议 | [TEST_PROTOCOL.md](TEST_PROTOCOL.md) |
| UX 测试规范 | [testing/UX_TEST_SPEC.md](testing/UX_TEST_SPEC.md) |
| Git 规范 | [GIT_PROTOCOL.md](GIT_PROTOCOL.md) |
| Phase 3 并行开发 | [docs/specs/phase3-parallel-guide.md](specs/phase3-parallel-guide.md) |

---

## 8. 快速启动

```bash
# 1. 配置 API Keys
cp backend/.env.example backend/.env
# 编辑 .env: DEEPSEEK_API_KEY=sk-xxx

# 2. 启动后端
cd backend
.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload

# 3. 启动前端
cd frontend
npm install
npx vite --host 127.0.0.1 --port 5173

# 4. 浏览器打开
http://127.0.0.1:5173
```

---

## 9. Skill 说明

| Skill | 用途 | 触发 |
|-------|------|------|
| `agenthub-module-dev` | 标准模块开发流程 | 开发新功能时 |
| `agenthub-code-review` | 代码审查 | 模块完成后说 "审查" |
| `agenthub-qa-audit` | 企业级质量审计 (真实环境 E2E) | 说 "质量审计"/"验收测试" |
| `agenthub-phase-wrapup` | 阶段收尾 | 说 "阶段验收"/"收尾" |

---

## 10. 测试命令

```bash
# 后端全部测试
cd backend && .venv\Scripts\python.exe -m pytest test_unit/ test_api/ -v

# 前端类型检查 + 测试
cd frontend && npx tsc --noEmit && npx vitest run

# E2E 浏览器测试 (需先启动后端+前端)
cd . && .venv\Scripts\python.exe e2e/full_ui_audit.py
```
