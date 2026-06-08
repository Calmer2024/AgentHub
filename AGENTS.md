# AGENTS.md

## 项目：AgentHub — 多 Agent 协作平台

IM 式聊天平台，用户可与 AI Agent（Claude Code、Codex、OpenCode 等）对话，支持群聊协作调度与产物预览。

> **项目全局上下文**（领域术语、架构总览、Phase 状态、完整文档索引）见 [CONTEXT.md](CONTEXT.md)。首次参与本项目的开发者/Agent 必须先阅读 CONTEXT.md，再阅读本文件。

---

## 文档语言规则

| 文档类型 | 语言 | 说明 |
|---------|------|------|
| **AGENTS.md** | 中文 | AI Agent 行为规则 |
| **CONTEXT.md** | 中文 | 领域知识 + 文档索引 |
| **ADR** (架构决策记录) | 中文 | 架构决策及原因 |
| **Spec** (功能规格) | 中文 | 各 Phase 的功能规格与验收标准 |
| **PRD** (产品需求文档) | 中文 | 产品需求 |
| **Dev Log** (开发日志) | 中文 | 开发时间线与教训 |
| **Skill** (技能文件) | 中文 | 可复用的 AI 工作流 |
| **代码注释** | 中文 | 所有 `.py` / `.ts` / `.tsx` 中的注释 |

> 以上规则取代此前"AI-facing docs in English, human-facing docs in Chinese"的旧约定。全项目统一中文，降低维护负担，消除中英混杂导致的表述不一致。

---

## 架构约束

### 分层依赖（只能向下，不能向上）

```
前端 (React) → API 网关 (FastAPI) → 业务逻辑 (Service) → 领域核心 (Domain) → 基础设施 (Infrastructure) → 数据持久化 (Data)
```

### 核心规则

- 模块只能依赖下层，绝不依赖上层。
- 同层模块通过接口或 EventBus 通信，禁止直接导入。
- Domain 层是纯逻辑：不依赖 FastAPI、SQLAlchemy 等框架。
- 架构按需增长：Phase 1 仅 3 层，复杂度达到触发条件时才引入新层（见 ADR-0004）。
- 接口契约（ADR-0005）稳定不变，实现可自由迭代。
- PRD-01 是底层 Agent 架构的唯一权威：AgentHub 是 CLI-Wrapper 调度壳，通过 PTY/subprocess 封装真实物理工具（Anthropic `Codex` CLI、OpenAI `codex` CLI、开源 `opencode`）。AgentHub 绝不裸调 HTTP LLM API 作为 Agent——那是 PRD-00/01 明确否决的"伪 Agent"反模式。
- 消息操作必须是真实的 Agent 上下文，不能只是 UI 状态。Reply 保存引用消息快照并注入 `[Reply context]` 到 prompt；Pin 通过 `ContextManager` 注入 `[Pinned message]`。

---

## 技术栈（锁定）

| 层 | 技术 |
|----|------|
| 前端 | React + TypeScript + Vite + shadcn/ui + Tailwind CSS v3 |
| 后端 | Python FastAPI + WebSocket |
| 数据库 | SQLite + SQLAlchemy 2.0（async with aiosqlite） |
| 桌面 | Tauri v2 |
| 移动 | Capacitor |
| AI SDK | anthropic (Python), @anthropic-ai/sdk (TypeScript) |

---

## 代码规则

### 通用

- 所有代码注释用中文。
- 避免单个源文件臃肿：行数是代码气味提示，不是硬性上限。只有当文件承担多个职责、难以测试或难以局部理解时才拆分；职责清晰的长文件不为追数字而硬拆。
- 每个模块完成后立即写单元测试。
- 小步提交：每个可运行函数 = 一次 commit。
- **自动化优先**：任何功能设计在前端上的体现是让任务尽量自动化处理，不要让用户做太多配置。复杂决策（链式触发、角色分配、Agent 选择）由后端自动完成。

### 每轮结束服务交接（硬性要求）

每轮开发/修复结束必须完成以下流程：

1. **清理旧进程**：检查后端（默认 `127.0.0.1:8000`）和前端（默认 `127.0.0.1:5173`）端口，停止运行旧代码的进程。
2. **启动当前代码服务**：
   - 后端：用项目 Python 环境运行当前 `backend/app/main.py`
   - 前端：运行当前 Vite 应用（`frontend/`）
   - 若默认端口被占用，使用下一个空闲端口并明确报告
3. **在真实服务上验证**：检查后端根路径/OpenAPI、前端根路径、`/api` 代理、以及改动功能的真实验收路径。不能只依赖单元测试或临时 ASGI 客户端。
4. **报告访问地址**：始终给出前端 URL、后端 URL、API 文档 URL，和任何端口变更。

旧进程仍在运行旧代码、或未提供服务 URL，本轮不结束。

### Python（后端）

- Pydantic v2 做请求/响应校验。空消息 → 400；不存在的 session → 404。
- 全异步：所有路由 handler 和 Service 方法用 `async def`。
- 环境变量通过 `python-dotenv` 管理，绝不硬编码 API Key。
- 用户可见 Agent 适配器只遵循 CLI 事件契约：真实进程执行、stdout/stderr 解析、交互提示、标准事件输出。DeepSeek 只通过后端 SystemLLM 使用，不属于用户 Agent 适配器。
- 测试要依赖真实数据库文件。每个测试自己创建所需 fixtures。

### TypeScript（前端）

- 禁止 `any` 类型。用 `unknown` 做不确定类型，然后收窄。
- Zustand 管理状态，每个领域一个 store（chat、sessions 等）。
- 组件仅使用 shadcn/ui 原语，自定义样式通过 Tailwind 类。
- API 客户端：带类型的 fetch 封装；SSE 用 EventSource + 重连逻辑。

---

## 文档规则

项目文档遵循**渐进式披露**策略：

1. **按细节深度分层，不是按主题**。入口文档（AGENTS.md、CONTEXT.md）提供概览并往下链接。ADR 解释决策。Spec 定义精确需求。Dev Log 记录历史。
2. **概括，不复制**。下游文档可概括上游概念并链接，但绝不复制全文。一个事实一个权威源。
3. **交叉引用，不重复声明**。若规则/决策已在其他文档中存在，链接过去而非重述。
4. **先索引，后细节**。每个文档目录都有索引，读者无需通读全文就能找到所需内容。
5. **新文档必须证明存在价值**。创建新文档前先问：能放入已有文档吗？能 → 修改已有；不能 → 新建并加入索引。
6. **文档修改必须全局重构，禁止局部修补**。修改文档某一部分时，必须通读全文，检查并更新所有与修改内容矛盾的旧描述。不允许同一文档中 A 段落说"本文件只定义 X"、B 段落却同时定义了 Y。每次文档修改的终点是一份整体逻辑自洽的文档。不允许打补丁式修改文档。

---

## 禁止事项

- 构建"以后可能用到"的抽象 — 只构建当前 Phase 需要的。
- 在定义接口契约前写实现代码。
- 结束增量时没有可演示的前端。
- 跳过验收标准就标记 Phase 完成。
- 添加当前 Spec 范围之外的功能。
- 结束开发轮次时仍有旧后端/前端进程在运行旧代码，或未报告服务访问 URL。
- **执行任何 Git 操作（add/commit/push）前，必须先获得用户明确的"人工验收"确认。** 即使模块开发 Skill 中已进入 Step 6，也必须等待用户说"人工验收认可"/"验收通过"/"批准提交"等确认口令。未获确认前，Git 操作等同于 Spec 之外的功能——禁止执行。

---

## Debug 质量守则

Debug 不是"让 bug 消失"，而是"让系统更正确"：

1. **修根因，不修表象** — 找到问题的系统性原因（如字段命名不一致、架构设计缺陷），不写补丁式修复。
2. **保持代码质量不降级** — 修复不能引入 `any`、绕过类型检查、破坏分层架构、添加临时 hack。
3. **前瞻性** — 修复方案要考虑同一类问题在项目中其他地方是否也存在，一并修复。
4. **全局性** — 一个 bug 修复后，检查相关联的模块是否受影响（运行全量测试，不仅是相关测试）。
5. **安全性** — 不为了"快速修复"而降级 API Key 校验、跳过输入验证、暴露错误详情给前端。
6. **字段命名一致性** — 前后端字段名必须严格一致。后端 Pydantic 模型必须用 `Field(alias="camelCase")` + `populate_by_name=True` 统一输出 camelCase。
7. **每轮修复后全量测试零回归** — `pytest test_api/` + `npx vitest run` + `npx tsc --noEmit` 三者必须全部通过。
8. **主动发现问题** — 用户的验收反馈是片面的，不应只修复用户提出的问题。必须从用户反馈延申出去，主动审查相关功能是否存在同类设计缺陷、UI/UX 问题、边界条件遗漏。从"这段代码还能怎么出问题"的角度思考，而不是"用户说了什么我就修什么"。

---

## AI 协作体系

三层协作体系：Rules（始终生效）→ Spec（按功能加载）→ Skill（按需调用）

| 层 | 文件位置 | 生效时机 | 用途 |
|----|---------|---------|------|
| **Rules** | `AGENTS.md`、`.trae/rules/project_rules.md` | 每次 AI 对话 | 技术栈锁定、架构约束、代码规则、禁止事项 |
| **Spec** | `docs/specs/phaseN/` | 按功能开发 | 定义要构建什么、输入输出、行为、验收标准、非目标 |
| **Skill** | `.agents/skills/*.md`（`.claude/skills/` 保留镜像） | 按需调用 | 标准化开发流程、代码审查清单 |

---

## 阶段感知

当前处于 **Phase 10（Sandbox Runner 与云端 Agent Runtime）准备期**。Phase 8 P1 发布候选收口已完成并通过真实服务验收；Phase 9 Cloud Workspace Foundation 已落地 P2 用户/团队/RBAC、CloudWorkspaceProvider、workspace 导入/快照/恢复、审计日志，并完成 P1 local 零回归验收。下一阶段只能在 Phase 9 的 `workspaceId` / RBAC / audit 基座上接入云端 sandbox 与真实 CLI Runtime，不能回退到裸 HTTP LLM API，也不能破坏 P1 本地 `workspace_path` 主路径。

完整 Phase 状态表见 [CONTEXT.md §开发阶段](CONTEXT.md)。

### 产品交付阶段

| 优先级 | 产品形态 | 架构 | 一键部署 |
|--------|---------|------|---------|
| **P1（当前）** | **桌面版**：桌面端（Tauri/Node.js）= 本地无头服务器 + 本地特权执行引擎；Web 端（浏览器）= 主力 UI | 浏览器 → localhost 后端 → 本机文件系统 + 本机 CLI Agent | ❌ |
| **P2（正在铺设基座）** | **SaaS 云版**：Web 浏览器 + 云端后端 + 云端容器沙箱 | 浏览器 → 云端后端 → 云端沙箱 + 云端 CLI Agent → 云端 URL | ✅ |

**Project-first 工作流**：用户必须先创建 Project，然后在 Project 下创建私聊或群聊。P1 本地 Project 使用新建空白 workspace 目录或系统原生目录选择器绑定已有目录，Project 内所有本地 Agent 共享 `Project.workspace_path` 作为 `cwd`；P2 云端 Project 使用 `workspaceId` 和 `cloud://agenthub/workspaces/{id}` 逻辑 URI，前端不应看到服务器或用户本机物理路径。Project 不再暴露“静态网页 / Vite React / 已有项目”等用户可选属性。详见 [ADR-0009](docs/adr/0009-project-workspace-model.md) 与 [Phase 9 Spec](docs/specs/phase9/README.md)。

> 完整的 P1/P2 定义、Workspace 位置、运行环境、安全边界见 [CONTEXT.md §产品交付阶段](CONTEXT.md)。
