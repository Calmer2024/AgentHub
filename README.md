# AgentHub — 多 Agent 协作平台

> AI 版的 Slack：把多个 AI Agent 拉到群聊里，它们自动分工协作，像真人团队一样讨论和产出。

## 项目简介

AgentHub 采用 IM 聊天作为核心交互范式，用户通过新建对话、发送消息的方式与不同 AI Agent 进行交互。支持单聊、群聊（@Agent）、Orchestrator 自动协调、产物预览等能力。

底层 Agent 架构以 [PRD-01 CLI Adapter](docs/PRD/01-Architecture_Adapter.md) 为准：目标不是裸调 HTTP LLM API，而是由后端封装真实 CLI 工具，例如 Anthropic 官方 `claude` CLI、开源 `opencode` 等。当前 DeepSeek/Gemini/GLM/MiniMax/Claude/OpenAI HTTP 适配器是过渡/并存能力，Phase 6 会补齐 CLI Wrapper。

**技术栈**：React + FastAPI + SQLite + WebSocket/SSE

## 快速启动

```bash
# 1. 配置 API Keys
cp backend/.env.example backend/.env
# 编辑 .env，填入至少一个 API Key（DEEPSEEK_API_KEY 推荐）

# 2. 启动后端
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload

# 3. 启动前端（新终端）
cd frontend
npm install
npx vite --host 127.0.0.1 --port 5173

# 4. 浏览器打开 http://127.0.0.1:5173
```

## 项目结构

```
AgentHub/
├── backend/                    # Python FastAPI 后端
│   └── app/
│       ├── api/                # REST + WebSocket 路由
│       ├── services/           # 业务逻辑层 (ChatService, MessageService, SessionService)
│       ├── domain/             # 纯逻辑层 (Orchestrator, ContextManager)
│       ├── agents/             # AI 适配器 (DeepSeek, Gemini, GLM, MiniMax, Claude, OpenAI)
│       ├── event_bus/          # 内存 Pub/Sub 事件总线
│       ├── infrastructure/     # 跨领域工具 (StreamMerger)
│       ├── models/             # SQLAlchemy ORM 模型
│       └── migrations/         # 数据库迁移脚本 (幂等)
├── frontend/                   # React + TypeScript + Vite
│   └── src/
│       ├── components/         # UI 组件
│       ├── stores/             # Zustand 状态管理
│       ├── api/                # REST + SSE + WebSocket 客户端
│       └── types/              # TypeScript 类型
├── docs/                       # 文档
│   ├── adr/                    # 架构决策记录 (ADR-0001 ~ 0008)
│   ├── specs/                  # 功能规格 + Orchestrator 设计文档
│   └── testing/                # 测试规范
├── e2e/                        # Playwright E2E 测试
└── .claude/skills/             # AI 工作流 Skill
```

## 开发阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 单聊全链路（SSE 流式） | ✅ 已完成 |
| Phase 2 | 多 Agent + 群聊 + Orchestrator + WebSocket + 产物预览 | ✅ 已完成 |
| Phase 3 | Orchestrator v2 + EventBus + DAG 协作面板 | ✅ 已完成 |
| Phase 4 | 消息交互闭环（Reply/Regenerate/Pin/Search） | ✅ 已完成 |
| Phase 5 | 产物深度管理（版本链 + Diff + 在线编辑） | 📋 计划中 |
| Phase 6 | CLI Agent 适配器 | 📋 计划中 |
| Phase 7 | UX 体验闭环 | 📋 计划中 |

### Phase 4 能力

| 能力 | 状态 |
|------|------|
| 引用回复 + 引用预览 + 跳转原消息 + Agent Prompt 引用上下文注入 | ✅ |
| AI 回复重新生成 + SSE 流式替换 + 原版保留 | ✅ |
| Pin/Unpin + `[Pinned message]` 长期上下文单聊/群聊优先注入 | ✅ |
| FTS5 全文搜索 + 中文 LIKE fallback + 结果跳转高亮 | ✅ |

## 测试

```bash
# 后端测试（单元 + API）
cd backend && python -m pytest test_unit/ test_api/ -v

# 前端测试
cd frontend && npx tsc --noEmit && npx vitest run

# E2E 浏览器测试（需先启动前后端）
python e2e/full_ui_audit.py

# Phase 4 真实 HTTP 验收（自动启动临时后端）
backend\venv\Scripts\python.exe e2e\phase4_real_acceptance.py
```

## 分支说明

| 分支 | 用途 |
|------|------|
| `main` | Phase 1 基线 |
| `phase/main` | 阶段集成分支 |
| `phase/phase3-smart-collab` | 历史开发分支 |

## 文档导航

| 想了解... | 看这个 |
|----------|--------|
| 项目背景和核心功能 | [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) |
| 领域术语 + 架构总览 | [CONTEXT.md](CONTEXT.md) |
| AI 协作规则 | [CLAUDE.md](CLAUDE.md) |
| 架构决策 | [docs/adr/](docs/adr/) |
| Phase 4 消息交互闭环 | [docs/specs/phase4/README.md](docs/specs/phase4/README.md) |
| Orchestrator 设计 | [docs/specs/phase3/02-orchestrator/](docs/specs/phase3/02-orchestrator/) |
| 测试协议 | [docs/TEST_PROTOCOL.md](docs/TEST_PROTOCOL.md) |
| Git 规范 | [docs/GIT_PROTOCOL.md](docs/GIT_PROTOCOL.md) |
