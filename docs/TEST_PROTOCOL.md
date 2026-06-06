# 测试协议 (Test Protocol)

**版本**: v2.3
**创建日期**: 2026-05-26
**最后更新**: 2026-06-02
**适用范围**: AgentHub 所有开发阶段

---

## 1. 测试原则

### 1.1 核心理念

- **测试即文档**：每个阶段的测试用例精确反映 Spec 的验收标准，不做"顺便测一下"。
- **不可跳过**：未通过全部测试的 Phase 不得标记为 Completed。
- **即时暴露**：每次代码变更后必须跑相关测试，不得积累到阶段末。
- **回归防护**：任何已发现的 bug 修复后必须加入对应的回归测试。
- **功能正确是底线，体验正确是标准**：UX 交互体验测试与功能测试同等权重。详见 [UX_TEST_SPEC.md](testing/UX_TEST_SPEC.md)。
- **Mock 不改变代码路径**：Mock 只能替换外部依赖的返回值，不能跳过被测试的业务代码。如果 mock 让某条 `if` 分支、某个函数调用不被执行，那就在测试盲区里制造了虚假的安全感。

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
| Backend 数据库 | SQLite 文件数据库（临时目录）+ 真实迁移 | 真实 schema，与生产一致 |
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

### 2.2 API 测试 —— 每个端点 + 每个模式变体必须覆盖

| 覆盖类型 | 最低要求 |
|---------|---------|
| Happy Path | 每个端点 **× 每个模式变体** 至少 1 条 |
| 参数校验 | 空输入、超长输入、非法类型 |
| 错误传播 | 资源不存在 (404)、业务错误 (400)、外部服务错误 (502) |
| 边界值 | 最小值、最大值、刚好越界 |
| **模式变体** | **每个端点如果存在条件分支（如 `mode=single` vs `mode=group`），每条分支必须独立覆盖** |

> ⚠️ **教训 (2026-06-01)**：`POST /sessions/{id}/chat` 在 `mode=single` 和 `mode=group` 下走完全不同的代码路径（前者直接调 adapter，后者走 AgentExecutor 四阶段 Pipeline）。Phase 3 期间，group chat 消息发送路径未被任何测试覆盖，导致 `asyncio.wait_for(async_generator)` 致命 Bug 漏到人工验收。此后，任何端点的任何模式变体必须有独立测试。

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

```python
# backend/conftest.py — 在所有 app 模块导入前设置环境变量
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{temp_db_path}"
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-dummy-key-...")  # 虚拟 key
```

- 测试使用 **文件数据库**（系统临时目录），执行完整 lifespan（create_all + migrations + EventBus）。
- 只默认设置 DeepSeek 系统模型虚拟 Key；用户可见 Agent 不再默认注入厂商 API Key。
- CLI Agent 测试使用 fixture CLI 脚本走真实 subprocess 路径；系统 LLM 测试在 `system_llm` service seam 注入 fake。
- WAL 模式避免多连接锁冲突，每测试后 DELETE 清理数据。
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
  5a. 若本 Phase 引入/重构架构层，必须补架构契约测试（Domain 纯逻辑、Service 编排、Infrastructure 适配器契约）
  6. 清理旧服务进程，使用当前仓库代码启动新的后端/前端服务进程
  7. 在新服务进程上执行真实服务验收，并确认前端 `/api` 代理命中当前后端
  8. 手动验证清单 (Spec 第 4 节)
  9. 最终交付必须给出前端地址、后端地址、API docs 地址
  10. 全部通过 → Phase 标记为 Completed
```

### 4.2.1 真实服务进程交接（硬性要求）

每轮开发/修复结束时必须执行，不限于 Phase 收尾：

1. **清理旧进程**：检查默认端口 `127.0.0.1:8000`（后端）和 `127.0.0.1:5173`（前端）。发现旧代码进程或无关进程占用时，停止旧进程或改用新端口，并记录原因。
2. **启动新进程**：后端必须从当前仓库 `backend/` 启动；前端必须从当前仓库 `frontend/` 启动。
3. **验证新进程**：
   - 后端根路径 `/` 返回正常。
   - OpenAPI 包含本轮新增/修改的端点。
   - 前端根路径返回正常。
   - 前端 `/api` 代理能访问当前后端。
   - 本轮改动的关键路径在真实服务上通过。
4. **交付地址**：最终回复必须包含前端 URL、后端 URL、API docs URL。若端口不是默认值，必须明确说明。

未执行上述步骤，或旧服务仍在提供旧代码，视为验收未完成。

### 4.3 Phase 测试计划

每个 Phase 新建 Spec 时，应同步创建对应的测试计划：

```
docs/testing/phase{N}-test-plan.md    ← 本 Phase 的具体测试用例清单（Phase 1 起创建，Phase 2 测试覆盖记录见 phase2-dev-log.md）
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

### 5.1 后端 Fake

```python
# CLI Agent: 用一个真实 Python 脚本作为 executable，仍走 subprocess/stdin/stdout。
agent = AgentConfig(
    agent_type="cli_wrapper",
    cli_tool="custom",
    executable=sys.executable,
    init_args=json.dumps([str(fixture_cli)]),
    env_vars="{}",
)

# System LLM: 在 service seam 注入 fake，不恢复旧 provider registry。
monkeypatch.setattr(artifact_service_module, "system_llm", FakeSystemLLM())
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
- [ ] **本 Phase 所有 API 端点的每个模式变体（single/group、不同 role 等）都有独立测试覆盖**
- [ ] 本 Phase 所有 API 端点的异常分支（400/404/500）有覆盖
- [ ] Spec 第 4 节所有验收标准已通过（自动或手动）
- [ ] 上一 Phase 的测试全部仍通过（无回归）
- [ ] 旧后端/前端进程已清理，新服务进程已从当前仓库启动
- [ ] 真实服务验收已通过，且最终交付包含前端/后端/API docs 地址

### 后端专项

- [ ] 所有 `async def` 端点用 `pytest-asyncio` 测试
- [ ] 外部依赖（Agent、数据库）正确 Mock
- [ ] 测试用文件数据库（临时目录），执行完整迁移，每测试后清理
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
| `engine.begin()` DDL in lifespan | 启动时 SQLite 报错，生产不可用 | 测试触发 lifespan，立即失败 |
| 文件 DB 跨测试数据泄漏 | 测试之间互相影响结果 | `_cleanup_db` autouse fixture DELETE 所有表 |
| FTS5 触发器影响 DELETE | SQL logic error | 清理前 `PRAGMA foreign_keys=OFF` |
| `asyncio.wait_for(async_gen)` | 全部 Agent 抛 `TypeError: 'async for' requires __aiter__` | **任何对 async generator 添加超时的位置必须用 `async with asyncio.timeout(seconds):` 而非 `asyncio.wait_for(generator, timeout)`。** `wait_for()` 只接受 coroutine (有 `__await__`)，不接受 async generator (有 `__aiter__`)。检测方式：用 fixture CLI 覆盖 group chat 的 `AgentExecutor._execute_single()` 路径并累积 SSE token。 |
| 测试只覆盖一条模式分支 | 所有测试通过但人工验收崩溃 | **列出端点内所有 if/switch 分支（如 `mode=single` vs `mode=group`），逐条确认每个分支都有至少 1 个测试。** 仅靠 "单聊测试" 不能保证 "群聊" 也正常 — 它们走的是不同的代码路径。**检查方法**: 阅读端点的源码，圈出所有 `if mode ==` / `if session.mode ==` 分支，在测试文件中搜索对应的测试用例名。 |
| 能力声明与真实实现不一致 | Service 判断 `supports_tool_call=True`，但系统模型没有把 `tools` 传给 DeepSeek | **能力声明必须可兑现。** Phase 5 后，系统 LLM 的工具调用路径必须测试 `chat(..., tools=[...])` 传参并解析 `tool_calls`；不可用时由 Service 降级。 |
| 版本链列表污染当前产物 | 会话产物列表显示 v1/v2 多张重复卡 | **会话产物列表只返回版本链头节点**；历史版本通过 `/artifacts/{id}/versions` 查询。API 测试必须覆盖这一语义。 |
| 旧进程仍在服务旧代码 | 单元测试通过，但浏览器/API 访问不到新增接口 | **每轮结束必须清理旧进程并重启新服务。** 检查端口监听进程、OpenAPI、前端 `/api` 代理和真实服务关键路径；最终回复必须给出访问地址。 |

---

## 9. 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-02 | v2.3 | 增加每轮结束清理旧进程、启动新服务、真实服务验收并交付访问地址的硬性要求 |
| 2026-06-02 | v2.2 | Phase 5 增加架构契约测试要求；记录 tool calling 能力声明、Artifact 版本链头节点测试陷阱 |
| 2026-06-01 | v2.1 | 复盘 Orchestrator 测试盲区: 新增"Mock 不改变代码路径"原则、模式变体强制覆盖、`asyncio.wait_for` 陷阱、分支覆盖检查清单 |
| 2026-05-27 | v2.0 | 测试策略升级：内存DB→文件DB+真实迁移+lifespan触发，Mock→真实registry注册 |
| 2026-05-26 | v1.0 | 初始版本，覆盖 Phase 1 测试规范 |
