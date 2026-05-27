# ADR-0006: Phase 1 行走骨架 —— 单聊全链路

**Date**: 2026-05-25
**Status**: Accepted

## Context

根据 ADR-0004 的行走骨架原则，Phase 1 的目标是打通一条最薄的全链路，验证技术选型和架构方向可行。不实现任何业务功能的完整性，只证明"前端 → API → Agent → 数据库"能跑通。

## Decision

### 行走骨架定义：第一条完整链路

```
用户打开网页 → 看到会话列表 → 新建对话(选择 Agent) → 输入文本消息
→ 点击发送 → 后端接收 → 查询会话历史 → 调用 Claude API(流式)
→ 每个 token 实时推送到前端 → 前端逐字展示 → 消息持久化到 SQLite
```

### 涉及的技术组件

| 组件 | 做什么 | 技术选型 |
|------|--------|---------|
| React 前端 | 会话列表 + 聊天窗口 + 流式渲染 | React + Vite + shadcn/ui + Tailwind |
| FastAPI 路由 | `POST /sessions` `POST /chat/{session_id}` | FastAPI + SSE |
| Claude Adapter | 封装 Claude SDK，实现 `BaseAgentAdapter` | `anthropic` Python SDK |
| SQLite | 存 Session、Message 两张表 | SQLAlchemy 2.0 + aiosqlite |
| 流式传输 | 后端 SSE → 前端 EventSource 接收 | SSE (Server-Sent Events) |

> **为什么 Phase 1 用 SSE 而不是 WebSocket？** SSE 实现更简单（纯 HTTP），Phase 1 只需单向推送（Server→Client），不需要双向通信。WebSocket 在 Phase 2.2 群聊场景引入。

### 明确不实现的内容

- ❌ 群聊模式、Orchestrator
- ❌ WebSocket（用 SSE 代替）
- ❌ 多 Agent 切换（硬编码 Claude 一个 Agent）
- ❌ 消息引用、重新生成、Pin
- ❌ 产物预览卡片（所有消息都是纯文本）
- ❌ 文件附件、代码 Diff、部署
- ❌ 用户认证、多用户
- ❌ Service 层、Event Bus、Context Manager
- ❌ 任何 P1/P2 功能

### 数据库表（最小集）

```sql
-- Session 表：一个对话会话
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New Chat',
    agent_name TEXT NOT NULL DEFAULT 'claude',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Message 表：一条消息
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### API 端点（最小集）

```
POST   /api/sessions              → 创建新会话
GET    /api/sessions              → 获取会话列表
GET    /api/sessions/{id}         → 获取单个会话详情
GET    /api/sessions/{id}/messages → 获取会话历史消息
POST   /api/sessions/{id}/chat    → 发送消息并流式返回 (SSE)
```

### 前端页面（最小集）

```
/                    → 主页面（左侧会话列表 + 右侧聊天窗口）
聊天窗口内容:
  - 顶部：Agent 名称 + 会话标题
  - 中间：消息列表（用户消息靠右，Agent 回复靠左，流式逐字出现）
  - 底部：输入框 + 发送按钮
会话列表:
  - 新建对话按钮
  - 会话项（标题、最后活跃时间）
  - 点击切换当前会话
```

### 后端目录结构（Phase 1 实际实现）

遵循 ADR-0002 的整体结构，但 Phase 1 只有最少的文件：

```
backend/
├── app/
│   ├── main.py              # FastAPI app 入口，CORS 配置
│   ├── config.py            # 环境变量、API Key 读取
│   ├── database.py          # SQLAlchemy engine + session factory
│   ├── models/
│   │   ├── __init__.py
│   │   ├── session.py       # Session ORM model
│   │   └── message.py       # Message ORM model
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py          # BaseAgentAdapter (接口定义，从 ADR-0005 拷贝)
│   │   └── claude_adapter.py # ClaudeAdapter 实现
│   └── api/
│       ├── __init__.py
│       ├── sessions.py      # Session CRUD 路由
│       └── chat.py          # 聊天路由（含 SSE 流式）
└── requirements.txt
```

### 前端目录结构（Phase 1 实际实现）

```
frontend/
├── src/
│   ├── App.tsx              # 路由 + 布局
│   ├── main.tsx             # 入口
│   ├── api/
│   │   └── client.ts        # fetch 封装，SSE EventSource 工具函数
│   ├── components/
│   │   ├── SessionList.tsx   # 左侧会话列表
│   │   ├── ChatWindow.tsx    # 右侧聊天窗口
│   │   ├── MessageBubble.tsx # 单条消息气泡
│   │   └── ChatInput.tsx     # 底部输入框
│   ├── stores/
│   │   └── chat.ts          # Zustand store：当前会话、消息列表
│   └── types/
│       └── index.ts         # Session, Message 类型定义
└── package.json
```

---

## Phase 1 Acceptance Criteria（验收标准）

完成以下 **5 项验收**，Phase 1 即为通过，可以进入 Phase 2：

### AC-1: 会话管理

- [ ] 打开网页，左侧显示空会话列表
- [ ] 点击"新建对话"，创建一个新会话，自动出现在列表顶部
- [ ] 会话列表按最近活跃时间排序
- [ ] 点击会话项，右侧显示该会话的消息历史
- [ ] 刷新页面后，会话列表和消息历史不丢失（SQLite 持久化验证通过）

### AC-2: 消息收发

- [ ] 在输入框输入文字，点击发送
- [ ] 用户消息立即出现在聊天窗口（气泡靠右）
- [ ] 3 秒内 Agent 开始回复（首个 token 到达）
- [ ] Agent 回复逐字/逐块出现在聊天窗口（气泡靠左），流式效果可感知
- [ ] 发送第二条消息时，Agent 能"记住"上文（验证上下文传递正确）

### AC-3: 流式体验

- [ ] Agent 回复过程中，用户可以看到内容在实时增长（不是一次性出现）
- [ ] 流式输出过程中，聊天窗口自动滚动到底部
- [ ] 流式输出完成时，消息完整保存在数据库（刷新后仍存在）

### AC-4: 错误处理

- [ ] Claude API Key 未配置时，发送消息显示明确的错误提示（不是白屏或无限 loading）
- [ ] 网络中断时，前端显示"连接失败"而非崩溃
- [ ] Claude API 返回错误时（如 rate limit），消息气泡显示错误信息

### AC-5: 代码质量

- [ ] `ClaudeAdapter` 实现了 `BaseAgentAdapter` 接口（接口验证通过）
- [ ] 前后端类型定义一致（Session、Message 的字段前后端对齐）
- [ ] 没有 TypeScript `any` 类型（或仅用于工具函数内部）
- [ ] API 端点有基础的输入校验（空消息拒绝、不存在的 session 返回 404）

---

## Phase 1 验收方式

| 验收项 | 验证方式 |
|--------|---------|
| AC-1 ~ AC-4 | 手动操作 + 截图记录。每个验收项一张截图，归档到 `docs/phase1-screenshots/` |
| AC-5 | 代码 Review：检查 `ClaudeAdapter` 是否继承 `BaseAgentAdapter`，检查 TypeScript 类型 |

---

## Phase 1 → Phase 2 的切换标准

同时满足以下条件，才能进入 Phase 2：

1. AC-1 ~ AC-5 全部通过
2. 团队每人独立操作过一遍完整链路
3. 至少一条 ADR 记录了 Phase 1 期间发现的架构问题（如果有的话）

## Consequences

- Phase 1 不追求功能完整，只追求链路贯通——允许硬编码、允许不优雅的实现，但不允许跳过任何验收项
- Phase 1 的代码**不是**最终架构——Phase 2 会重构引入 Service 层、Event Bus 等，这是预期内的演进
- 如果 Phase 1 超出预期时间，说明行走骨架定义的范围太大，需要砍减
