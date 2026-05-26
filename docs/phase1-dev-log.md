# Phase 1 开发日志：行走骨架

**开发者**: Calmer2024
**阶段**: Phase 1 — Walking Skeleton
**日期范围**: 2026-05-25 ~ 2026-05-26
**开发模式**: Vibe Coding + AI Agent 协作（Claude Code）

---

## 1. 阶段概述

从零搭建 AgentHub 项目骨架，打通第一条完整链路：用户通过 IM 界面发送消息 → 后端调用 Claude API → SSE 流式返回 → 前端实时渲染。证明全栈技术选型可行。

### 1.1 交付成果

| 模块 | 内容 | 规模 |
|------|------|------|
| 后端 API | FastAPI + SQLite + SSE Streaming | 14 个源文件 |
| 前端界面 | React + Vite + shadcn/ui + Zustand | 10 个源文件 |
| 测试套件 | pytest + httpx AsyncClient | 28 条测试，0.17s 全量通过 |
| 规范文档 | ADR × 7、Spec × 1、协议 × 4 | ~3000 行文档 |
| Git 提交 | 按粒度拆分的规范化提交 | 7 个 commit |

---

## 2. 开发时间线

### Day 0（项目准备）

- [x] 确定技术栈：React + FastAPI + SQLite + Claude API
- [x] 设计 7 层目标架构（Phase 1 仅启用 3 层）
- [x] 定义 Phase 1 范围：单聊全链路，Claude only，SSE 流式
- [x] 创建项目目录结构

### Day 1（核心链路）

- [x] 后端：数据库模型 (Session + Message) + SQLAlchemy async
- [x] 后端：Agent 适配器接口 (BaseAgentAdapter) + ClaudeAdapter + DeepSeekAdapter
- [x] 后端：Sessions CRUD API (POST/GET/GET-by-id)
- [x] 后端：Chat SSE 流式 API (POST /sessions/{id}/chat)
- [x] 后端：Messages API (GET /sessions/{id}/messages)
- [x] 前端：React + Vite + shadcn/ui 项目初始化
- [x] 前端：Zustand 状态管理 (chat store)
- [x] 前端：SessionList + ChatWindow + MessageBubble + ChatInput 组件
- [x] 前端：SSE 流式读取客户端
- [x] 前后端联调通过——第一条 AI 消息流式返回成功

### Day 2（质量加固 + Bug 修复）

- [x] Bug修复：Python 3.9 兼容性 — `dict | None` 语法 (PEP 604) → 升级 Python 3.12
- [x] Bug修复：SSE JSON 格式 — `{token!r}` 产生单引号 → 改用 `json.dumps()`
- [x] Bug修复：前端请求方式 — EventSource GET → 405 → 改用 fetch POST + reader
- [x] Bug修复：前端重复请求 — 3 个重复 fetch → 删掉 2 个死代码
- [x] Test基础设施：pytest + httpx + conftest 夹具 + Mock Agent
- [x] Test套件：28 条 API 测试 + 10 条冒烟测试
- [x] UX优化：打字指示器动画 + 空状态引导 + 错误显示 + 流式状态横幅

---

## 3. 遇到的 Bug 与解决方案

### Bug #1：后端启动 crash — `TypeError: unsupported operand type(s) for |`

**现象**：`uvicorn` 启动时 `base.py:21` 报错，`dict | None` 语法不支持。

**根因**：venv 使用 miniconda3 的 Python 3.9.1。PEP 604 的 `X | None` 语法需要 Python 3.10+。

**解决**：用系统 Python 3.12.9 重建 venv。这同时修复了 conda 的 `_ssl` DLL 缺失问题。

**教训**：项目应声明 `requires-python >= 3.12`，CI 中校验 Python 版本。

### Bug #2：前端 405 Method Not Allowed + 消息重复

**现象**：
1. 发送消息后控制台报 `GET /api/sessions/{id}/chat 405`
2. AI 不回复
3. 刷新网页后，消息出现两次，AI 也回复了两次

**根因**：`client.ts` 的 `createChatStream` 函数里有 3 个 HTTP 请求：
- ① `EventSource(url + queryString)` → 发 GET，后端只有 POST → 405
- ② `fetch POST`（丢弃 response）→ 把消息又发了一遍
- ③ `fetch POST`（SSE reader）→ 唯一正确工作的请求

**解决**：删除 ① 和 ②，只保留正确的 SSE reader。

**教训**：死代码堆积是隐患。EventSource 不支持 POST，留下了废弃尝试。Code Review 应对"无消费的 fetch"零容忍。

### Bug #3：流式回复无 UI 反馈

**现象**：
1. 发送消息后，AI 气泡显示灰色空白框
2. 无任何"思考中"指示
3. 等待数秒后内容突然出现——用户会以为界面卡死

**根因**：
- 后端：`{token!r}` 产生单引号 JSON，前端 `JSON.parse` 全部失败并静默吞掉
- 前端：`catch` 块无 `console.warn`，错误不可见
- 前端：`MessageBubble` 在空 content 时无加载指示器
- 前端：流式异常结束时 `onDone` 从未被调用

**解决**：
1. 后端 4 处 `yield` 全部改用 `json.dumps()` 生成合法 JSON
2. 前端 `catch` 改为 `console.warn`
3. 前端 `MessageBubble` 添加三个跳动圆点动画
4. 前端 stream 结束后加 `onDone` 兜底调用

**教训**：
- Python 的 `repr()` 和 JSON 的 `"` 不兼容，必须用 `json.dumps`
- 静默 `catch` 是调试地狱——至少打一行日志
- 用户体验问题也是 Bug，不是"以后优化"

### Bug #4：HTTPException 在 StreamingResponse 中失效

**现象**：400/404 测试失败，`HTTPException` 被包装成 500。

**根因**：`HTTPException` 在 `StreamingResponse` 的 generator 内抛出时，被 Starlette 的 ExceptionGroup 包装，httpx 看到的是 500。

**解决**：将校验逻辑（空内容、不存在的 session）从 generator 移到路由 handler。generator 只负责流式输出。

**教训**：StreamingResponse 的 generator 不适合做业务校验。校验逻辑应在进入 generator 之前完成。

---

## 4. 建立的项目基础设施

### 4.1 规范文档体系

| 文档 | 类型 | 作用 |
|------|------|------|
| ADR × 7 | 架构决策 | 记录技术选型、目录结构、开发方法、AI 协作系统 |
| Phase 1 Spec | 功能规格 | 定义输入输出、行为规格、验收标准、Non-Goals |
| TEST_PROTOCOL | 测试协议 | 金字塔模型、工具链、环境规范、Bug 修复流程 |
| UX_TEST_SPEC | UX 规范 | 6 状态覆盖模型、Chat 场景检查清单、P0-P3 分级 |
| GIT_PROTOCOL | Git 规范 | 分支策略、Commit 格式、三关强制验证流程 |

### 4.2 测试基础设施

```
28 tests in 0.17s — 全部通过，零警告
  Session API: 7 ✓
  Chat API:   11 ✓ (含 SSE JSON 回归测试)
  Smoke:      10 ✓
```

### 4.3 AI 协作体系

| 层级 | 文件 | 状态 |
|------|------|------|
| Rules | CLAUDE.md, CONTEXT.md, .trae/rules/ | 已建立 |
| Spec | docs/specs/phase1-skeleton-spec.md | 已完成 |
| Skills | agenthub-module-dev, agenthub-code-review | 已建立 |

---

## 5. 关键方法总结

### 5.1 Vibe Coding 实践心得

1. **Phase 0 不可跳过**：接口契约和骨架定义虽然"不写代码"，但避免了 Day 1 的方向错误
2. **小步快跑**：每完成一个函数就 commit，不攒大 diff。发现回退成本极低
3. **测试即文档**：测试用例精确对应用户可见的验收标准，不是形式主义

### 5.2 AI 协作心得

1. **Spec 先行**：没有 Spec 的 AI 开发 = 盲飞。Spec 给了 AI 明确边界
2. **Prompt 要具体**："修复这个 bug" → 差。"这个函数有 3 个请求，删掉前两个" → 好
3. **AI 适合做增量修改**，不适合一次重构整个模块
4. **AI 提交代码必须有 `[ai]` 标记** + 人类 review

### 5.3 项目治理心得

1. **协议文档比代码注释重要**：TEST_PROTOCOL、GIT_PROTOCOL 是"活"的规范，不是写完就归档的
2. **Bug 修复必须有回归测试**：每个 Phase 1 Bug 都有对应的测试用例
3. **UX 测试和功能测试同等权重**：功能正确 ≠ 体验正确

---

## 6. 下一步 (Phase 2)

- [ ] 多 Agent 支持（切换 Claude/DeepSeek）
- [ ] 群聊模式 + Orchestrator
- [ ] 产物预览卡片
- [ ] WebSocket 实时通信
- [ ] E2E 测试 (Playwright)
