# AgentHub — 多 Agent 协作平台

> AI 版的 Slack：把多个 AI Agent 拉到群聊里，它们自动分工协作，像真人团队一样讨论和产出。

## 项目简介

AgentHub 采用 IM 聊天作为核心交互范式，用户通过新建对话、发送消息的方式与不同 AI Agent 进行交互。支持单聊、群聊（@Agent）、Orchestrator 自动协调、产物预览等能力。

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
| Phase 3 | 智能增强（Orchestrator 升级 + 产物深化 + 体验闭环） | 🔧 进行中 |
| Phase 4 | 收尾（Bug 修复 + Demo 视频 + 答辩准备） | ⏳ 待开始 |

### Phase 3 模块进度

| 模块 | 内容 | 状态 |
|------|------|------|
| M1 | 基础设施（EventBus + DB迁移 + Service ABC） | ✅ |
| M2 | 消息操作（引用/重新生成/Pin） | ⏳ 待开发 |
| M3 | 消息搜索（FTS5 全文检索） | ⏳ 待开发 |
| M4 | Orchestrator 核心（Pipeline + 意图分析 + 任务拆解） | ✅ |
| M5 | 链式协作（已合并入 M4） | ✅ |
| M6 | 产物版本 + Diff | ⏳ 待开发 |
| M7 | 产物在线编辑 | ⏳ 待开发 |
| M8 | Store 拆分 + 体验收尾 | ⏳ 待开发 |

## 测试

```bash
# 后端测试（单元 + API）
cd backend && python -m pytest test_unit/ test_api/ -v

# 前端测试
cd frontend && npx tsc --noEmit && npx vitest run

# E2E 浏览器测试（需先启动前后端）
python e2e/full_ui_audit.py
```

## 分支说明

| 分支 | 用途 |
|------|------|
| `main` | Phase 1 基线 |
| `phase/main` | 阶段集成分支 |
| `phase/phase3-smart-collab` | **当前开发分支** |

## 文档导航

| 想了解... | 看这个 |
|----------|--------|
| 项目背景和核心功能 | [AgentHub-多Agent协作平台设计.md](AgentHub-多Agent协作平台设计.md) |
| 领域术语 + 架构总览 | [CONTEXT.md](CONTEXT.md) |
| AI 协作规则 | [CLAUDE.md](CLAUDE.md) |
| 架构决策 | [docs/adr/](docs/adr/) |
| Phase 3 模块计划 | [docs/specs/phase3-modules.md](docs/specs/phase3-modules.md)（phase3 分支） |
| Orchestrator 设计 | [docs/specs/orchestrator/](docs/specs/orchestrator/)（phase3 分支） |
| 新成员上手 | [docs/ONBOARDING.md](docs/ONBOARDING.md)（phase3 分支） |
| 测试协议 | [docs/TEST_PROTOCOL.md](docs/TEST_PROTOCOL.md) |
| Git 规范 | [docs/GIT_PROTOCOL.md](docs/GIT_PROTOCOL.md) |
