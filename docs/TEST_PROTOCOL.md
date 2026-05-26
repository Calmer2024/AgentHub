# 测试协议 (Test Protocol)

**版本**: v1.0
**创建日期**: 2026-05-26
**适用范围**: AgentHub 所有开发阶段

---

## 1. 测试原则

### 1.1 核心理念

- **测试即文档**：每个阶段的测试用例精确反映 Spec 的验收标准，不做"顺便测一下"。
- **不可跳过**：未通过全部测试的 Phase 不得标记为 Completed。
- **即时暴露**：每次代码变更后必须跑相关测试，不得积累到阶段末。
- **回归防护**：任何已发现的 bug 修复后必须加入对应的回归测试。
- **功能正确是底线，体验正确是标准**：UX 交互体验测试与功能测试同等权重。详见 [UX_TEST_SPEC.md](testing/UX_TEST_SPEC.md)。

### 1.2 测试金字塔

```
        ┌──────────┐
        │  E2E 测试 │  ← 关键用户路径，每个 Phase 1-2 条
        ├──────────┤
        │ UX 测试   │  ← 6 状态覆盖（空/加载/正常/完成/错误/边界）
        ├──────────┤
        │ API 测试  │  ← 每个端点至少 1 个 happy path + 全部异常分支
        ├──────────┤
        │ 集成测试  │  ← 跨模块交互、数据库读写、Agent 调用
        ├──────────┤
        │ 单元测试  │  ← 核心业务逻辑、状态管理、工具函数
        └──────────┘
```

### 1.3 测试工具链（锁定）

| 层级 | 工具 | 用途 |
|------|------|------|
| Backend 单元/集成 | pytest + pytest-asyncio | 异步测试 |
| Backend API | httpx (ASGITransport) | 无网络开销的 API 测试 |
| Backend 数据库 | SQLite 内存数据库 + SQLAlchemy | 隔离的 DB 测试 |
| Frontend 单元 | Vitest | 组件/状态/工具函数 |
| Frontend 组件 | Vitest + @testing-library/react | 组件渲染验证 |
| Frontend E2E | Playwright | 浏览器自动化 |

---

## 2. 测试分类与要求

### 2.1 冒烟测试（Smoke Test）—— 每次提交前必须通过

目标：确认模块能加载，基本导入链未断。

```python
# backend/test_smoke.py — 每个 Phase 必须存在
# 验证所有新模块能成功 import，无 TypeError/NameError
```

```typescript
// frontend/src/__tests__/smoke.test.ts — 每个 Phase 必须存在
// 验证所有新组件能成功渲染，无运行时错误
```

### 2.2 API 测试 —— 每个端点必须覆盖

| 覆盖类型 | 最低要求 |
|---------|---------|
| Happy Path | 每个端点至少 1 条 |
| 参数校验 | 空输入、超长输入、非法类型 |
| 错误传播 | 资源不存在 (404)、业务错误 (400)、外部服务错误 (502) |
| 边界值 | 最小值、最大值、刚好越界 |

**API 测试模板**：

```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_create_session(client):
    resp = await client.post("/api/sessions", json={"title": "测试", "agent_name": "claude"})
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["title"] == "测试"

@pytest.mark.asyncio
async def test_chat_empty_content(client):
    resp = await client.post("/api/sessions/{id}/chat", json={"content": ""})
    assert resp.status_code == 400
    assert "empty" in resp.json()["error"]
```

### 2.3 前端组件测试 —— 关键交互必须覆盖

```typescript
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChatInput } from "../components/ChatInput";

describe("ChatInput", () => {
  it("renders input and submit button", () => {
    render(<ChatInput onSubmit={vi.fn()} disabled={false} />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("does not submit empty content", async () => {
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} disabled={false} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
```

### 2.4 E2E 测试 —— 每个 Phase 核心路径必须覆盖

```typescript
import { test, expect } from "@playwright/test";

test("user can create session and send a message", async ({ page }) => {
  await page.goto("http://localhost:5173");
  await page.click("text=新建对话");
  await page.fill('[role="textbox"]', "你是谁？");
  await page.click("text=发送");
  // 3 秒内看到 AI 回复
  await expect(page.locator(".message.assistant")).toBeVisible({ timeout: 3000 });
});
```

---

## 3. 测试环境规范

### 3.1 后端

```bash
# 测试专用配置文件
backend/.env.test:

ANTHROPIC_API_KEY=test-key-placeholder
DEEPSEEK_API_KEY=
DATABASE_URL=sqlite+aiosqlite:///:memory:
APP_ENV=test
```

- 测试环境使用 SQLite **内存数据库**，不污染开发/生产数据。
- Agent Adapter 在测试中 **必须 Mock**，不得调用真实 API。
- 所有测试异步 (`pytest-asyncio`)。

### 3.2 前端

```bash
# vitest.config.ts
test: {
  environment: "jsdom",
  globals: true,
  setupFiles: ["./src/test-setup.ts"],
}
```

- 测试环境使用 jsdom，不依赖真实浏览器。
- API 调用使用 MSW (Mock Service Worker) 或 vi.mock 拦截。
- 浏览器 E2E 使用 Playwright 的 headless 模式。

---

## 4. 测试执行流程

### 4.1 日常开发

```
每次代码变更后:
  1. backend:   pytest test_smoke.py -v           (10 秒)
  2. frontend:  npx vitest run smoke.test.ts      (10 秒)
  3. backend:   pytest test_api/ -v               (1-2 分钟)
  4. frontend:  npx vitest run                    (1-2 分钟)
```

### 4.2 阶段验收

```
Phase 完成前:
  1. 冒烟测试 × 2 (backend + frontend)
  2. 全量 API 测试
  3. 全量前端组件测试（功能）
  4. UX 状态覆盖检查（UX_TEST_SPEC.md 第 3 节）
  5. E2E 测试 (核心路径)
  6. 手动验证清单 (Spec 第 4 节)
  7. 全部通过 → Phase 标记为 Completed
```

### 4.3 Phase 测试计划

每个 Phase 新建 Spec 时，必须同步创建对应的测试计划目录：

```
docs/testing/phase{N}-test-plan.md    ← 本 Phase 的具体测试用例清单
backend/test_smoke.py                  ← 更新，添加新模块的导入检查
backend/test_api/                      ← API 测试，按模块分文件
  test_sessions.py
  test_chat.py
frontend/src/__tests__/               ← 前端测试，按组件分文件
  smoke.test.ts
  ChatInput.test.tsx
  ChatWindow.test.tsx
e2e/                                   ← E2E 测试（从 Phase 2 开始强制）
  phase{N}-happy-path.spec.ts
```

---

## 5. 测试数据与 Mock 规范

### 5.1 后端 Mock

```python
# 使用 pytest.monkeypatch 或 fixture 覆盖依赖
@pytest.fixture
def mock_agent():
    class FakeAgent(BaseAgentAdapter):
        async def chat_stream(self, messages, system_prompt):
            for token in ["Hello", " World", "!"]:
                yield token
    return FakeAgent()
```

### 5.2 前端 Mock

```typescript
// 使用 vi.mock 拦截 API 模块
vi.mock("../api/client", () => ({
  fetchSessions: vi.fn().mockResolvedValue([
    { id: "1", title: "测试", agentName: "claude", createdAt: "...", updatedAt: "..." },
  ]),
}));
```

### 5.3 测试数据隔离

- 每个测试函数创建独立的 session/消息数据，测试后自动回滚或销毁。
- 不依赖数据库中的预存数据（除了 Schema 迁移结果）。
- 不使用生产环境的 API Key 或真实用户数据。

---

## 6. Bug 修复流程与回归测试

### 6.1 流程

```
发现 Bug → 在对应测试文件中写 1 条回归测试 → 确认回归测试 FAIL → 修复 → 确认 PASS
```

### 6.2 示例

本次修复的 SSE JSON 非法格式问题：

```python
# backend/test_api/test_chat.py — 回归测试
import json

@pytest.mark.asyncio
async def test_sse_events_are_valid_json(client, db_session):
    """回归测试：所有 SSE 事件必须是合法 JSON。修复 !r 导致的单引号问题。"""
    resp = await client.post("/api/sessions/{sid}/chat", json={"content": "hi"})
    async for line in resp.aiter_lines():
        if line.startswith("data: "):
            data = json.loads(line[6:])  # 不应抛异常
            assert "done" in data
            if "token" in data:
                assert isinstance(data["token"], str)
```

---

## 7. Phase 完成检查清单

每个 Phase 结束前，必须逐条确认：

### 通用

- [ ] `backend/test_smoke.py` 通过（含本 Phase 新增的所有模块）
- [ ] `frontend/src/__tests__/smoke.test.ts` 通过
- [ ] 本 Phase 所有 API 端点有至少 1 个 happy path 测试
- [ ] 本 Phase 所有 API 端点的异常分支（400/404/500）有覆盖
- [ ] Spec 第 4 节所有验收标准已通过（自动或手动）
- [ ] 上一 Phase 的测试全部仍通过（无回归）

### 后端专项

- [ ] 所有 `async def` 端点用 `pytest-asyncio` 测试
- [ ] 外部依赖（Agent、数据库）正确 Mock
- [ ] 测试用内存数据库，不写磁盘
- [ ] 每个新的 Pydantic Model 有序列化/反序列化测试

### 前端专项（功能）

- [ ] 所有新组件有至少 1 个渲染测试
- [ ] 关键用户交互（点击、输入、提交）有测试
- [ ] Store 的状态转换逻辑有测试
- [ ] 无 TypeScript `any` 类型
- [ ] shadcn/ui 组件正确导入

### 前端专项（UX 体验）

- [ ] 每个新组件通过 6 状态检查（空/加载/正常/完成/错误/边界），详见 [UX_TEST_SPEC.md](testing/UX_TEST_SPEC.md)
- [ ] 加载态：有明确的加载指示器，用户不会认为"卡死了"
- [ ] 空状态：有引导文案 + 行动入口，不是空白区域
- [ ] 错误态：错误信息用中文、说明原因、提供操作入口（重试/返回）
- [ ] 流式过程中：输入框禁用 + placeholder 提示 + 发送按钮禁用 + 打字指示器可见
- [ ] 流式完成后：指示器消失 → 输入框恢复 → 内容完整显示
- [ ] P0/P1 级 UX 缺陷必须在当前 Phase 修复

---

## 8. 常见陷阱

| 陷阱 | 现象 | 检测方式 |
|------|------|---------|
| Python `!r` 在 JSON 中 | 前端静默失败，SSE 不显示 | 回归测试用 `json.loads()` 逐行校验 |
| `from __future__` 缺失 | Python 3.9 报 TypeError | 冒烟测试覆盖所有 import |
| 前端 `EventSource` 用 GET | 405 Method Not Allowed | API 测试只测 POST |
| 组件 key 使用 index | 列表重排时状态混乱 | 检查 React DevTools 的 key 警告 |
| async session 未 await | 数据未持久化 | 测试中显式查询数据库验证 |

---

## 9. 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-26 | v1.0 | 初始版本，覆盖 Phase 1 测试规范 |
