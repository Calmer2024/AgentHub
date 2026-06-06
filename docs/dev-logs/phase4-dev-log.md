# Phase 4 Dev Log: 消息交互闭环

**日期**: 2026-06-02  
**状态**: Completed

## 目标

完成用户可感知的消息闭环：

- 引用回复：消息可引用，输入区和气泡区显示引用预览。
- 重新生成：AI 消息支持 SSE 流式重生成，保留旧版本。
- Pin：消息可固定，并进入单聊/群聊上下文组装。
- 搜索：当前会话全文搜索，支持中文关键词高亮与跳转。

## 实现摘要

- 后端新增 `SqlAlchemyMessageService`，实现 `MessageService` ABC 的 Phase 4 方法。
- 新增 `/api/messages/*` 路由：reply、regenerate、pin、unpin、search、get message。
- `ChatServiceImpl` 单聊发送前通过 `ContextManager` 组装上下文，并传入 pinned ids。
- `GroupChatStream` 将 pinned ids 传给 `OrchestratorV2.PipelineRequest`，群聊路径同样享受 Pin 上下文优先级。
- 前端新增 `MessageActions`、`ReplyPreview`、`SearchPanel`，接入 `ChatWindow`、`ChatInput`、`useSendMessage`、`client.ts`。
- 新增真实 HTTP 验收脚本 `e2e/phase4_real_acceptance.py`，自动启动临时后端并验证 Phase 4 主链路。

## Bug 与修复

### 人工验收时 `/api/messages/*` 返回 404

**现象**: 浏览器控制台出现 `Failed to load resource: the server responded with a status of 404 (Not Found)`，消息搜索/Pin/引用等 Phase 4 API 不可用。

**诊断**:

- `http://127.0.0.1:8000/openapi.json` 不包含 `/api/messages/*`。
- `http://127.0.0.1:8001/openapi.json` 包含 `/api/messages/*`。
- Vite `frontend/vite.config.ts` 固定将 `/api` 代理到 `http://127.0.0.1:8000`。
- 因此浏览器请求落到了 2026-06-01 启动的旧 8000 后端进程，而不是当前代码启动的 8001。

**修复**:

- 停止旧 8000 uvicorn 进程。
- 用当前仓库代码在 8000 重新启动后端。
- 新增 `e2e/phase4_dev_proxy_check.py`，人工验收前检查 `5173 -> 8000` 的 `/api/messages/search` 是否可用。

### FTS5 update trigger 导致 Pin/Regenerate 更新失败

**现象**: `UPDATE messages SET is_pinned = ...` 和更新 `metadata_json` 时，SQLite 抛出 `SQL logic error`。

**原因**: `messages_fts_update` 对所有 `UPDATE ON messages` 触发，即使只更新非 content 字段，也会尝试重写 FTS5；旧 delete 语法在当前 FTS5 表定义下不稳定。

**修复**:

- `006_create_fts_triggers.sql` 的 delete/update trigger 改为 `DELETE FROM messages_fts WHERE rowid = old.rowid`。
- update trigger 限定为 `AFTER UPDATE OF content ON messages`。
- 新增 `008_fix_messages_fts_update_trigger.sql`，为已有数据库 drop/recreate 触发器。
- 更新迁移测试，断言 update trigger SQL 包含 `AFTER UPDATE OF content`。

## 验收

```bash
cd backend && .\venv\Scripts\python.exe -m pytest test_unit test_api test_smoke.py test_import.py -q
# 154 passed

cd frontend && npm exec vitest run
# 21 passed

cd frontend && npm run build
# passed

backend\venv\Scripts\python.exe e2e\phase4_real_acceptance.py
# Phase 4 real acceptance passed
```

### 人工验收复核：引用消息 Agent 感知

**日期**: 2026-06-02

人工验收反馈要求确认真实服务中，引用历史消息后 Agent 是否真的能感知被引用内容，而不是只显示 UI 引用卡片。

复核步骤：

1. 停止旧 `127.0.0.1:8000` uvicorn 进程。
2. 用当前仓库 `backend\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` 重启真实后端。
3. 保留当前仓库 Vite 前端 `http://127.0.0.1:5173`。
4. 在真实 UI 中新建对话，生成 4 天 3 夜攻略，并要求回复内包含唯一代号。
5. 点击该 AI 回复的 [引用]，再发送“把引用的 4 天 3 夜攻略改成一周版本”。
6. 浏览器抓包确认第二次 `/chat` 请求携带 `parentMessageId`，数据库确认用户回复保存 `metadata.replyReference` 快照。
7. Agent 最终回复复述了只存在于被引用消息里的唯一代号，并输出一周版本内容。

结论：引用消息已从 UI 状态贯通到 `/chat` 请求、消息落库、Prompt 上下文和真实 Agent 回复。Phase 4 人工验收通过。

## 与旧模块打通确认

- Phase 1/2 单聊 SSE 与消息持久化：`test_chat.py` 全量通过。
- Phase 2/3 群聊 Orchestrator SSE：`test_group_chat.py` 全量通过。
- Phase 3 ContextManager：Pin 消息在单聊和群聊测试中均验证已注入。
- Phase 3 迁移体系：新增 008 迁移，runner 幂等测试通过。
