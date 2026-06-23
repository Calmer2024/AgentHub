# AgentHub — 多 Agent 协作平台

> AI 版的 Slack：把多个 AI Agent 拉到同一个项目群聊里，由 Orchestrator 自动拆解任务、分派角色、执行工作，并把代码、网页、文档、部署等产物回流到聊天流中。

## 1. 项目简介

AgentHub 是一个以 IM 聊天为核心交互范式的多 Agent 协作平台。用户先创建 Project，再在 Project 下创建单聊或群聊，与 Claude Code、Codex、OpenCode 等真实 CLI Agent 协作完成任务。

项目核心不是简单调用大模型 API，而是通过 CLI Wrapper 启动真实 Agent 工具进程，让 Agent 在 Project workspace 中读写文件、运行命令、生成产物，并通过消息级 Artifact 卡片完成预览、编辑、Diff、版本和部署回流。

## 2. 交付材料入口

| 入口 | 位置 |
| --- | --- |
| 交付总入口 | [docs/submission/00-交付总入口.md](docs/submission/00-交付总入口.md) |
| 产品设计文档 | [docs/submission/01-产品设计文档.md](docs/submission/01-产品设计文档.md) |
| 技术设计文档 | [docs/submission/02-技术设计文档.md](docs/submission/02-技术设计文档.md) |
| AI 协作开发记录 | [docs/submission/03-AI协作开发记录.md](docs/submission/03-AI协作开发记录.md) |
| 项目答辩核心掌握指南 | [docs/submission/04-项目答辩核心掌握指南.md](docs/submission/04-项目答辩核心掌握指南.md) |
| 全局上下文与文档索引 | [CONTEXT.md](CONTEXT.md) |
| 文档中心 | [docs/README.md](docs/README.md) |
| 当前架构事实 | [docs/architecture/overview.md](docs/architecture/overview.md) |
| 数据模型 | [docs/architecture/data-model.md](docs/architecture/data-model.md) |
| 课题原始要求 | [docs/archive/AgentHub-多Agent协作平台设计.md](docs/archive/AgentHub-多Agent协作平台设计.md) |

## 3. 核心功能

| 模块 | 能力 |
| --- | --- |
| IM 聊天 | Project、会话列表、单聊、群聊、消息历史、引用、Pin、搜索、重新生成。 |
| 多 Agent 协作 | Orchestrator 计划生成、任务拆解、DAG 调度、Agent 分派、结果汇总。 |
| 真实 Agent 接入 | 通过 CLI Wrapper 接入 Claude Code、Codex、OpenCode 等真实 CLI 工具。 |
| Workspace | 本机 Project 绑定真实目录；SaaS Project 使用云端 workspace。 |
| Artifact | 代码、文件、网页预览、Diff、版本、编辑、部署状态以消息级卡片回流。 |
| 桌面端 | Tauri 桌面壳，一键启动本地后端和前端，管理本机 CLI 进程生命周期。 |
| SaaS 云端 | 云端 workspace、团队、仓库导入、快照恢复、云端 runtime、预览和部署链接。 |
| 移动端 | 轻量查看、审批、产物预览的产品壳和能力矩阵。 |
| AI 协作沉淀 | Rules、PRD、ADR、阶段归档、历史 Skill、Dev Log 和测试协议。 |

## 4. Demo 路线

### 4.1 本机桌面端主线

1. 双击启动 AgentHub Local Desktop。
2. 创建 Project 并绑定本机 workspace。
3. 创建单聊，让 Agent 读取、修改或生成项目文件。
4. 查看聊天流中的执行过程、文件变化和 Artifact 卡片。
5. 创建群聊，让 Orchestrator 拆解任务并调度多个 Agent。
6. 展示计划执行、人机确认、Agent 输出和最终产物。

### 4.2 SaaS 云端能力

1. 展示 SaaS Web 入口。
2. 展示团队、云端 workspace、仓库导入、快照恢复。
3. 展示云端 Agent Runtime、云端产物预览和一键部署访问链接。

### 4.3 AI 协作开发记录

1. 展示 `CLAUDE.md` / `CONTEXT.md` 项目规则。
2. 展示 `docs/archive/phases/` 中的阶段规格与开发日志归档。
3. 展示早期 Skill 在 Git 历史中的演进和退役记录。
4. 展示 `docs/archive/phases/dev-logs/` 阶段开发记录。

## 5. 运行方式

### 5.1 桌面端

```text
双击 AgentHub Local Desktop.exe
```

桌面端会自动启动本地后端并打开前端界面。关闭桌面端窗口后，本地后端进程会随之释放。

### 5.2 源码开发模式

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8188 --reload
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开：

```text
http://127.0.0.1:5173
```

### 5.3 桌面端构建

```powershell
cd desktop
npm install
npm run build
```

构建产物会输出到桌面端 release/portable 目录，具体路径以命令输出为准。
当前 portable demo 包默认输出到：

```text
deploy/desktop-demo/AgentHub-Local-Desktop-Demo-0.1.0-win-x64/
deploy/desktop-demo/AgentHub-Local-Desktop-Demo-0.1.0-win-x64.zip
```

## 6. 项目结构

```text
AgentHub/
├── backend/              # FastAPI 后端、服务层、Agent Runtime、数据库模型
├── frontend/             # React + TypeScript + Vite 前端
├── desktop/              # Tauri 本地桌面端
├── mobile/               # Capacitor 移动端产品壳
├── docs/                 # PRD、ADR、Architecture、用户手册、测试协议、归档文档
├── CLAUDE.md             # AI Agent 行为规则
└── CONTEXT.md            # 全局上下文和文档索引
```

## 7. 技术架构

```text
React / Tauri / SaaS Web / Mobile
  ↓
FastAPI API Gateway
  ↓
Service 业务层
  ↓
Domain：Orchestrator / ContextManager / Workspace / Artifact
  ↓
Infrastructure：CLI Adapter / EventBus / Runtime Provider
  ↓
SQLite / Cloud Workspace Metadata
```

技术栈：

| 层 | 技术 |
| --- | --- |
| 前端 | React + TypeScript + Vite + shadcn/ui + Tailwind CSS v3 |
| 后端 | FastAPI + WebSocket / SSE |
| 数据库 | SQLite + SQLAlchemy 2.0 async |
| 桌面端 | Tauri v2 |
| 移动端 | Capacitor |
| Agent Runtime | Claude Code CLI、Codex CLI、OpenCode CLI |
| 测试 | pytest、vitest、Playwright |

## 8. 课题要求映射

| 课题要求 | 对应实现 | 文档位置 |
| --- | --- | --- |
| IM 聊天式交互 | Project、单聊、群聊、消息操作、上下文连续。 | `docs/PRD/03-User_Experience.md` |
| 主 Agent 协调器 | Orchestrator、DAG、调度状态、人机确认。 | `docs/adr/0007-Orchestrator 架构设计.md` |
| 多 Agent 接入 | Claude Code、Codex、OpenCode CLI Adapter。 | `docs/PRD/01-Architecture_Adapter.md` |
| 产物预览与编辑 | Artifact 卡片、预览、编辑、Diff、版本。 | `docs/archive/adr/0010-message-level-artifact-experience.md` |
| 部署发布 | SaaS 云端 deployment、访问链接。 | `docs/archive/phases/specs/phase11/README.md` |
| 多端支持 | Local Desktop、SaaS Web、Mobile。 | `docs/archive/phases/specs/phase13/README.md` |
| AI 协作能力 | Rules、Spec、Skill、Dev Log。 | `docs/submission/03-AI协作开发记录.md` |

## 9. 测试

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

前端：

```powershell
cd frontend
npx tsc --noEmit
npm test
```

桌面端：

```powershell
cd desktop
npm run build
```

完整测试策略见 [docs/TEST_PROTOCOL.md](docs/TEST_PROTOCOL.md) 和 [docs/testing/UX_TEST_SPEC.md](docs/testing/UX_TEST_SPEC.md)。

## 10. 文档导航

| 想了解 | 阅读 |
| --- | --- |
| 产品是什么 | [docs/submission/01-产品设计文档.md](docs/submission/01-产品设计文档.md) |
| 技术怎么实现 | [docs/submission/02-技术设计文档.md](docs/submission/02-技术设计文档.md) |
| AI 协作怎么沉淀 | [docs/submission/03-AI协作开发记录.md](docs/submission/03-AI协作开发记录.md) |
| 答辩怎么准备 | [docs/submission/04-项目答辩核心掌握指南.md](docs/submission/04-项目答辩核心掌握指南.md) |
| 完整文档索引 | [CONTEXT.md](CONTEXT.md) |
| PRD | [docs/PRD/](docs/PRD/) |
| ADR 状态与决策 | [docs/adr/README.md](docs/adr/README.md) |
| 当前架构事实 | [docs/architecture/overview.md](docs/architecture/overview.md) |
| 数据模型 | [docs/architecture/data-model.md](docs/architecture/data-model.md) |
| 文档治理规范 | [docs/documentation-governance.md](docs/documentation-governance.md) |
| Phase 归档 | [docs/archive/phases/](docs/archive/phases/) |
| 规格归档 | [docs/archive/phases/specs/](docs/archive/phases/specs/) |
| 开发日志归档 | [docs/archive/phases/dev-logs/](docs/archive/phases/dev-logs/) |
