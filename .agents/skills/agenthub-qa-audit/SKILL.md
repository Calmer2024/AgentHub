---
name: agenthub-qa-audit
description: AgentHub 企业级质量审计流程。当用户说"质量审计"、"QA audit"、"验收测试"、"审核测试"、"真实测试"或完成一轮开发后进行。不是局部代码正确性测试——而是启动项目、浏览器自动化、端到端业务链路审核、UX 状态覆盖检查、启发式问题发现、修复闭环验证。
---

# AgentHub 企业级质量审计 (QA Audit)

你是一位**企业级测试专家**。你的职责不是验证某个函数对不对（那是 pytest/vitest 的工作），而是回答一个问题：

**这一轮开发是否真正完成了任务？有没有偷工减料？核心业务链路是否打通？**

当前 `pytest test_api/` + `pytest test_unit/` + `npx vitest run` + `npx tsc --noEmit` 四者必须全部通过后，你的审计才开始。

## 审计原则

| 原则 | 含义 |
|------|------|
| **不信任声明，只信任证据** | 代码里写了"已完成"不代表真的完成了。你要亲自启动项目、点击界面、检查网络请求。 |
| **端到端优先** | 不评审单个模块。追踪从用户输入 → API → 业务逻辑 → 数据持久化 → 前端渲染的全链路。 |
| **体验即功能** | 界面空白、按钮无反馈、错误信息是英文——这些不是"优化项"，是 **bug**。 |
| **启发式攻击** | 主动寻找问题：极端输入、快速操作、并发点击、网络断开。不等待用户告诉你哪里有问题。 |
| **修复闭环** | 发现问题 → 定位根因 → 修复 → 回归验证，不留下已知缺陷。 |

## 审计范围定义

### 你做

- 启动真实后端 + 前端服务
- 浏览器自动化 (Playwright) 交互测试
- SSE 事件协议逐帧验证
- API 请求/响应格式检查
- 组件 6 状态覆盖 (空/加载/正常/完成/错误/边界)
- 跨模块数据流追踪（数据类型是否在各层一致）
- 错误路径演练（Agent 不可用、超时、空响应）
- 前端 JS 控制台错误扫描
- 发现 Bug → 修复 → 回归

### 你不做

- 单元测试或组件测试（pytest/vitest 已经覆盖）
- 代码风格审查（agenthub-code-review 负责）
- 性能基准测试
- 安全渗透测试

## 审计工作流（4 阶段）

### 阶段 1: 代码架构审查（只读）

```
目标: 确认本轮开发声称完成的内容与实际代码一致
方法: 交叉阅读 Spec/ADR + 源代码，不运行
输出: 架构成熟度报告
```

**1.1 Spec-代码映射**

将 Spec/ADR 中声明的每项功能，逐条映射到实际文件：

```
| Spec 声明 | 对应文件 | 状态 |
|-----------|---------|------|
| "IntentAnalyzer 独立类" | domain/intent_analyzer.py | ✅ 存在 |
| "Agent 元数据匹配" | domain/agent_selector.py L42-68 | ✅ 实现 |
| "链式自动触发" | domain/execution_planner.py L133-169 | ✅ 实现 |
```

**1.2 Import 链完整性**

从入口点向下追踪 import 链，检查是否有断裂：
- `main.py` → `api/chat.py` → `chat_service_impl.py` → `orchestrator_v2.py` → 4 个组件
- `App.tsx` → `client.ts` → `types/index.ts`
- 验证所有 import 的目标文件确实存在且导出正确

**1.3 遗留代码扫描**

- 搜索已删除模块的残留引用 (grep 旧类名/文件名)
- 检查是否有未被使用的"死文件"
- 验证 V1→V2 迁移的完整性

**1.4 数据类型跨层一致性**

追踪核心数据结构从前端到后端每一层的定义：

```
TypeScript type → Pydantic schema → Domain dataclass → SQLAlchemy model
```

验证：字段名 (camelCase alias)、类型、必填/可选 在各层一致。

### 阶段 2: 真实环境启动

```
目标: 确认项目能真实运行，无启动错误
方法: 启动后端 + 前端，健康检查
```

**2.1 后端启动检查**

```bash
# 0. 端口冲突预检 (Windows)
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# 1. Import 检查
cd backend
python -c "from app.main import app; print('Import OK')"

# 2. 启动
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

验证：
- [ ] lifespan 事件无异常
- [ ] 数据库迁移全部执行
- [ ] EventBus 启动无错误
- [ ] `GET /api/agents` 返回 Codex / Codex / OpenCode CLI 好友
- [ ] `GET /api/settings` 返回 `systemModel.provider=deepseek`
- [ ] `GET /api/sessions?includeArchived=true` 返回会话 IM 状态字段（isPinned/archivedAt/unreadCount/isMuted）

**2.2 前端启动检查**

```bash
cd frontend
npx vite --host 127.0.0.1 --port 5173
```

验证：
- [ ] 首页渲染无白屏
- [ ] 浏览器控制台无 JS Error (排除 favicon)
- [ ] 所有组件正常挂载

### 阶段 3: 业务链路端到端审计

```
目标: 每个核心用户场景的完整链路追踪
```

**3.1 场景定义**

从 Spec/ADR 中提取本轮开发的用户场景，每个场景定义预期行为链：

```
场景: 群聊智能路由
用户操作: 在群聊中输入"帮我写一个React登录组件"
预期链路:
  1. POST /sessions/{id}/chat → 200
  2. SSE: orchestrator.route → [{id, name}]
  3. SSE: orchestrator.task_started → {intent, tasks}
  4. SSE: agent.start → {agentId, messageId}
  5. SSE: token 流 → 累积为完整响应
  6. SSE: orchestrator.task_completed → {summary}
  7. 前端: Orchestrator 横幅可见
  8. 前端: CollaborationView 渲染 Agent 卡片
  9. 前端: 意图标签正确显示
```

**3.2 SSE 协议逐帧验证**

使用 `requests.post(stream=True)` 直接读取 SSE 流，逐事件验证：

- [ ] 事件顺序正确 (route → task_started → agent.start → tokens → agent.done → task_completed)
- [ ] 每个事件 JSON 合法
- [ ] 事件字段完整（不缺少必填字段）
- [ ] per-agent done 事件不终止前端流（`data.done && !data.agentId` 才终止）

**3.3 浏览器交互验证**

使用 Playwright headless 模式：

- [ ] 页面加载无错误
- [ ] 关键 UI 元素可见
- [ ] 按钮可点击
- [ ] 输入框可用（不被 disabled 阻塞）
- [ ] 消息发送成功
- [ ] 响应在合理时间内出现
- [ ] Agent 名称/角色标签正确显示

**3.4 错误路径演练**

至少覆盖：
- [ ] Agent 不可用 → 显示 `[Agent名 不可用]`
- [ ] 所有 Agent 失败 → 显示 "所有 Agent 均无法响应"
- [ ] 空消息 → 400 错误
- [ ] 不存在的 Session → 404 错误
- [ ] 链式步骤中断 → 保留已完成步骤 + 中断事件

### 阶段 4: UX 体验审计

```
目标: 6 状态模型覆盖检查
```

对每个用户可见组件，检查：

| 状态 | 检查项 | 标准 |
|------|--------|------|
| **空状态** | 首次进入 | 有引导文案 + 行动入口，不是空白 |
| **加载中** | AI 回复中 | 打字指示器/脉冲动画可见，输入框禁用 |
| **正常态** | 常规交互 | 内容可读，操作可点击 |
| **完成态** | 流式结束 | 指示器消失，输入框恢复，内容完整 |
| **错误态** | API 失败 | 中文错误说明 + 重试/返回入口 |
| **边界态** | 极长输入/快速切换 | 不崩溃、不丢失数据 |

**4.1 具体检查清单**

- [ ] 发送消息时：按钮变灰/禁用 + placeholder 变为 "AI 正在回复..."
- [ ] 流式完成时：指示器消失 → 输入框恢复 → 内容完整显示
- [ ] 错误时：红色横幅 + 中文错误信息 + 关闭按钮
- [ ] CollaborationView: 折叠/展开正常，状态圆点颜色正确
- [ ] Orchestrator 横幅: 意图标签显示、Agent 名称 tag 显示
- [ ] 群聊创建: 2-5 个 Agent 可选，无链式开关（自动触发）
- [ ] 会话列表: 置顶分组、归档箱、未读徽标、免打扰、搜索、最近活跃排序可见且刷新后保持
- [ ] 消息右键菜单: 引用/重新生成/Pin/复制/转发/多选菜单不被滚动容器裁剪
- [ ] 执行过程全屏: 可打开、滚动、关闭，无遮挡

**4.2 前端控制台扫描**

使用 Playwright 的 `page.on("console")` 捕获所有 JS Error：
- [ ] 无 TypeError/ReferenceError
- [ ] 无 "cannot read property of undefined"
- [ ] STATUS_CONFIG[undefined] 等运行时异常已防御

### 阶段 5: 问题修复闭环

**5.1 Bug 分级**

| 级别 | 定义 | 处理 |
|------|------|------|
| 🔴 阻断 | 核心功能不可用、页面崩溃、数据丢失 | 立即修复 |
| 🟡 中等 | 功能可用但结果不正确、错误信息丢失 | 本轮修复 |
| 🟢 低 | 体验不佳、缺少反馈、非关键路径 | 记录，下轮修复 |

**5.2 修复流程**

```
发现 Bug → 定位根因（不是表象）→ 修复 → 全量回归 (pytest + vitest + tsc) → 重新 E2E 验证 → 确认闭环
```

**5.3 修复约束**

- 修复不引入新 `any` 类型
- 修复不绕过类型检查
- 修复不破坏分层架构
- 修复后全量测试必须零回归

## 审计输出格式

```
=== AgentHub QA Audit Report ===
日期: {date}
审计范围: {本轮开发内容}

--- 阶段 1: 架构审查 ---
✅/{total} 通过
（逐项列出）

--- 阶段 2: 环境启动 ---
✅/{total} 通过

--- 阶段 3: 业务链路 ---
✅/{total} 通过

--- 阶段 4: UX 审计 ---
✅/{total} 通过

--- Bug 清单 ---
| # | 严重度 | 描述 | 状态 |
（列出所有发现并修复的 Bug）

--- 回归验证 ---
Backend:  pytest → {N} passed
Frontend: tsc → 0 errors, vitest → {N} passed
E2E:     {N}/{N} 通过

=== 结论 ===
{通过 / 未通过}
{若未通过，列出阻塞项}
```

## 审计命令速查

```bash
# 后端启动
cd backend && .venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000

# 前端启动
cd frontend && npx vite --host 127.0.0.1 --port 5173

# 全量回归
cd backend && .venv\Scripts\python.exe -m pytest test_unit/ test_api/ -q
cd frontend && npx tsc --noEmit && npx vitest run

# Playwright E2E (headless)
$env:PYTHONIOENCODING='utf-8'
cd {project} && .venv\Scripts\python.exe e2e/orchestrator_audit.py

# SSE 事件验证
python -c "import requests,json; r=requests.post(f'{API}/sessions/{sid}/chat',json={...},stream=True); [print(json.loads(l[6:]).get('type','token')) for l in r.iter_lines(decode_unicode=True) if l.startswith('data: ')]"
```

## 审计后环境清理

**每次审计结束后必须执行，不留后台进程占用端口：**

```powershell
# 停止后端
Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force

# 停止前端 (Vite dev server 通常是 node 子进程)
Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*vite*" } | Stop-Process -Force

# 释放端口
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# 确认端口已释放
netstat -ano | findstr ":8000"
netstat -ano | findstr ":5173"
```

**清理确认清单：**
- [ ] 后端 uvicorn 进程已停止
- [ ] 8000 端口已释放
- [ ] 5173 端口已释放
- [ ] 临时测试 session 数据无需清理（项目使用文件数据库，下次启动自动重置）

## 关联文档

- [TEST_PROTOCOL.md](../../docs/TEST_PROTOCOL.md) — 测试金字塔、工具链、Mock 规范
- [UX_TEST_SPEC.md](../../docs/testing/UX_TEST_SPEC.md) — 6 状态模型、体验三定律
- [AGENTS.md](../../AGENTS.md) — 项目规则（自动化优先、禁止项）
- [CONTEXT.md](../../CONTEXT.md) — 领域术语定义

## Phase 7D 审计 (2026-06-07)

- 引用仍有效：`docs/TEST_PROTOCOL.md`、`docs/testing/UX_TEST_SPEC.md`、`AGENTS.md`、`CONTEXT.md` 均存在。
- 审计清单已补 Phase 7D IM 主链路：会话置顶/归档/未读/免打扰、消息右键菜单、转发/多选、执行过程全屏。
- 真实服务验收需额外检查明亮主题纯白辅色、输入框外层透明、文件视图全屏布局和归档菜单层级遮挡问题。
