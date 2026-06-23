# Spec: Phase 3.1 — 基础设施

**版本**: v1.0 | **状态**: ✅ COMPLETED
**关联**: Phase 3 模块总览历史文档已在 2026-06-22 文档整理中删除；当前追溯入口为 [Phase 3 README](README.md)、ADR-0005、ADR-0007

## 1. 范围

EventBus + 数据库迁移 + Service 层 ABC。所有后续模块的依赖基础。

## 2. 交付清单

- [x] `event_bus/` — InMemoryEventBus (pub/sub + 异常隔离 + fire-and-forget)
- [x] `migrations/` — 6 个 SQL 脚本 + migration_runner (幂等执行)
- [x] `services/message_service.py` — MessageService ABC (7 方法)
- [x] `services/chat_service.py` — ChatService ABC
- [x] `services/session_service.py` — SessionService 具体实现
- [x] `services/schemas.py` — 共享 Pydantic 模型
- [x] `models/` — Message (+parent_message_id, +is_pinned), Artifact (+version, +parent_artifact_id)
- [x] `agents/base.py` — BaseAgentAdapter +tools 参数
- [x] `agents/` — 6 个 adapter 签名更新

## 3. 测试

- Smoke: 14 条 | API: 39 条 | Unit: 29 条
- 新增 test_unit/: EventBus(10), MigrationRunner(6), SessionService(13)

## 4. 对其他模块的契约

参见 `services/message_service.py` (MessageService ABC), `services/chat_service.py` (ChatService ABC), `services/session_service.py`.
