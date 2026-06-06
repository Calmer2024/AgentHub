# AgentHub — 多 Agent 协作平台

> AI 版的 Slack：把多个 AI Agent 拉到群聊里，它们自动分工协作，像真人团队一样讨论和产出。

## 项目简介

AgentHub 采用 IM 聊天作为核心交互范式，用户通过新建对话、发送消息的方式与不同 AI Agent 进行交互。支持单聊、群聊（@Agent）、Orchestrator 自动协调、产物预览等能力。最新产品闭环以 [PRD-05 端到端产品闭环](docs/PRD/05-End_to_End_Product_Flow.md) 为准；P1 当前 Artifact 体验以 [ADR-0010](docs/adr/0010-message-level-artifact-experience.md) 为准：用户输入任务后，系统要打通 Agent 执行、消息级 Artifact Card、页面级预览/编辑/版本管理和审批继续。

底层 Agent 架构以 [PRD-01 CLI Adapter](docs/PRD/01-Architecture_Adapter.md) 为准：AgentHub 不是裸调 HTTP LLM API，而是通过 PTY/subprocess 封装真实 CLI 工具（Anthropic 官方 `claude` CLI、开源 `opencode` 等），提供 stdin/stdout 桥接、ANSI 清洗、交互式拦截。这是项目唯一的 Agent 架构。

**技术栈**：React + FastAPI + SQLite + WebSocket/SSE

## 快速启动

```bash
# 1. 准备本机 CLI 与内部系统模型配置
cp backend/.env.example backend/.env
# 在系统终端完成 claude / codex / opencode 的安装和登录
# 项目内部能力需要 DEEPSEEK_API_KEY，由开发者在 .env 中配置，不向用户暴露

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
│       ├── agents/             # CLI adapters + DeepSeek system model adapter
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
| Phase 5 | 产物工作台能力（版本链 + Diff + 在线编辑） | ✅ 已完成 |
| Phase 6 | Workspace Runtime + CLI Agent 适配器 + 产物入口桥接 | ✅ 核心闭环验收通过 |
| Phase 7 | 任务可控性 + 审批 + 环境体检 + 演示闭环 | 📋 计划中 |

### Phase 4 能力

| 能力 | 状态 |
|------|------|
| 引用回复 + 引用预览 + 跳转原消息 + Agent Prompt 引用上下文注入 | ✅ |
| AI 回复重新生成 + SSE 流式替换 + 原版保留 | ✅ |
| Pin/Unpin + `[Pinned message]` 长期上下文单聊/群聊优先注入 | ✅ |
| FTS5 全文搜索 + 中文 LIKE fallback + 结果跳转高亮 | ✅ |

### Phase 5 能力

| 能力 | 状态 |
|------|------|
| Artifact 版本链 + 会话只展示最新链头 | ✅ |
| 任意版本 Diff + split/unified 双模式 | ✅ |
| 代码选区编辑 + Diff 预览 + 确认创建新版本/拒绝不落库 | ✅ |
| DeepSeek system model tool calling + 上下文降级 | ✅ |
| ArtifactService 接入 EventBus (`artifact.created` / `artifact.version_created`) | ✅ |

Phase 5 的边界也已经在文档中明确：它完成的是“对已有 Artifact 的工作台能力”。Phase 6 已补齐 Project-first workspace runtime、真实 CLI 执行和 Artifact Bridge：CLI 产物会以消息下方卡片出现，并可继续编辑、引用和版本管理。Phase 7 继续做运行取消/恢复、审批卡片、环境体检和真实演示加固。

### Phase 6 能力

| 能力 | 状态 |
|------|------|
| Project 实体 + `sessions.project_id` + `artifacts.project_id` | ✅ |
| 创建项目菜单：新建空白文件夹 / 选择现有文件夹 | ✅ |
| 选择现有文件夹通过系统原生目录选择器授权，不要求用户手输路径 | ✅ |
| 去除用户可选的“静态网页 / Vite React / 已有项目”项目类型 | ✅ |
| workspace 文件树、文件读取安全校验、snapshot/diff、静态 preview | ✅ |
| `/api/sessions/{id}/workspace` 返回 Session 继承的 `workspacePath` | ✅ |
| Claude Code / Codex / OpenCode 真实 CLI Agent 路径 | ✅ |
| CLI 输出与 workspace diff 自动创建 Artifact | ✅ |
| 消息下方 ArtifactCard、文件编辑器、代码片段引用、版本管理 | ✅ |

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

# Phase 5 真实 HTTP 验收（自动启动临时后端）
backend\venv\Scripts\python.exe e2e\phase5_real_acceptance.py
```

## 每轮结束服务交接

每轮开发/修复结束必须清理旧后端/前端进程，用当前仓库代码启动新服务，并在真实服务上完成验收。最终交付必须给出：

- 前端地址，默认 `http://127.0.0.1:5173`
- 后端地址，默认 `http://127.0.0.1:8000`
- API 文档地址，默认 `http://127.0.0.1:8000/docs`

若端口被占用，使用新端口并明确说明。详见 [CLAUDE.md](CLAUDE.md) 和 [测试协议](docs/TEST_PROTOCOL.md)。

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
| 端到端产品闭环 | [docs/PRD/05-End_to_End_Product_Flow.md](docs/PRD/05-End_to_End_Product_Flow.md) |
| MVP 本机 workspace 链路 | [docs/PRD/06-MVP_Local_Workspace_Delivery.md](docs/PRD/06-MVP_Local_Workspace_Delivery.md) |
| SaaS 云端 workspace 链路 | [docs/PRD/07-SaaS_Cloud_Workspace_Delivery.md](docs/PRD/07-SaaS_Cloud_Workspace_Delivery.md) |
| PRD/Spec 覆盖审计 | [docs/audit/prd-spec-coverage-audit.md](docs/audit/prd-spec-coverage-audit.md) |
| Phase 5 产物工作台能力 | [docs/specs/phase5/README.md](docs/specs/phase5/README.md) |
| Phase 6 Workspace + CLI + 产物入口桥接 | [docs/specs/phase6/README.md](docs/specs/phase6/README.md) |
| Phase 7 MVP 演示闭环 | [docs/specs/phase7/README.md](docs/specs/phase7/README.md) |
| Orchestrator 设计 | [docs/specs/phase3/02-orchestrator/](docs/specs/phase3/02-orchestrator/) |
| 测试协议 | [docs/TEST_PROTOCOL.md](docs/TEST_PROTOCOL.md) |
| Git 规范 | [docs/GIT_PROTOCOL.md](docs/GIT_PROTOCOL.md) |
