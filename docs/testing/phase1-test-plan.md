# Phase 1 测试计划：行走骨架

**版本**: v1.0
**日期**: 2026-05-26
**关联 Spec**: [phase1-skeleton-spec.md](../specs/phase1-skeleton-spec.md)
**关联协议**: [TEST_PROTOCOL.md](../TEST_PROTOCOL.md)

---

## 1. 测试范围

Phase 1 实现：会话 CRUD + 消息收发 + Claude SSE 流式对话。

### 涉及模块

| 模块 | 文件 | 测试重点 |
|------|------|---------|
| 会话 API | `backend/app/api/sessions.py` | CRUD + 参数校验 |
| 聊天 API | `backend/app/api/chat.py` | POST chat → SSE 流 + 异常分支 |
| 数据库模型 | `backend/app/models/` | 建表 + 外键 + 时间戳 |
| Agent 适配器 | `backend/app/agents/` | 接口契约 + ClaudeAdapter |
| 前端 Store | `frontend/src/stores/chat.ts` | 状态转换 |
| 前端组件 | `frontend/src/components/` | 渲染 + 交互 |
| API 客户端 | `frontend/src/api/client.ts` | fetch + SSE 解析 |

---

## 2. 测试用例清单

### 2.1 冒烟测试

#### S1 — 后端模块导入（✅ 已实现）

```python
# backend/test_smoke.py
def test_import_config():     # config 模块
def test_import_database():   # database 模块
def test_import_models():     # Session, Message 模型
def test_import_agents():     # BaseAgentAdapter, ClaudeAdapter, DeepSeekAdapter
def test_import_api_routes(): # sessions router, chat router
def test_import_main_app():   # FastAPI app 实例
```

#### S2 — 前端组件导入（Phase 2 实施）

前端 smoke test 和组件测试基础设施已安装（vitest + testing-library），具体测试用例将在 Phase 2 中编写。

---

### 2.2 API 测试（后端） — ✅ 全部实现

#### Sessions API

| ID | 端点 | 场景 | 预期 |
|----|------|------|------|
| A1 | `POST /api/sessions` | 正常创建 | 201, 返回 id/title/agent_name/created_at |
| A2 | `POST /api/sessions` | 自定义 title | 201, title 值正确 |
| A3 | `POST /api/sessions` | 默认值（不传 title） | 201, title="新对话" |
| A4 | `GET /api/sessions` | 空列表 | 200, 返回 [] |
| A5 | `GET /api/sessions` | 有一条记录 | 200, 返回含 1 项的列表 |
| A6 | `GET /api/sessions/{id}` | 存在的 session | 200, 返回详情 |
| A7 | `GET /api/sessions/{id}` | 不存在的 session | 404 |

#### Chat API

| ID | 端点 | 场景 | 预期 |
|----|------|------|------|
| B1 | `POST /api/sessions/{id}/chat` | 正常发送消息 | 200, SSE 流式输出 |
| B2 | `POST /api/sessions/{id}/chat` | SSE 每个事件是合法 JSON | 每个 `data:` 行可 `json.loads()` |
| B3 | `POST /api/sessions/{id}/chat` | 流完成后消息已持久化 | 查 messages 有 user + assistant 各一条 |
| B4 | `POST /api/sessions/{id}/chat` | 空 content | 400, error 含 "empty" |
| B5 | `POST /api/sessions/{id}/chat` | 不存在的 session | 404, error 含 "not found" |
| B6 | `POST /api/sessions/{id}/chat` | 多轮对话上下文 | 第 2 次请求携带历史消息 |
| B7 | `POST /api/sessions/{id}/chat` | 纯空格 content | 400 |

#### Messages API

| ID | 端点 | 场景 | 预期 |
|----|------|------|------|
| C1 | `GET /api/sessions/{id}/messages` | 空 session | 200, [] |
| C2 | `GET /api/sessions/{id}/messages` | 有消息的 session | 200, 返回消息列表含 id/role/content |
| C3 | `GET /api/sessions/{id}/messages` | 不存在的 session | 200, [] 或 404 |

---

### 2.3 前端组件测试

| ID | 组件 | 场景 | 预期 |
|----|------|------|------|
| D1 | ChatInput | 渲染输入框和发送按钮 | input + button 在 DOM 中 |
| D2 | ChatInput | 空内容点击发送 | `onSubmit` 不被调用 |
| D3 | ChatInput | 输入文字点击发送 | `onSubmit` 被调用，参数正确 |
| D4 | ChatInput | 流式中禁用 | `disabled=true` 时 input 和 button 都 disabled |
| D5 | SessionList | 渲染空列表 | 正常渲染，无 session 项 |
| D6 | SessionList | 渲染含 session 的列表 | 每项显示 title |
| D7 | SessionList | 点击新建按钮 | `onNewSession` 被调用 |
| D8 | SessionList | 点击某个 session | `onSelectSession` 被调用，传入选中的 id |
| D9 | MessageBubble | 渲染 user 消息 | 右对齐样式 |
| D10 | MessageBubble | 渲染 assistant 消息 | 左对齐样式 |
| D11 | MessageBubble | 渲染空内容（流式中） | 不崩溃，显示 loading 或空 |
| D12 | ChatWindow | 空消息列表 | 显示 "开始和 Claude 对话吧" |
| D13 | ChatWindow | 有消息时 | 渲染 MessageBubble × N |

---

### 2.4 Store 测试

| ID | Store 操作 | 场景 | 预期 |
|----|-----------|------|------|
| E1 | `setSessions` | 设置会话列表 | `sessions` 状态更新 |
| E2 | `setCurrentSessionId` | 切换会话 | `currentSessionId` 更新 |
| E3 | `appendMessage` | 追加一条消息 | `messages` 长度 +1 |
| E4 | `appendStreamingToken` | 没有消息时调用 | 状态不变，不崩溃 |
| E5 | `appendStreamingToken` | 最后一个不是 assistant | 状态不变 |
| E6 | `appendStreamingToken` | 最后一个消息是 assistant + isStreaming=true | assistant 消息 content 追加 token |
| E7 | `appendStreamingToken` | isStreaming=false | 状态不变 |
| E8 | `setIsStreaming` | true/false 切换 | `isStreaming` 正确更新 |

---

### 2.5 SSE 回归测试（针对已修复 Bug）

| ID | Bug | 回归测试 | 预期 |
|----|-----|---------|------|
| R1 | `{token!r}` 产生单引号 JSON | 逐行解析 SSE 的 `data:` 为 JSON | 全部解析成功 |
| R2 | 前端 GET → 405 | `createChatStream` 只发一次 POST | 不出现 GET 请求 |
| R3 | 重复 fetch 导致消息重复 | 验证最终只创建了 1 条 user + 1 条 assistant | messages 数量 = 2 |

---

### 2.6 手动验证清单（浏览器）

| ID | 验收项（来自 Spec） |
|----|-------------------|
| M1 | 打开网页 → 空会话列表 → 新建对话 → 会话出现在列表 |
| M2 | 发消息 → 3 秒内看到 AI 回复第一个字 |
| M3 | AI 回复流式逐字/逐块出现，滚动条自动跟随 |
| M4 | 第二条消息 AI 能引用第一条的内容 |
| M5 | 刷新页面 → 所有会话和消息保留 |
| M6 | 关闭页面再打开 → 回复完整显示 |
| M7 | API Key 未配置 → 前端显示错误提示（非白屏） |

---

## 3. 执行顺序

```bash
# 步骤 1: 冒烟测试（10 秒）
cd backend && pytest test_smoke.py -v
cd frontend && npx vitest run src/__tests__/smoke.test.ts

# 步骤 2: 后端 API 测试（2 分钟）
cd backend && pytest test_api/ -v

# 步骤 3: 前端组件 + Store 测试（2 分钟）
cd frontend && npx vitest run

# 步骤 4: 启动前后端 → 手动验证 M1-M7

# 步骤 5: 全部通过 → Phase 1 标记为 Completed
```

---

## 4. 测试环境准备

```bash
# 后端
cd backend
cp .env .env.test
# 编辑 .env.test: ANTHROPIC_API_KEY=test-key
#                  DATABASE_URL=sqlite+aiosqlite:///:memory:

# 前端
cd frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```
